#!/usr/bin/env bash
# RNGD NPU Chat (gradio) 서버측 기동 헬퍼.
#   ./run.sh start        # 7860에 detached 기동(세션 종료해도 유지) → 맥북에서 alpacon tunnel 로 접속
#   ./run.sh stop         # UI 만 종료 (백엔드 serve 는 남겨 둠 — 아래 설명)
#   ./run.sh stop --all   # UI + 이 UI 가 띄운 백엔드 serve 까지 종료 (NPU 카드 반납)
#                         #   (-all · -a · all 도 같은 뜻. 모르는 옵션은 아무것도 안 하고 에러를 낸다)
#   ./run.sh status       # UI·백엔드·라우터·카드 점유를 한 번에 표시
#   ./run.sh restart      # 재기동 (백엔드는 유지 → 모델 재로딩 없이 그대로 붙는다)
#
# ⚠️ `stop` 이 백엔드를 안 죽이는 건 의도된 동작입니다.
#    chat_app.py 는 `furiosa-llm serve` 를 start_new_session=True 로 분리 기동합니다. 그래서
#    UI 를 껐다 켜도 이미 올라간 모델에 그대로 다시 붙습니다(_discover). 모델 로딩이 수십 분
#    걸리기 때문에(262K 컨텍스트 pp2 는 50분 넘긴 적도 있음) 기본값을 '살려 두기'로 둔 것입니다.
#    카드를 비우고 싶을 때만 `stop --all` 을 쓰세요.
#
# ⚠️ furio 코딩에이전트 라우터(coding-agent/furiosa_router.py, :8400)는 **별개 서비스**입니다.
#    이 스크립트는 건드리지 않습니다(팀원들이 쓰고 있을 수 있음). 내리려면:
#        bash ~/RNGD-proj/Model_Benchmark/rngd-npu/coding-agent/serve-router.sh stop
#    라우터와 chat UI 를 동시에 켜 두면 **둘 다 같은 카드 4장을 스케줄링해 충돌할 수 있습니다** —
#    chat_app 은 자기 CATALOG 포트의 백엔드만 카드 점유로 인식하므로 라우터 백엔드(:8410+)가
#    쓰는 카드를 못 봅니다. 한쪽만 켜 두는 것을 권합니다(status 가 경고를 띄웁니다).
#
# 접속(개인 맥북 터미널):
#   alpacon tunnel furiosa-npu-e6ec40 -l 7860 -r 7860   → 브라우저 http://127.0.0.1:7860
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${CHAT_PORT:-7860}"
PY="$HERE/.venv/bin/python"
APP="$HERE/chat_app.py"
LOG="$HERE/gradio.log"
PIDF="$HERE/.gradio.pid"
ROUTER_STOP="$(cd "$HERE/../coding-agent" 2>/dev/null && pwd)/serve-router.sh"

port_pid() { ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | head -1; }
# 이 UI 가 띄운 백엔드 = CHAT_ARTIFACTS 아티팩트나 furiosa-ai/* 를 서빙하는 furiosa-llm serve.
# (라우터 백엔드와 구분하려고 --served-model-name 이 붙은 것은 제외 — 라우터만 그 옵션을 쓴다.)
#
# ⚠️ pgrep -f 는 명령줄 "문자열"만 본다. 그래서 `furiosa-llm serve` 라는 글자가 들어간 셸 명령
#    (이 스크립트를 부른 셸, 그 문자열을 인자로 가진 다른 명령 등)까지 잡아서 **자기 자신을
#    죽이는** 사고가 난다(2026-08-04 실제로 발생). 진짜 백엔드는 python 인터프리터로 뜨므로
#    실행 파일($2)이 python/furiosa-llm 인 것만 남기고, 자기 PID 도 제외한다.
backend_pids() {
  pgrep -af 'furiosa-llm[ ]serve' 2>/dev/null \
    | awk '$2 ~ /(python|furiosa-llm)/ { print }' \
    | grep -v -- '--served-model-name' \
    | awk -v self="$$" '$1 != self { print $1 }'
}
router_pid() { pgrep -f 'furiosa_router[.]py serve' 2>/dev/null | head -1; }

start() {
  local p; p="$(port_pid)"
  if [ -n "$p" ]; then echo "이미 실행 중 (PID $p, 포트 $PORT). 먼저 ./run.sh stop"; return 1; fi
  if [ -n "$(router_pid)" ]; then
    echo "⚠️  furio 라우터(:8400)가 떠 있습니다 — 라우터와 chat UI 는 같은 카드 4장을 두고 충돌할 수 있습니다."
    echo "    라우터를 내리려면: bash $ROUTER_STOP stop"
  fi
  CHAT_PORT="$PORT" setsid "$PY" "$APP" > "$LOG" 2>&1 &
  # setsid 래퍼가 아닌 실제 리스너 PID 를 잡는다
  for _ in $(seq 1 40); do
    sleep 1; p="$(port_pid)"; [ -n "$p" ] && break
  done
  if [ -n "$p" ]; then echo "$p" > "$PIDF"; echo "기동됨 (PID $p, 포트 $PORT). 로그: $LOG";
    echo "맥북에서: alpacon tunnel furiosa-npu-e6ec40 -l $PORT -r $PORT  → http://127.0.0.1:$PORT";
  else echo "기동 실패 — 로그 확인: $LOG"; tail -n 20 "$LOG"; return 1; fi
}

