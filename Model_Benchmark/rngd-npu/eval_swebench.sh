#!/usr/bin/env bash
# SWE-bench Docker 채점. orchestrator의 swebench 태스크가 만든 예측 jsonl을
# swebench_eval.py로 일괄 채점한다 (harness가 prebuilt 이미지를 pull).
# inference는 NPU 서버가 필요하지만 이 단계는 Docker만 필요.
set -uo pipefail
cd "$(dirname "$0")"

MAX_WORKERS=${MAX_WORKERS:-8}

if ! command -v docker >/dev/null 2>&1; then
    echo "docker missing"; exit 1
fi

python swebench_eval.py --max-workers "$MAX_WORKERS" "$@"
