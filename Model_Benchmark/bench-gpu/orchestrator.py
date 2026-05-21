"""모델 × 평가축을 순차 실행하는 메인 오케스트레이터 (NVIDIA GPU / vLLM).

사용:
    python orchestrator.py configs/models.yaml --tasks tps,sweep,memsweep,swebench,embed,rerank
    python orchestrator.py configs/models.yaml --tasks tps --models Llama-3.1-8B
    python orchestrator.py configs/models.yaml --dry-run

태스크:
  tps      - concurrency=1, stream으로 TTFT/ITL/output_TPS
  sweep    - concurrency × prompt_len 매트릭스
  memsweep - vllm serve 인자(max-model-len, max-num-seqs, gpu-memory-utilization) OFAT 스윕
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

from runners.server import VllmServer  # noqa: E402
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


def _split_serve_args(args: list[str]):
    """공통+모델 serve_args에서 host/port를 분리, 나머지는 extra로."""
    extra: list[str] = []
    host, port = "0.0.0.0", 8000
    it = iter(args)
    for tok in it:
        if tok == "--host":
            host = next(it)
        elif tok == "--port":
            port = int(next(it))
        else:
            extra.append(tok)
    return host, port, extra


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


async def _task_memsweep(model_cfg, common, model, out_dir, sweep, memsweep_cfg, cuda):
    base_args = _build_serve_args(model_cfg, common)
    host, port, extra = _split_serve_args(base_args)
    log_dir = LOGS_ROOT / _safe_name(model)
    mid_plen = sweep["prompt_lens"][len(sweep["prompt_lens"]) // 2]
    rows = await sweep_serve_args(
        model=model, revision=model_cfg.get("revision"),
        base_extra_args=extra, memsweep_cfg=memsweep_cfg,
        host=host, port=port, cuda_visible_devices=cuda,
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

async def run_for_model(model_cfg, common, sweep, tasks, memsweep_cfg=None, cuda="0"):
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
    host, port, extra = _split_serve_args(base_args)

    print(f"\n== {model} ==  cuda={cuda}  tasks={sorted(applicable)}")

    if "memsweep" in applicable:
        await _task_memsweep(model_cfg, common, model, out_root / "memsweep", sweep, memsweep_cfg, cuda)
        applicable -= {"memsweep"}
    if not applicable:
        return

    server = VllmServer(
        model=model, revision=model_cfg.get("revision"),
        host=host, port=port, cuda_visible_devices=cuda,
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
            sweep=cfg["sweep"], tasks=tasks,
            memsweep_cfg=cfg.get("memsweep"),
            cuda=str(cfg.get("cuda_visible_devices", "0")),
        )


if __name__ == "__main__":
    main()
