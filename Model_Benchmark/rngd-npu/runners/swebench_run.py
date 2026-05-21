"""SWE-bench inference + evaluation 래퍼 (Furiosa RNGD NPU).

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
  SWEBENCH_MAXTOK   - 응답 max_tokens (default 1024)
  SWEBENCH_CONC     - 동시 요청 수 (default 8)
  SWEBENCH_FILTER_CONTEXT - 서버 context를 넘는 인스턴스 사전 제외 (default 1)
  SWEBENCH_MAX_INPUT_TOKENS - 입력 토큰 상한 override (기본: server max_model_len - max_tokens)
  SWEBENCH_DROP_INVALID_PATCH - 형식상 깨진 diff를 빈 패치로 저장 (default 0)
  SWEBENCH_RETRY_INVALID - 형식상 깨진 diff 재생성 횟수 (default 0, single-shot 유지)
"""
from __future__ import annotations

import json
import math
import os
import re
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
    "the relevant part of a code base. Produce one valid unified diff patch that "
    "resolves the issue. Output only the patch, with no explanation. Start with "
    "diff --git. Use exact file paths from the provided repository context. Do not "
    "use placeholder paths such as some_file.py. Every hunk must include a valid @@ "
    "header and every changed/context line must begin with space, +, or -. Do not "
    "wrap the patch in markdown fences."
)


def _server_max_model_len(base_url: str) -> int | None:
    """OpenAI-compatible /models에서 furiosa-llm이 실제로 쓰는 max_model_len을 읽는다."""
    try:
        import httpx

        resp = httpx.get(f"{base_url.rstrip('/')}/models", timeout=10.0)
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            value = item.get("max_model_len") or item.get("max_seq_len")
            if value:
                return int(value)
    except Exception:
        return None
    return None


def _load_tokenizer(model_name: str):
    try:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    except Exception:
        return None


def _count_prompt_tokens(tokenizer, text: str) -> int:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    if tokenizer is not None:
        try:
            ids = tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True
            )
            return len(ids)
        except Exception:
            try:
                serialized = f"{SYSTEM_PROMPT}\n\n{text}"
                return len(tokenizer(serialized, add_special_tokens=True)["input_ids"])
            except Exception:
                pass
    # tokenizer를 못 읽는 환경에서도 over-context 요청을 줄이기 위한 보수적 추정.
    return math.ceil((len(SYSTEM_PROMPT) + len(text)) / 3.0)


def _filter_by_context(
    instances: list[dict],
    model_name: str,
    base_url: str,
    max_tokens: int,
    filter_context: bool,
    max_input_tokens: int | None,
    context_margin_tokens: int = 0,
) -> tuple[list[dict], list[dict], int | None, int | None, dict[str, int]]:
    server_limit = _server_max_model_len(base_url)
    if max_input_tokens is None and server_limit:
        max_input_tokens = max(0, server_limit - max_tokens - context_margin_tokens)
    elif max_input_tokens is not None and context_margin_tokens:
        max_input_tokens = max(0, max_input_tokens - context_margin_tokens)
    if not filter_context or not max_input_tokens:
        return instances, [], server_limit, max_input_tokens, {}

    tokenizer = _load_tokenizer(model_name)
    kept: list[dict] = []
    filtered: list[dict] = []
    prompt_tokens: dict[str, int] = {}
    for inst in instances:
        tokens = _count_prompt_tokens(tokenizer, inst["text"])
        iid = inst["instance_id"]
        prompt_tokens[iid] = tokens
        if tokens <= max_input_tokens:
            kept.append(inst)
        else:
            filtered.append({
                "instance_id": iid,
                "prompt_tokens": tokens,
                "max_input_tokens": max_input_tokens,
                "requested_tokens": tokens + max_tokens,
                "max_model_len": server_limit,
            })
    return kept, filtered, server_limit, max_input_tokens, prompt_tokens


def _parse_hunk_count(raw: str | None) -> int:
    return 1 if raw in (None, "") else int(raw)


