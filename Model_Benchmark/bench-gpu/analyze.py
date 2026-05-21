"""results/ 아래의 JSON들을 모아 모델/조건별 비교표 생성.

사용:
    python analyze.py                        # results/ 전체 스캔, 표 출력
    python analyze.py --csv out.csv          # csv로 저장
    python analyze.py --task sweep           # task 필터
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = REPO_ROOT / "results"


def collect():
    rows = []
    for model_dir in RESULTS_ROOT.iterdir():
        if not model_dir.is_dir() or model_dir.name.startswith("_"):
            continue
        for task_dir in model_dir.iterdir():
            if not task_dir.is_dir():
                continue
            task = task_dir.name
            for f in sorted(task_dir.glob("*.json")):
                try:
                    obj = json.loads(f.read_text())
                except Exception:
                    continue
                if task == "sweep" and isinstance(obj, dict):
                    for s in obj.get("sweep", []):
                        rows.append({"task": task, "file": str(f), **s})
                elif isinstance(obj, list):
                    for item in obj:
                        if not isinstance(item, dict):
                            continue
                        s = item.get("bench") or item.get("summary") or {}
                        meta = {k: v for k, v in item.items()
                                if k not in {"bench", "summary", "server_info"}}
                        rows.append({"task": task, "file": str(f), **meta, **s})
                elif isinstance(obj, dict):
                    s = obj.get("summary") or {k: obj.get(k) for k in obj.keys()}
                    rows.append({"task": task, "file": str(f), **(s or {})})
    return rows


def to_table(rows, columns):
    # 단순 정렬 + 정렬된 컬럼 출력
    if not rows:
        return "(no data)"
    cols = columns or sorted({k for r in rows for k in r.keys()})
    widths = [max(len(str(c)), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in cols]
    header = " | ".join(f"{c:<{w}}" for c, w in zip(cols, widths))
    sep = "-+-".join("-" * w for w in widths)
    lines = [header, sep]
    for r in rows:
        lines.append(" | ".join(f"{str(r.get(c, '')):<{w}}" for c, w in zip(cols, widths)))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--task", default=None)
    args = ap.parse_args()

    rows = collect()
    if args.task:
        rows = [r for r in rows if r.get("task") == args.task]

    if args.csv:
        cols = sorted({k for r in rows for k in r.keys()})
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})
        print(f"wrote {args.csv} ({len(rows)} rows)")
        return

    interesting = [
        "task", "model", "concurrency", "prompt_tokens_target", "max_tokens",
        "ttft_s_p50", "ttft_s_p95", "itl_s_p50",
        "output_tps_per_request_p50", "aggregate_output_tps",
        "successes", "failures",
    ]
    print(to_table(rows, columns=interesting))


if __name__ == "__main__":
    main()
