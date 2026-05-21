"""모델 × 평가축을 순차 실행하는 메인 오케스트레이터 (Furiosa RNGD / furiosa-llm).

사용:
    python orchestrator.py configs/models.yaml --tasks tps,sweep,memsweep,swebench,embed,rerank
    python orchestrator.py configs/models.yaml --tasks tps --models Llama-3.1-8B
    python orchestrator.py configs/models.yaml --dry-run

태스크:
  tps      - concurrency=1, stream으로 TTFT/ITL/output_TPS
  sweep    - concurrency × prompt_len 매트릭스
  memsweep - furiosa-llm serve 인자(max-model-len, max-batch-size,
             max-num-batched-tokens) OFAT 스윕
  embed    - 임베딩 모델 throughput (batch size별)
  rerank   - 리랭커 모델 throughput
  swebench - SWE-bench Lite oracle 예측 (+ 채점은 swebench_eval.py)

결과: results/<model_safe>/<task>/<timestamp>.json
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from runners.server import FuriosaServer  # noqa: E402
from runners.tps import run_concurrency, to_jsonable  # noqa: E402
from runners.memory_sweep import sweep_serve_args  # noqa: E402
from runners.embed_bench import (  # noqa: E402
    bench_embeddings, bench_reranker, to_jsonable_embed, to_jsonable_rerank,
)

RESULTS_ROOT = REPO_ROOT / "results"
LOGS_ROOT = REPO_ROOT / "results" / "_server_logs"

GEN_TASKS = {"tps", "sweep", "memsweep", "swebench"}
EMBED_TASKS = {"embed"}
RERANK_TASKS = {"rerank"}


def _safe_name(s: str) -> str:
    return s.replace("/", "__").replace(":", "_")


def _ts() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _split_serve_args(args: list[str], default_devices: str):
    """공통+모델 serve_args에서 host/port/devices를 분리, 나머지는 extra로."""
    extra: list[str] = []
    host, port, devices = "0.0.0.0", 8000, default_devices
    it = iter(args)
    for tok in it:
        if tok == "--host":
            host = next(it)
        elif tok == "--port":
            port = int(next(it))
        elif tok == "--devices":
            devices = next(it)
        else:
            extra.append(tok)
    return host, port, devices, extra


def _build_serve_args(model_cfg: dict, common: list[str]) -> list[str]:
    return list(common) + list(model_cfg.get("serve_args") or [])


# ---------- 태스크별 실행 ----------

async def _task_tps(server, model, sweep, out_dir):
    res = await run_concurrency(
        base_url=server.base_url, model=model, concurrency=1,
        prompt_tokens_target=sweep.get("prompt_lens", [1024])[0],
        max_tokens=sweep["max_tokens"], n_requests=sweep["measured_requests"],
        warmup=sweep["warmup_requests"],
    )
    _save_json(out_dir / f"tps_{_ts()}.json", to_jsonable(res))
    print(f"  [tps] {json.dumps(res.summary(), ensure_ascii=False)}")


async def _task_sweep(server, model, sweep, out_dir):
    summaries = []
    for plen in sweep["prompt_lens"]:
        for bs in sweep["batch_sizes"]:
            print(f"  [sweep] concurrency={bs}, prompt_len={plen}")
            try:
                res = await run_concurrency(
                    base_url=server.base_url, model=model, concurrency=bs,
                    prompt_tokens_target=plen, max_tokens=sweep["max_tokens"],
                    n_requests=max(sweep["measured_requests"], bs * 4),
                    warmup=sweep["warmup_requests"],
                )
                summaries.append(res.summary())
            except Exception as e:
                summaries.append({
                    "model": model, "concurrency": bs, "prompt_tokens_target": plen,
                    "error": f"{type(e).__name__}: {e}",
                })
    _save_json(out_dir / f"sweep_{_ts()}.json", {"sweep": summaries})


async def _task_memsweep(model_cfg, common, devices, model, out_dir, sweep, memsweep_cfg):
    base_args = _build_serve_args(model_cfg, common)
    host, port, _, extra = _split_serve_args(base_args, devices)
    log_dir = LOGS_ROOT / _safe_name(model)
    # prompt_len은 중간값 고정: max_model_len=4096 조합에서도
    # prompt+max_tokens가 한도를 넘지 않게 해서 OOM이 아닌 max_len 탈락을 막음.
    mid_plen = sweep["prompt_lens"][len(sweep["prompt_lens"]) // 2]
    rows = await sweep_serve_args(
        model=model, revision=model_cfg.get("revision"),
        devices=devices, base_extra_args=extra, memsweep_cfg=memsweep_cfg,
        host=host, port=port,
        concurrency=sweep["batch_sizes"][-1], prompt_len=mid_plen,
        max_tokens=sweep["max_tokens"],
        n_requests=max(sweep["measured_requests"], sweep["batch_sizes"][-1] * 2),
        warmup=sweep["warmup_requests"], out_dir=out_dir, log_dir=log_dir,
    )
    print(f"  [memsweep] {len(rows)} combos done")


async def _task_embed(server, model, out_dir):
    results = await bench_embeddings(server.base_url, model)
    _save_json(out_dir / f"embed_{_ts()}.json",
               {"results": [to_jsonable_embed(r) for r in results]})
    for r in results:
        print(f"  [embed] {json.dumps(r.summary(), ensure_ascii=False)}")


async def _task_rerank(server, model, out_dir):
    res = await bench_reranker(server.base_url, model)
    _save_json(out_dir / f"rerank_{_ts()}.json", to_jsonable_rerank(res))
    print(f"  [rerank] {json.dumps(res.summary(), ensure_ascii=False)}")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _task_swebench(model, base_url, out_dir):
    from runners.swebench_run import load_instances, run_predictions, DEFAULT_DATASET
    dataset_name = os.environ.get("SWEBENCH_DATASET", DEFAULT_DATASET)
    n = int(os.environ.get("SWEBENCH_N", "50") or 0)
    max_tokens = int(os.environ.get("SWEBENCH_MAXTOK", "1024"))
    concurrency = int(os.environ.get("SWEBENCH_CONC", "8"))
    filter_context = _env_flag("SWEBENCH_FILTER_CONTEXT", True)
    drop_invalid_patch = _env_flag("SWEBENCH_DROP_INVALID_PATCH", False)
    retry_invalid = int(os.environ.get("SWEBENCH_RETRY_INVALID", "0") or 0)
    max_input_tokens_env = os.environ.get("SWEBENCH_MAX_INPUT_TOKENS")
    max_input_tokens = int(max_input_tokens_env) if max_input_tokens_env else None
    preds_dir = out_dir / "preds"
    print(f"  [swebench] dataset={dataset_name} subset={n or 'full'}")
    instances = load_instances(dataset_name, subset=(n or None))
    summary = run_predictions(
        instances=instances, model_name=model, base_url=base_url,
        output_dir=preds_dir, temperature=0.0,
        max_tokens=max_tokens, concurrency=concurrency,
        filter_context=filter_context, max_input_tokens=max_input_tokens,
        drop_invalid_patch=drop_invalid_patch, retry_invalid=retry_invalid,
    )
    summary.setdefault("instance_ids", [i["instance_id"] for i in instances])
    _save_json(out_dir / f"swebench_{_ts()}.json", summary)
    printable = {k: v for k, v in summary.items() if k != "instance_ids"}
    print(f"  [swebench] {json.dumps(printable, ensure_ascii=False)}")


# ---------- 모델 단위 ----------

async def run_for_model(model_cfg, common, devices, sweep, tasks, memsweep_cfg=None):
    model = model_cfg["id"]
    if not model_cfg.get("enabled", True):
        print(f"== SKIP {model} (disabled) ==")
        return

    role_gen = model_cfg.get("gen", True)
    is_embed = model_cfg.get("role") == "embedding"
    is_rerank = model_cfg.get("role") == "reranker"

    applicable = set()
    if role_gen:
        applicable |= tasks & GEN_TASKS
    if is_embed:
        applicable |= tasks & EMBED_TASKS
    if is_rerank:
        applicable |= tasks & RERANK_TASKS
    if not applicable:
        print(f"== SKIP {model} (no applicable task: tasks={tasks}, role={model_cfg.get('role')}) ==")
        return

    out_root = RESULTS_ROOT / _safe_name(model)
    log_path = LOGS_ROOT / f"{_safe_name(model)}_{_ts()}.log"
    base_args = _build_serve_args(model_cfg, common)
    host, port, devs, extra = _split_serve_args(base_args, devices)

    print(f"\n== {model} ==  devices={devs}  tasks={sorted(applicable)}")

    if "memsweep" in applicable:
        await _task_memsweep(model_cfg, common, devs, model, out_root / "memsweep", sweep, memsweep_cfg)
        applicable -= {"memsweep"}
    if not applicable:
        return

    server = FuriosaServer(
        model=model, revision=model_cfg.get("revision"),
        devices=devs, host=host, port=port,
        extra_args=extra, log_path=log_path,
    )
    try:
        with server:
            if "tps" in applicable:
                await _task_tps(server, model, sweep, out_root / "tps")
            if "sweep" in applicable:
                await _task_sweep(server, model, sweep, out_root / "sweep")
            if "embed" in applicable:
                await _task_embed(server, model, out_root / "embed")
            if "rerank" in applicable:
                await _task_rerank(server, model, out_root / "rerank")
            if "swebench" in applicable:
                _task_swebench(model, server.base_url, out_root / "swebench")
    except Exception:
        print(f"!! {model} 실패. server log: {log_path}")
        traceback.print_exc()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", type=Path)
    ap.add_argument("--tasks", default="tps,sweep",
                    help="comma-separated: tps, sweep, memsweep, embed, rerank, swebench")
    ap.add_argument("--models", default=None, help="comma-separated substring filter")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    tasks = set(t.strip() for t in args.tasks.split(",") if t.strip())
    only = set(s.strip() for s in (args.models or "").split(",") if s.strip())

    selected = [m for m in cfg["models"]
                if not only or any(s in m["id"] for s in only)]

    if args.dry_run:
        for m in selected:
            print(f"would run: {m['id']}  enabled={m.get('enabled', True)}  tasks={sorted(tasks)}")
        return

    asyncio.run(_run_all(selected, cfg, tasks))


async def _run_all(selected, cfg, tasks):
    for m in selected:
        await run_for_model(
            model_cfg=m,
            common=cfg.get("common_serve_args", []),
            devices=str(cfg.get("devices", "npu:0")),
            sweep=cfg["sweep"], tasks=tasks,
            memsweep_cfg=cfg.get("memsweep"),
        )


if __name__ == "__main__":
    main()
