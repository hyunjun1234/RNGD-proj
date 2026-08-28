#!/usr/bin/env bash
# RNGD NPU 채팅용 모델 서버 — chat_app.py 의 CATALOG 와 같은 키·포트·파서를 쓴다.
# (chat UI 를 안 띄우고 백엔드만 손으로 올릴 때 쓰는 헬퍼. UI 는 스스로 serve 를 띄운다.)
#
# 2026-08-04 갱신: 옛 카탈로그가 가리키던 rngd-npu/artifacts 는 비어 있어 전부 死경로였다.
# 지금은 실재하는 두 갈래를 쓴다.
#   · 로컬 legacy(v2) tp8 아티팩트 = /mnt/nvme2n1p1/models/artifacts   (2026-07-29 빌드, 8종)
#     tp8 이라 serve 때 `-pp` 로 층을 쪼갤 수 있다 = pp 커스텀 가능.
#   · furiosa-ai 프리빌트 저장소   = HF_HUB_CACHE(/mnt/nvme2n1p1/models/hf/hub)  (15종)
#     대부분 tp32(4장 독점). FXB 번들은 `-pp` 를 런타임이 거부하므로 여기선 안 준다.
#
# 카드 예산(4장): 한 모델이 쓰는 카드 수 = tp32 면 4, tp8 이면 dp×pp.
#   - tp8 모델은 합쳐서 4장까지 동시에
#   - tp32 모델은 1개만(4장 독점)
#
# 사용:
#   ./serve_models.sh                  # 기본 세트(가벼운 tp8 2종)를 빈 카드에 동시 serve
#   ./serve_models.sh 2                # 기본 세트에서 앞 N개만
#   ./serve_models.sh coder qwen3-32b  # 고른 모델만 (빈 카드에 자동 배정)
#   ./serve_models.sh hub-gpt-oss-120b # tp32 프리빌트 1개 (4장 전부)
#   ./serve_models.sh list             # 등록된 모델 키 보기
#   ./serve_models.sh stop             # 전부 종료
#
# 로그: chat/serve_logs/<port>.log  ·  서버 준비되면 "Uvicorn running" 출력됨.
set -u
ART="${CHAT_ARTIFACTS:-/mnt/nvme2n1p1/models/artifacts}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-/mnt/nvme2n1p1/models/hf/hub}"
LOGDIR=~/RNGD-proj/Model_Benchmark/rngd-npu/chat/serve_logs
mkdir -p "$LOGDIR"
# serve 바이너리(venv 가 깨졌을 때 FURIOSA_LLM_BIN 으로 다른 venv 를 쓸 수 있게).
source ~/furiosa/bin/activate 2>/dev/null
FURIOSA_LLM="${FURIOSA_LLM_BIN:-furiosa-llm}"

