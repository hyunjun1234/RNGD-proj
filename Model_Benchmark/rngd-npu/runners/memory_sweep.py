"""Serve 시점 옵션 스윕.

`tps.py`의 sweep은 request shape(concurrency × prompt_len)만 변경하지만,
이 모듈은 furiosa-llm serve를 다른 인자로 여러 번 띄워서 다음 질문에 답합니다:

- 동시 접속자 N명을 지원하려면 어떤 serve 옵션 조합이 필요한가
- KV cache 풀 크기, max-batch-size, max-num-batched-tokens가 throughput과 OOM에 어떻게 영향
- spare-blocks-ratio 늘리면 prefix caching hit-rate가 좋아지는가 (그리고 OOM 안전한가)

각 조합마다:
  1. 새 인자로 server 재시작
  2. tps.run_concurrency로 부하 측정
  3. /v1/models, /metrics 등에서 부가 정보 수집
  4. 정리 후 다음 조합으로
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import httpx

from .server import FuriosaServer
from .tps import run_concurrency, to_jsonable


# OFAT(One-Factor-At-a-Time) memsweep 기본 설정.
# baseline(=furiosa-llm 기본값)에서 한 번에 한 축만 변경한다. full cartesian은
# 모델당 서버를 수십~수백 회 재기동해야 해서 비현실적이므로, 각 serve 옵션의
# 독립적 효과만 본다. 조합 수 = 1 + 각 축 값 개수의 합.
# 주의: spare_blocks_ratio는 furiosa-llm 2026.2.0에서 deprecated(0.0이어야 하며
# 다른 값은 엔진 패닉) → 축에서 제외.
DEFAULT_MEMSWEEP = {
    "baseline": {},
    "axes": {
        "max_model_len": [4096, 8192, 16384],
        "max_batch_size": [8, 32],
        "max_num_batched_tokens": [4096, 16384],
    },
}


def _ofat_combinations(cfg: dict) -> list[dict]:
    """{baseline, axes} 설정으로 OFAT 조합 목록 생성.

    또는 옛 형식 {axis: [values]} (cartesian)도 받아 baseline {}에서의
    OFAT으로 해석한다 (None 값은 baseline 의미라 무시).
    """
    if "axes" in cfg or "baseline" in cfg:
        baseline = dict(cfg.get("baseline") or {})
        axes = cfg.get("axes") or {}
    else:
        # 옛 형식: 각 키가 곧 축. None은 "기본값" 의미라 제외.
        baseline = {}
        axes = {k: [v for v in vs if v is not None] for k, vs in cfg.items()}

    combos: list[dict] = [dict(baseline)]          # baseline 먼저
    seen = {tuple(sorted(baseline.items()))}
    for axis, values in axes.items():
        for v in values:
            if v is None:
                continue
            combo = dict(baseline)
            combo[axis] = v
            key = tuple(sorted(combo.items()))
            if key not in seen:
                seen.add(key)
                combos.append(combo)
    return combos


def _combo_to_args(combo: dict) -> list[str]:
    args: list[str] = []
    if "max_model_len" in combo:
        args += ["--max-model-len", str(combo["max_model_len"])]
    if "max_batch_size" in combo:
        args += ["--max-batch-size", str(combo["max_batch_size"])]
    if "max_num_batched_tokens" in combo:
        args += ["--max-num-batched-tokens", str(combo["max_num_batched_tokens"])]
    if "spare_blocks_ratio" in combo:
        args += ["--spare-blocks-ratio", str(combo["spare_blocks_ratio"])]
    return args


async def sweep_serve_args(
    model: str,
    revision: Optional[str],
    devices: str,
    base_extra_args: list[str],
    memsweep_cfg: Optional[dict] = None,
    concurrency: int = 16,
    prompt_len: int = 1024,
    max_tokens: int = 256,
    n_requests: int = 64,
    warmup: int = 4,
    out_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
) -> list[dict]:
    """OFAT 조합마다 serve→bench→stop 반복. 각 결과 json으로 저장."""
    combos = _ofat_combinations(memsweep_cfg or DEFAULT_MEMSWEEP)
    rows: list[dict] = []
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for i, combo in enumerate(combos):
        combo_args = _combo_to_args(combo)
        extra = base_extra_args + combo_args
        log_path = (log_dir / f"memsweep_{i:03d}.log") if log_dir else None
        print(f"\n[memsweep {i+1}/{len(combos)}] combo={combo}")

        server = FuriosaServer(
            model=model, revision=revision, devices=devices,
            extra_args=extra, log_path=log_path,
        )
        row: dict = {"combo": combo, "started_at": time.time()}
        try:
            with server:
                # 서버 가동 후 KV cache / 메모리 정보 수집 시도
                row["server_info"] = await _collect_server_info(server.base_url)
                res = await run_concurrency(
                    base_url=server.base_url, model=model,
                    concurrency=concurrency,
                    prompt_tokens_target=prompt_len,
                    max_tokens=max_tokens,
                    n_requests=n_requests,
                    warmup=warmup,
                )
                row["bench"] = res.summary()
                row["status"] = "ok"
                if out_dir:
                    (out_dir / f"memsweep_{i:03d}.json").write_text(
                        json.dumps({"combo": combo, **to_jsonable(res)}, indent=2, default=str)
                    )
        except Exception as e:
            row["status"] = "error"
            row["error"] = f"{type(e).__name__}: {e}"
            print(f"  !! {row['error']}")
        rows.append(row)

    if out_dir:
        (out_dir / "memsweep_summary.json").write_text(
            json.dumps(rows, indent=2, default=str)
        )
    return rows


async def _collect_server_info(base_url: str) -> dict:
    info: dict = {}
    async with httpx.AsyncClient(timeout=5.0) as c:
        for path in ["/models", "/../metrics", "/../healthz"]:
            url = base_url + path
            try:
                r = await c.get(url)
                if r.status_code == 200:
                    ct = r.headers.get("content-type", "")
                    info[path] = r.json() if "json" in ct else r.text[:1000]
            except Exception:
                pass
    return info