stop_ui() {
  local p; p="$(port_pid)"; [ -z "$p" ] && p="$(cat "$PIDF" 2>/dev/null)"
  if [ -z "$p" ]; then echo "UI: 실행 중인 인스턴스 없음 (포트 $PORT)"; rm -f "$PIDF"; return 0; fi
  kill "$p" 2>/dev/null; sleep 2
  if kill -0 "$p" 2>/dev/null; then kill -9 "$p" 2>/dev/null; sleep 1; fi
  rm -f "$PIDF"; echo "UI 종료됨 (PID $p)"
}

stop_backends() {
  local pids; pids="$(backend_pids)"
  if [ -z "$pids" ]; then echo "백엔드: 실행 중인 serve 없음"; return 0; fi
  echo "백엔드 종료 중: $(echo "$pids" | tr '\n' ' ')"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null
  for _ in $(seq 1 30); do
    sleep 1; [ -z "$(backend_pids)" ] && break
  done
  pids="$(backend_pids)"
  if [ -n "$pids" ]; then
    echo "  응답 없어 강제 종료: $(echo "$pids" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null; sleep 2
  fi
  echo "백엔드 종료 완료 (NPU 카드 반납까지 몇 초 걸릴 수 있음)"
}

stop() {
  # 옵션은 UI 를 죽이기 **전에** 검증한다 — 오타 하나로 "UI 만 꺼지고 백엔드는 남는" 절반 실행이
  # 되면 사용자는 다 정리된 줄 안다. 실제로 `-all`(하이픈 1개)이 조용히 무시된 사고가 있었다.
  local all=0
  case "${1:-}" in
    "")               ;;
    --all|-all|-a|all) all=1 ;;
    *) echo "✗ 모르는 옵션: $1"; echo "   사용법: $0 stop [--all]   (--all = 백엔드 serve 까지 종료)"; return 1 ;;
  esac
  stop_ui
  if [ "$all" = 1 ]; then
    stop_backends
    local r; r="$(router_pid)"
    [ -n "$r" ] && echo "ℹ️  furio 라우터(PID $r)는 별개 서비스라 그대로 뒀습니다. 내리려면: bash $ROUTER_STOP stop"
  else
    local pids; pids="$(backend_pids)"
    if [ -n "$pids" ]; then
      echo "ℹ️  백엔드 serve $(echo "$pids" | wc -l)개가 살아 있습니다(의도된 동작 — 다시 켜면 재로딩 없이 붙습니다)."
      echo "    카드까지 비우려면: ./run.sh stop --all"
    fi
  fi
}

status() {
  local p r pids
  p="$(port_pid)"
  if [ -n "$p" ]; then echo "UI      : 실행 중 (PID $p, 포트 $PORT — http://127.0.0.1:$PORT)";
  else echo "UI      : 꺼짐 (포트 $PORT)"; fi

  pids="$(backend_pids)"
  if [ -n "$pids" ]; then
    echo "백엔드  : $(echo "$pids" | wc -l)개"
    pgrep -af 'furiosa-llm[ ]serve' 2>/dev/null | grep -v -- '--served-model-name' \
      | sed -E 's#.*serve ([^ ]+).*--devices ([^ ]+).*--port ([0-9]+).*#          \3  \2  \1#' \
      | sed 's#/mnt/nvme2n1p1/models/artifacts/##'
  else
    echo "백엔드  : 없음"
  fi

  r="$(router_pid)"
  if [ -n "$r" ]; then
    echo "라우터  : 실행 중 (PID $r, :8400) — 별개 서비스. 내리려면 bash $ROUTER_STOP stop"
    [ -n "$p" ] && echo "          ⚠️ chat UI 와 동시 실행 중 — 같은 카드 4장을 두고 충돌할 수 있습니다."
  else
    echo "라우터  : 꺼짐"
  fi

  if command -v furiosa-smi >/dev/null 2>&1; then
    echo "NPU     : $(furiosa-smi status 2>/dev/null | grep -oE '[0-9.]+/[0-9.]+ GiB' | tr '\n' ' ')"
  fi
}

case "${1:-status}" in
  start) start ;;
  stop) stop "${2:-}" ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  *) echo "사용법: $0 {start|stop [--all]|restart|status}"; exit 1 ;;
esac
