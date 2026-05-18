"""SWE-bench inference + evaluation 래퍼.

흐름:
  1. princeton-nlp/SWE-bench_Lite_oracle 로드 — `text` 컬럼이 prebuilt라 pyserini/BM25
     불필요. oracle = 정답 파일이 context로 주어짐 → "올바른 파일이 주어졌을 때
     이슈를 해결하는 patch를 만들 수 있는가" = 순수 코드 편집/생성 능력 측정.
  2. 로컬 furiosa-llm OpenAI 호환 서버(/v1/chat/completions)에 text를 보내 diff 생성.
  3. swebench.harness.run_evaluation (Docker)로 실제 테스트 통과(resolved) 여부 평가.
     --namespace swebench 기본값 → prebuilt instance 이미지를 pull (대량 빌드 생략).

swebench.inference.run_api는 OpenAI/Anthropic 모델명에 하드코딩(MODEL_LIMITS)돼 있어
로컬 모델로는 못 쓴다 → 자체 inference 루프로 대체한다.

환경변수:
  SWEBENCH_DATASET  - inference용 데이터셋 (default princeton-nlp/SWE-bench_Lite_oracle)
  SWEBENCH_N        - subset 크기 (default 50, 0 또는 미설정-full=300)
  SWEBENCH_MAXTOK   - 응답 max_tokens (default 4096)
  SWEBENCH_CONC     - 동시 요청 수 (default 8)
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

DEFAULT_DATASET = "princeton-nlp/SWE-bench_Lite_oracle"
EVAL_DATASET = "princeton-nlp/SWE-bench_Lite"   # harness가 채점에 쓰는 데이터셋

SYSTEM_PROMPT = (
    "You are an expert software engineer. You are given an issue statement and "
    "the relevant part of a code base. Produce a single patch in unified diff "
    "format that resolves the issue. Output ONLY the patch wrapped in a fenced "
    "```diff code block."
)


def load_instances(
    dataset_name: str = DEFAULT_DATASET,
    subset: Optional[int] = None,
    seed: int = 0,
) -> list[dict]:
    """oracle 데이터셋(test split) 로드. subset이 주어지면 repo별 stratified 샘플.

    stratified: SWE-bench Lite의 repo 분포를 유지하도록 repo를 round-robin으로 돌며
    추출 → 특정 repo에 치우치지 않는 대표 subset.
    """
    from datasets import load_dataset

    rows = list(load_dataset(dataset_name, split="test"))
    if not subset or subset >= len(rows):
        return rows

    import random

    by_repo: dict[str, list] = defaultdict(list)
    for r in rows:
        by_repo[r["repo"]].append(r)
    rng = random.Random(seed)
    for v in by_repo.values():
        rng.shuffle(v)

    picked: list[dict] = []
    repos = sorted(by_repo)
    i = 0
    while len(picked) < subset and any(by_repo[r] for r in repos):
        bucket = by_repo[repos[i % len(repos)]]
        if bucket:
            picked.append(bucket.pop())
        i += 1
    return picked


def run_predictions(
    instances: list[dict],
    model_name: str,
    base_url: str,
    output_dir: Path,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    concurrency: int = 8,
    timeout_s: float = 1200.0,
) -> dict:
    """로컬 furiosa-llm 서버에 SWE-bench 인스턴스를 보내 patch 예측 생성.

    결과 jsonl: harness가 요구하는 {instance_id, model_name_or_path, model_patch}
    + 분석용 {full_output, error, prompt_chars, gen_s, output_tokens}.
    """
    from openai import OpenAI
    from swebench.inference.make_datasets.utils import extract_diff

    output_dir.mkdir(parents=True, exist_ok=True)
    safe = model_name.replace("/", "__")
    out_file = output_dir / f"{safe}__preds.jsonl"

    client = OpenAI(base_url=base_url, api_key="dummy", timeout=timeout_s)

    def one(inst: dict) -> dict:
        rec = {
            "instance_id": inst["instance_id"],
            "model_name_or_path": model_name,
            "prompt_chars": len(inst["text"]),
        }
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": inst["text"]},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            completion = resp.choices[0].message.content or ""
            rec["gen_s"] = round(time.perf_counter() - t0, 2)
            rec["output_tokens"] = getattr(
                getattr(resp, "usage", None), "completion_tokens", None)
            rec["full_output"] = completion
            rec["model_patch"] = extract_diff(completion) or ""
        except Exception as e:
            rec["gen_s"] = round(time.perf_counter() - t0, 2)
            rec["full_output"] = ""
            rec["model_patch"] = ""
            rec["error"] = f"{type(e).__name__}: {e}"
        return rec

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(one, inst) for inst in instances]
        for n, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if n % 10 == 0:
                print(f"    [swebench] {n}/{len(instances)} predicted")

    results.sort(key=lambda r: r["instance_id"])
    with open(out_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    gens = [r["gen_s"] for r in results if "error" not in r]
    summary = {
        "model": model_name,
        "dataset": "oracle-subset",
        "n_instances": len(results),
        "n_nonempty_patch": sum(1 for r in results if r["model_patch"].strip()),
        "n_error": sum(1 for r in results if "error" in r),
        "gen_s_p50": round(statistics.median(gens), 1) if gens else None,
        "gen_s_p95": round(sorted(gens)[max(0, int(0.95 * (len(gens) - 1)))], 1)
        if gens else None,
        "preds_file": str(out_file),
    }
    return summary


def run_evaluation(
    predictions_path: Path,
    run_id: str,
    instance_ids: Optional[list[str]] = None,
    dataset_name: str = EVAL_DATASET,
    max_workers: int = 8,
    namespace: str = "swebench",
    cache_level: str = "env",
    report_dir: Optional[Path] = None,
) -> dict:
    """Docker harness로 예측을 실제 테스트와 함께 실행 → resolved/unresolved 산출.

    namespace=swebench → Docker Hub의 prebuilt instance 이미지를 pull (빌드 최소화).
    harness는 report를 `<model_safe>.<run_id>.json` 형태로 report_dir에 쓴다.
    """
    report_dir = report_dir or predictions_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python", "-m", "swebench.harness.run_evaluation",
        "--dataset_name", dataset_name,
        "--predictions_path", str(predictions_path),
        "--max_workers", str(max_workers),
        "--namespace", namespace,
        "--cache_level", cache_level,
        "--report_dir", str(report_dir),
        "--run_id", run_id,
    ]
    if instance_ids:
        cmd += ["--instance_ids", *instance_ids]
    proc = subprocess.run(cmd, cwd=str(report_dir))

    # harness가 쓴 리포트 파일 탐색 (이름: <model_safe>.<run_id>.json)
    report = None
    for p in report_dir.glob(f"*{run_id}.json"):
        try:
            report = json.loads(p.read_text())
            report["_report_file"] = str(p)
            break
        except Exception:
            pass
    return {
        "run_id": run_id,
        "returncode": proc.returncode,
        "report": report,
    }