# 모델 카탈로그:  키 = "포트|카드수|아티팩트|추가 serve 인자"
#   카드수 = 이 구성이 점유할 NPU 카드 수(tp32=4, tp8 은 pp 값).
#   아티팩트 = 로컬 절대경로 또는 furiosa-ai/... HF 저장소 ID(캐시에서 해석, 없으면 다운로드).
#   추가 인자 = 파서 + 필요한 -pp. 파서 근거는 legacy_moe_build/README.md §0.5 와 라우터 REGISTRY.
#
# ⚠️ 2026.3.0 이 받는 tool 파서는 constants.py:TOOL_PARSER_NAMES 에 하드코딩된
#    {hermes, llama3_json, llama4_json, openai, solar_open} 뿐이다(2026-08-04 실측).
#    Qwen3-Coder 전용 qwen3_coder 는 목록에 없어서 주면 serve 가 즉시 죽는다 →
#    coder·coder-bf16·hub-coder 는 파서 없이(채팅 전용) 띄운다.
declare -A CAT=(
  # ── 로컬 tp8 아티팩트 (pp 커스텀 가능) ────────────────────────────────
  # 총 컨텍스트 262144 여도 kv_heads=4 계열은 프롬프트가 65,408 까지만 된다(README §0.8).
  # MoE 위장 제거(2026-08-29) [coder]="8000|2|$ART/coder-tp8|-pp 2"
  # bf16 56.9G — pp2(장당 27.6/29.9 GiB)로 정상 기동 확인(2026-08-04). 4장이 필요하면 -pp 4 로.
  # MoE 위장 제거(2026-08-29) [coder-bf16]="8001|2|$ART/coder-bf16-tp8|-pp 2"
  # MoE 위장 제거(2026-08-29) [a3b-inst-2507]="8002|2|$ART/a3b-inst-2507-tp8|--enable-auto-tool-choice --tool-call-parser hermes -pp 2"
  # MoE 위장 제거(2026-08-29) [a3b-think-2507]="8003|2|$ART/a3b-think-2507-tp8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3 -pp 2"
  # ❌ a3b — 아티팩트 고장으로 비활성(2026-08-04): serve 는 뜨는데 생성이 0 토큰. 재빌드 필요.
  #        위장은 무죄 — 같은 처리를 한 coder·a3b-*-2507 은 정상 생성한다. 상세는 chat_app.py 주석.
  # [a3b]="8004|1|$ART/a3b-tp8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  [qwen3-32b]="8005|1|$ART/qwen3-32b-tp8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  # 가중치 30.8G + KV 256KiB/token — 131072 를 다 쓰면 1장을 넘어 pp2.
  [exaone4]="8006|2|$ART/exaone4-tp8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser exaone4 -pp 2"
  [llama31-8b]="8007|1|$ART/llama31-8b-tp8|--enable-auto-tool-choice --tool-call-parser llama3_json"

  # ── furiosa-ai 프리빌트 (tp32 = 4장 독점) ─────────────────────────────
  [hub-gpt-oss-120b]="8010|4|furiosa-ai/gpt-oss-120b|--enable-auto-tool-choice --tool-call-parser openai"
  [hub-solar-100b]="8011|4|furiosa-ai/Solar-Open-100B-NVFP4A16|--enable-auto-tool-choice --tool-call-parser solar_open --reasoning-parser solar_open"
  [hub-llama-70b]="8012|4|furiosa-ai/Llama-3.3-70B-Instruct|--enable-auto-tool-choice --tool-call-parser llama3_json"
  [hub-qwen3-32b]="8013|4|furiosa-ai/Qwen3-32B-FP8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  [hub-exaone4]="8014|4|furiosa-ai/EXAONE-4.0-32B-FP8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser exaone4"
  [hub-kexaone-236b]="8015|4|furiosa-ai/K-EXAONE-236B-A23B-NVFP4A16|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_v3 --default-chat-template-kwargs {\"enable_thinking\":true}"
  [hub-a3b-inst-2507]="8016|4|furiosa-ai/Qwen3-30B-A3B-Instruct-2507-FP8|--enable-auto-tool-choice --tool-call-parser hermes"
  [hub-a3b-think-2507]="8017|4|furiosa-ai/Qwen3-30B-A3B-Thinking-2507-FP8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  [hub-a3b]="8018|4|furiosa-ai/Qwen3-30B-A3B-FP8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  [hub-coder]="8019|4|furiosa-ai/Qwen3-Coder-30B-A3B-Instruct-FP8|"
  [hub-qwen3-vl-32b]="8020|4|furiosa-ai/Qwen3-VL-32B-Instruct|--enable-auto-tool-choice --tool-call-parser hermes"

  # ── furiosa-ai 프리빌트 중 1장짜리 ────────────────────────────────────
  [hub-llama31-8b]="8021|1|furiosa-ai/Llama-3.1-8B-Instruct|--enable-auto-tool-choice --tool-call-parser llama3_json"
  # Qwen3-8B/4B 는 FXB 번들이라 -pp 를 주면 PanicException 으로 죽는다 — 주지 않는다.
  [hub-qwen3-8b]="8022|1|furiosa-ai/Qwen3-8B-FP8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  [hub-qwen3-4b]="8023|1|furiosa-ai/Qwen3-4B-FP8|--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
  # tp4 — 카드 하나의 앞 4 PE 만 쓴다(아래 PE 목록으로 devices 를 npu:X:0-3 으로 만든다).
  [hub-qwen2.5-0.5b]="8024|1|furiosa-ai/Qwen2.5-0.5B-Instruct|--enable-auto-tool-choice --tool-call-parser hermes"
)
# tp<8 아티팩트 — 카드를 통째로 주면 안 되고 앞 N PE 만 준다.
declare -A PE=( [hub-qwen2.5-0.5b]=4 )

DEFAULT_SET=(llama31-8b qwen3-32b)   # 기본 2종 — 둘 다 tp8·pp1 이라 1장씩 (a3b 는 위 사유로 비활성)

case "${1:-}" in
  stop) pkill -f "furiosa-llm serve" && echo "모든 serve 종료" || echo "실행 중인 serve 없음"; exit 0 ;;
  list)
    echo "등록된 모델 키 (포트 / 카드 / 아티팩트):"
    for k in "${!CAT[@]}"; do
      IFS='|' read -r P C A _ <<< "${CAT[$k]}"
      printf "  %-20s :%s  %s장  %s\n" "$k" "$P" "$C" "$(basename "$A")"
    done | sort
    echo "기본 세트: ${DEFAULT_SET[*]}"
    exit 0 ;;
