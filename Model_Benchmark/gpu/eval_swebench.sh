#!/usr/bin/env bash
# SWE-bench Docker 채점 — orchestrator의 swebench 태스크가 만든 예측 jsonl을 일괄 채점.
# 추론(orchestrator)은 GPU 필요, 이 단계는 Docker만 필요.
set -uo pipefail
cd "$(dirname "$0")"
[ -d .venv ] && source .venv/bin/activate

MAX_WORKERS=${MAX_WORKERS:-8}
command -v docker >/dev/null 2>&1 || { echo "docker 없음 — 설치 필요"; exit 1; }
python swebench_eval.py --max-workers "$MAX_WORKERS" "$@"
