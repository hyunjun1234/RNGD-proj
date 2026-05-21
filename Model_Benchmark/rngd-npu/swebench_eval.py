"""SWE-bench Docker 평가 드라이버.

orchestrator의 swebench 태스크(inference, NPU 서버 필요)가 만든 예측 jsonl을 찾아
Docker harness로 채점한다. 이 단계는 Docker만 필요 — NPU 불필요하므로 생성
벤치마크와 분리해서 돌린다 (Docker 빌드 부하가 latency 측정을 오염시키지 않도록).

harness는 --namespace swebench 기본값으로 prebuilt instance 이미지를 pull한다.

사용:
    python swebench_eval.py                   # results/*/swebench/preds/*.jsonl 전부
    python swebench_eval.py --models Llama    # model_safe substring 필터
    python swebench_eval.py --max-workers 12
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from runners.swebench_run import run_evaluation  # noqa: E402

RESULTS = REPO_ROOT / "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=None, help="model_safe substring 필터")
    ap.add_argument("--max-workers", type=int, default=8)
    args = ap.parse_args()

    preds = sorted(RESULTS.glob("*/swebench/preds/*__preds.jsonl"))
    if not preds:
        print("예측 파일 없음. 먼저: python orchestrator.py configs/models.yaml --tasks swebench")
        return

    for pred in preds:
        model_safe = pred.parents[2].name
        if args.models and args.models not in model_safe:
            continue
        ids = []
        for line in pred.read_text().splitlines():
            try:
                ids.append(json.loads(line)["instance_id"])
            except Exception:
                pass
        swebench_dir = pred.parents[1]
        run_id = f"{model_safe}_{dt.datetime.now():%Y%m%d_%H%M%S}"
        print(f"=== eval {model_safe}  ({len(ids)} instances) ===")
        res = run_evaluation(
            predictions_path=pred, run_id=run_id, instance_ids=ids,
            max_workers=args.max_workers, report_dir=swebench_dir,
        )
        out = swebench_dir / "eval_result.json"
        out.write_text(json.dumps(res, indent=2, default=str))
        rep = res.get("report") or {}
        print(f"  resolved {rep.get('resolved_instances', '?')}"
              f"/{rep.get('total_instances', '?')}  -> {out}")


if __name__ == "__main__":
    main()