esac

# 띄울 모델 목록 결정: 인자 없으면 기본 세트, 숫자면 기본 세트의 앞 N개, 그 외엔 키 목록.
if [ "$#" -eq 0 ]; then
  SEL=("${DEFAULT_SET[@]}")
elif [[ "$1" =~ ^[0-9]+$ ]]; then
  SEL=("${DEFAULT_SET[@]:0:$1}")
else
  SEL=("$@")
fi

# 키 유효성 + 카드 예산 검사(요청한 것들의 카드 합이 4장을 넘으면 거절).
TOTAL=0
for k in "${SEL[@]}"; do
  [ -n "${CAT[$k]:-}" ] || { echo "✗ 모르는 모델 키: $k   (./serve_models.sh list 로 확인)"; exit 1; }
  IFS='|' read -r _ C _ _ <<< "${CAT[$k]}"
  TOTAL=$((TOTAL + C))
done
if [ "$TOTAL" -gt 4 ]; then
  echo "✗ 카드가 4장뿐인데 요청한 구성은 ${TOTAL}장입니다. 줄여서 지정하세요."
  echo "  (tp32 프리빌트는 4장을 독점하므로 단독으로만 띄울 수 있습니다.)"
  exit 1
fi

# 빈 카드 풀에서 필요한 장수만큼 순서대로 배정.
# ⚠️ 이미 떠 있는 serve 가 쓰는 카드는 빼야 한다. 예전엔 무조건 (0 1 2 3) 에서 시작해서,
#    이 스크립트를 두 번 나눠 호출하면 두 번째가 첫 번째와 같은 카드를 골라 충돌했다.
#    실행 중인 프로세스의 --devices 를 읽어 실제 점유를 반영한다(chat_app.py 의 _discover 와 같은 방식).
#    npu:0 · npu:0:0-3 둘 다 카드 번호만 뽑는다.
HELD="$(pgrep -af 'furiosa-llm[ ]serve' 2>/dev/null \
        | grep -oP -- '--devices\s+\K\S+' \
        | tr ',' '\n' | sed -n 's/^npu:\([0-9][0-9]*\).*/\1/p' | sort -u | tr '\n' ' ')"
FREE=()
for c in 0 1 2 3; do
  case " $HELD " in *" $c "*) ;; *) FREE+=("$c") ;; esac
done
if [ -n "${HELD// /}" ]; then
  echo "ℹ️  이미 쓰는 카드: ${HELD}  →  남은 카드: ${FREE[*]:-없음}"
  echo
fi
for k in "${SEL[@]}"; do
  IFS='|' read -r PORT CARDS A EXTRA <<< "${CAT[$k]}"
  # 로컬 아티팩트만 미리 확인한다. 프리빌트는 저장소 ID 라 파일이 아니고, 없으면 serve 가 받아온다.
  case "$A" in
    /*) [ -f "$A/artifact.json" ] || { echo "⏭  skip $k — artifact 없음: $A"; continue; } ;;
  esac
  if pgrep -f "furiosa-llm serve.*--port $PORT" >/dev/null 2>&1; then echo "✔  $k 포트 $PORT 이미 실행 중"; continue; fi
  if [ "${#FREE[@]}" -lt "$CARDS" ]; then echo "✗ 빈 카드 ${CARDS}장 필요 — $k 건너뜀 (남은 ${#FREE[@]}장)"; continue; fi
  pe="${PE[$k]:-8}"
  if [ "$pe" -lt 8 ]; then
    DEV="npu:${FREE[0]}:0-$((pe - 1))"
  else
    DEV=""
    for c in "${FREE[@]:0:$CARDS}"; do DEV="${DEV:+$DEV,}npu:$c"; done
  fi
  FREE=("${FREE[@]:$CARDS}")
  echo "▶  $k ($DEV) → :$PORT   $(basename "$A")"
  # shellcheck disable=SC2086  # EXTRA 는 여러 인자로 쪼개져야 한다
  nohup "$FURIOSA_LLM" serve "$A" --devices "$DEV" --host 0.0.0.0 --port "$PORT" \
        --enable-prefix-caching $EXTRA > "$LOGDIR/$PORT.log" 2>&1 &
done

echo
echo "준비 확인:  tail -f $LOGDIR/<port>.log  →  'Uvicorn running' 뜨면 OK"
echo "채팅 UI:    cd ~/RNGD-proj/Model_Benchmark/rngd-npu/chat && ./run.sh start"
