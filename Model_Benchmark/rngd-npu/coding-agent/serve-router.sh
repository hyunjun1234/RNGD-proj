#!/usr/bin/env bash
# Furiosa NPU lazy-serving 라우터 기동/종료 (OpenCode 용)
# ---------------------------------------------------------------------------
# rngd-npu/artifacts 의 모든 모델을 OpenAI 호환 엔드포인트 1개(:8400)로 노출.
# OpenCode 모델 선택창(switch model)에서 고르면 첫 요청 때 올바른 옵션으로 자동 서빙.
# 카드(4장)가 모자라면 LRU 백엔드를 내려서 교체한다.
#
#   bash serve-router.sh [start]   # 라우터 기동(+ opencode.json 자동 갱신)
#   bash serve-router.sh stop      # 라우터 + 모든 백엔드 serve 종료
# ---------------------------------------------------------------------------
set -euo pipefail
HERE=~/RNGD-proj/Model_Benchmark/rngd-npu/coding-agent
LOG=~/RNGD-proj/Model_Benchmark/rngd-npu/chat/serve_logs/router.log
PIDFILE="$HERE/.router.pid"
source ~/furiosa/bin/activate 2>/dev/null || true

stop_router() {
  if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null && echo "  router stopped (pid $(cat "$PIDFILE"))" || true
    rm -f "$PIDFILE"
  fi
  # PIDFILE 이 없거나(옛 버전이 안 남겼거나) 다른 방식으로 뜬 라우터도 확실히 정리한다.
  # char-class 로 pkill 자신·이 스크립트와 self-match 회피(cmdline 은 'bash serve-router.sh').
  pkill -f 'furiosa_router[.]py serve' 2>/dev/null && echo "  router (pattern) stopped" || true
}

if [ "${1:-start}" = "stop" ]; then
  stop_router
  # 백엔드 serve 정리. char-class 정규식으로 이 스크립트 자신과 self-match 회피.
  pkill -f 'furiosa-llm[ ]serve' 2>/dev/null && echo "  backends stopped" || true
  echo "종료 완료"; exit 0
fi

# ── 자동 최신화 ─────────────────────────────────────────────────────────────
# 서버 체크아웃이 옛 브랜치(예: add-extra-models)에 있어도, start 때 origin/main 의 라우터
# 파일만 덮어써 항상 최신 코드로 뜬다(다른 uncommitted 작업은 안 건드림 — furiosa_router.py 만).
# → PR 을 main 에 머지하기만 하면 다음 serve-router.sh start 에서 자동 반영. 끄려면 FURIO_NO_AUTOUPDATE=1.
# (serve-router.sh 자신은 실행 중 덮어쓰면 위험해서 안 건드림 — 이 블록은 최초 1회 수동 반영이 필요하다.)
if [ "${FURIO_NO_AUTOUPDATE:-0}" != "1" ]; then
  RFILE="Model_Benchmark/rngd-npu/coding-agent/furiosa_router.py"
  if git -C ~/RNGD-proj rev-parse --git-dir >/dev/null 2>&1 && git -C ~/RNGD-proj fetch origin >/dev/null 2>&1; then
    git -C ~/RNGD-proj checkout origin/main -- "$RFILE" 2>/dev/null \
      && echo "[auto-update] furiosa_router.py ← origin/main" \
      || echo "[auto-update] 건너뜀(로컬 변경/충돌) — 필요시 git checkout origin/main -- $RFILE"
  fi
fi

echo "[..] 기존 라우터/serve 정리(라우터가 NPU 4장 전체를 스케줄링)"
stop_router
pkill -f 'furiosa-llm[ ]serve' 2>/dev/null || true
sleep 3

echo "[..] opencode.json 갱신(전 모델 등록 → 라우터 :8400)"
python3 "$HERE/furiosa_router.py" gen-config "$HERE/opencode/opencode.json"

echo "[..] 라우터 기동 → :8400  (로그 $LOG)"
mkdir -p "$(dirname "$LOG")"
: > "$LOG"
nohup python3 "$HERE/furiosa_router.py" serve >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"   # 다음 stop/start 가 이 라우터를 정확히 종료할 수 있게 pid 기록
sleep 1
if [ -n "${SDI_API_KEY:-}" ]; then
  echo "[ok] 🔒 인증 ON — 사용자는 이 키(SDI_API_KEY)로 접속해야 합니다."
else
  echo "[ok] 🔓 인증 OFF — 사용자는 키 없이 접속 가능(승인된 사내망 전용)."
  echo "         키를 요구하려면:  SDI_API_KEY=<키> bash serve-router.sh start"
fi
echo "[ok] 모델 목록:  curl -s localhost:8400/v1/models | python3 -m json.tool"
echo "     라우터 상태: curl -s localhost:8400/router/status | python3 -m json.tool"