def _patch_sanity_error(patch: str) -> str | None:
    """Unified diff 구조 검사. GNU patch가 허용하는 빈 context line은 허용한다."""
    text = patch.strip("\n")
    if not text:
        return "empty"
    lines = text.splitlines()
    if not any(line.startswith("--- ") for line in lines):
        return "missing --- file header"
    if not any(line.startswith("+++ ") for line in lines):
        return "missing +++ file header"
    if not any(line.startswith("@@ ") for line in lines):
        return "missing @@ hunk"

    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    in_hunk = False
    expected_old = expected_new = 0
    seen_old = seen_new = 0

    def finish_hunk() -> str | None:
        if not in_hunk:
            return None
        if seen_old != expected_old or seen_new != expected_new:
            return (
                "hunk line count mismatch "
                f"old={seen_old}/{expected_old} new={seen_new}/{expected_new}"
            )
        return None

    for line in lines:
        if line.startswith("@@ "):
            err = finish_hunk()
            if err:
                return err
            m = hunk_re.match(line)
            if not m:
                return "bad @@ hunk header"
            expected_old = _parse_hunk_count(m.group(2))
            expected_new = _parse_hunk_count(m.group(4))
            seen_old = seen_new = 0
            in_hunk = True
            continue

        if line.startswith("diff --git ") or line.startswith("--- ") or line.startswith("+++ "):
            err = finish_hunk()
            if err:
                return err
            in_hunk = False
            continue

        if not in_hunk:
            continue
        if line.startswith("\\ No newline at end of file"):
            continue

        prefix = line[:1]
        if prefix == "-":
            seen_old += 1
        elif prefix == "+":
            seen_new += 1
        elif prefix == " " or line == "":
            seen_old += 1
            seen_new += 1
        else:
            return "bad hunk line prefix"

    return finish_hunk()


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
    filter_context: bool = True,
    max_input_tokens: int | None = None,
    drop_invalid_patch: bool = False,
    retry_invalid: int = 0,
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

    requested_instances = len(instances)
    instances, filtered_context, server_max_model_len, max_input_tokens, prompt_tokens = (
        _filter_by_context(
            instances, model_name, base_url, max_tokens, filter_context, max_input_tokens,
            context_margin_tokens=256 if retry_invalid > 0 else 0,
        )
    )
    if filtered_context:
        print(
            f"    [swebench] context-filtered {len(filtered_context)}/{requested_instances} "
            f"(max_input_tokens={max_input_tokens}, max_model_len={server_max_model_len})"
        )

    client = OpenAI(base_url=base_url, api_key="dummy", timeout=timeout_s)

    def one(inst: dict) -> dict:
        rec = {
            "instance_id": inst["instance_id"],
            "model_name_or_path": model_name,
            "prompt_chars": len(inst["text"]),
            "prompt_tokens": prompt_tokens.get(inst["instance_id"]),
        }
        t0 = time.perf_counter()
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": inst["text"]},
            ]
            attempts: list[dict] = []
            for attempt in range(max(0, retry_invalid) + 1):
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                completion = resp.choices[0].message.content or ""
                patch = extract_diff(completion) or ""
                sanity_error = _patch_sanity_error(patch)
                attempts.append({"attempt": attempt + 1, "patch_sanity_error": sanity_error})
                rec["output_tokens"] = getattr(
                    getattr(resp, "usage", None), "completion_tokens", None)
                rec["full_output"] = completion
                rec["model_patch"] = patch
                if not sanity_error or attempt >= max(0, retry_invalid):
                    break
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"{inst['text']}\n\n"
                            "The previous answer was not a valid unified diff "
                            f"because: {sanity_error}. Regenerate only one complete "
                            "unified diff patch. No markdown fences, no explanation."
                        ),
                    },
                ]
            rec["gen_s"] = round(time.perf_counter() - t0, 2)
            if len(attempts) > 1:
                rec["retry_attempts"] = attempts
            sanity_error = _patch_sanity_error(rec["model_patch"])
            if sanity_error:
                rec["patch_sanity_error"] = sanity_error
                if drop_invalid_patch and sanity_error != "empty":
                    rec["raw_model_patch"] = rec["model_patch"]
                    rec["model_patch"] = ""
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
        "n_requested_instances": requested_instances,
        "n_instances": len(results),
        "n_filtered_context": len(filtered_context),
        "filtered_context_ids": [r["instance_id"] for r in filtered_context],
        "filtered_context": filtered_context,
        "max_model_len": server_max_model_len,
        "max_input_tokens": max_input_tokens,
        "max_tokens": max_tokens,
        "n_nonempty_patch": sum(1 for r in results if r["model_patch"].strip()),
        "n_error": sum(1 for r in results if "error" in r),
        "n_invalid_patch": sum(
            1 for r in results
            if r.get("patch_sanity_error") and r.get("patch_sanity_error") != "empty"
        ),
        "invalid_patch_examples": [
            {"instance_id": r["instance_id"], "reason": r.get("patch_sanity_error")}
            for r in results
            if r.get("patch_sanity_error") and r.get("patch_sanity_error") != "empty"
        ][:10],
        "instance_ids": [r["instance_id"] for r in results],
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
