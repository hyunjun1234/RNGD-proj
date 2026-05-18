#!/usr/bin/env bash
# 전체 벤치마크 파이프라인 실행 (preflight → smoke → main → analyze).
# 단계별로 STAGE 환경변수로 일부만 실행 가능: STAGE=smoke ./run_all.sh
set -euo pipefail

cd "$(dirname "$0")"

CONFIG=${CONFIG:-configs/models.yaml}
STAGE=${STAGE:-all}
LOG_DIR=results/_run_logs
mkdir -p "$LOG_DIR"

ts() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG_DIR/run_all.log"; }

step_preflight() {
    log "=== preflight ==="
    bash preflight.sh 2>&1 | tee "$LOG_DIR/preflight.log" || {
        log "preflight failed"; exit 1;
    }
}

step_smoke() {
    log "=== smoke (Qwen2.5-0.5B, tps only) ==="
    python orchestrator.py "$CONFIG" \
        --tasks tps \
        --models Qwen2.5-0.5B 2>&1 | tee "$LOG_DIR/smoke.log"
}

step_gen() {
    # 생성 모델: tps + sweep + memsweep 순서로
    log "=== gen models: tps + sweep + memsweep ==="
    python orchestrator.py "$CONFIG" \
        --tasks tps,sweep,memsweep 2>&1 | tee "$LOG_DIR/gen.log"
}

step_swebench() {
    # Docker 필요. swebench 패키지 설치 확인.
    log "=== SWE-bench (Lite) — gen models ==="
    if ! command -v docker >/dev/null 2>&1; then
        log "docker missing — skipping swebench"
        return
    fi
    python -c "import swebench" 2>/dev/null || pip install swebench
    python orchestrator.py "$CONFIG" \
        --tasks swebench 2>&1 | tee "$LOG_DIR/swebench.log"

    # 예측 jsonl이 results/<model>/swebench/preds/ 안에 생성됨.
    # 평가는 별도 스크립트(eval_swebench.sh)로 모델별 일괄 실행.
    bash eval_swebench.sh 2>&1 | tee "$LOG_DIR/swebench_eval.log" || true
}

step_embed() {
    log "=== embedding + reranker throughput ==="
    python orchestrator.py "$CONFIG" \
        --tasks embed,rerank 2>&1 | tee "$LOG_DIR/embed.log"
}

step_report() {
    log "=== aggregate + report ==="
    python analyze.py --csv "$LOG_DIR/summary.csv" 2>&1 | tee "$LOG_DIR/analyze.log"
    python report.py 2>&1 | tee "$LOG_DIR/report.log" || true
}

case "$STAGE" in
    preflight) step_preflight ;;
    smoke)     step_preflight; step_smoke ;;
    gen)       step_preflight; step_smoke; step_gen ;;
    embed)     step_embed ;;
    swebench)  step_swebench ;;
    report)    step_report ;;
    all)
        step_preflight
        step_smoke
        step_gen
        step_embed
        step_swebench
        step_report
        ;;
    *) echo "unknown STAGE=$STAGE (valid: preflight|smoke|gen|embed|swebench|report|all)"; exit 1 ;;
esac

log "done."
