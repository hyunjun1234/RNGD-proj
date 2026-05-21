"""furiosa-llm serve 옵션 OFAT 스윕 (Furiosa RNGD NPU).

furiosa-llm serve를 다른 인자로 여러 번 띄워 다음 질문에 답한다:
  - max-model-len / max-batch-size / max-num-batched-tokens 가 처리량·OOM에 미치는 영향
  - 동시 접속자 N명을 안정적으로 받으려면 어떤 serve 옵션 조합이 필요한가

OFAT(One-Factor-At-a-Time): baseline에서 한 번에 한 축만 변경. full cartesian은
모델당 서버를 수십~수백 회 재기동해야 해서 비현실적이므로, 각 serve 옵션의
독립적 효과만 본다. 조합 수 = 1(baseline) + 각 축 값 개수의 합.

주의: spare_blocks_ratio는 furiosa-llm 2026.2.0에서 deprecated(0.0이어야 하며
다른 값은 엔진 패닉) → 축에서 제외.
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


DEFAULT_MEMSWEEP = {
    "baseline": {},
    "axes": {
        "max_model_len": [4096, 8192, 16384],
        "max_batch_size": [8, 32],
        "max_num_batched_tokens": [4096, 16384],
    },
}


def _ofat_combinations(cfg: dict) -> list[dict]:
    """{baseline, axes} 설정으로 OFAT 조합 목록 생성."""
    if "axes" in cfg or "baseline" in cfg:
        baseline = dict(cfg.get("baseline") or {})
        axes = cfg.get("axes") or {}
    else:
        baseline = {}
        axes = {k: [v for v in vs if v is not None] for k, vs in cfg.items()}

    combos: list[dict] = [dict(baseline)]
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
    """combo dict → furiosa-llm serve 인자."""
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
    host: str = "0.0.0.0",
    port: int = 8000,
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
        extra = base_extra_args + _combo_to_args(combo)
        log_path = (log_dir / f"memsweep_{i:03d}.log") if log_dir else None
        print(f"\n[memsweep {i+1}/{len(combos)}] combo={combo}")

        server = FuriosaServer(
            model=model, revision=revision, devices=devices,
            host=host, port=port, extra_args=extra, log_path=log_path,
        )
        row: dict = {"combo": combo, "started_at": time.time()}
        try:
            with server:
                row["server_info"] = await _collect_server_info(server.base_url)
                res = await run_concurrency(
                    base_url=server.base_url, model=model,
                    concurrency=concurrency, prompt_tokens_target=prompt_len,
                    max_tokens=max_tokens, n_requests=n_requests, warmup=warmup,
                )
                row["bench"] = res.summary()
                if "error" in row["bench"] or row["bench"].get("failures", 0):
                    row["status"] = "error"
                    row["error"] = row["bench"].get("error", "request failures")
                else:
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
        (out_dir / "memsweep_summary.json").write_text(json.dumps(rows, indent=2, default=str))
    return rows


async def _collect_server_info(base_url: str) -> dict:
    info: dict = {}
    async with httpx.AsyncClient(timeout=5.0) as c:
        for path in ["/models", "/../metrics", "/../healthz"]:
            try:
                r = await c.get(base_url + path)
                if r.status_code == 200:
                    ct = r.headers.get("content-type", "")
                    info[path] = r.json() if "json" in ct else r.text[:1000]
            except Exception:
                pass
    return info
