#!/usr/bin/env bash
# Furiosa RNGD 벤치마크 추가 의존성 설치.
# 전제: ~/furiosa 가상환경에 furiosa-llm SDK가 이미 설치돼 있음 (Furiosa 공식 설치 가이드 참조).
# 본 스크립트는 그 위에 측정용 클라이언트 의존성(httpx/openai/datasets/swebench 등)만 추가한다.
set -uo pipefail
cd "$(dirname "$0")"

echo "=== 1. NPU / SDK 확인 ==="
command -v furiosa-smi >/dev/null 2>&1 && furiosa-smi info 2>/dev/null | head -5 \
  || echo "  !! furiosa-smi 없음 — 드라이버/SDK 설치 후 재시도"
command -v furiosa-llm >/dev/null 2>&1 || echo "  !! furiosa-llm 없음 — Furiosa SDK 설치 필요"
echo

echo "=== 2. furiosa venv 활성화 ==="
if [ -f ~/furiosa/bin/activate ]; then
  source ~/furiosa/bin/activate
  echo "  ok — ~/furiosa 활성화"
else
  echo "  !! ~/furiosa 가상환경 없음. Furiosa 공식 가이드로 SDK 설치 후 재실행."
  exit 1
fi
echo

echo "=== 3. 측정 클라이언트 의존성 설치 ==="
pip install --upgrade pip wheel >/dev/null
pip install -r requirements.txt
echo

echo "=== 4. SWE-bench 설치 (swebench 태스크용) ==="
pip install swebench || echo "  swebench 설치 실패 — swebench 태스크 빼고 진행 가능"
echo

echo "=== 5. Docker 확인 (SWE-bench 채점에 필요) ==="
if command -v docker >/dev/null 2>&1; then
  docker --version
  docker info >/dev/null 2>&1 || echo "  !! docker 데몬 비응답 — sudo systemctl start docker"
else
  echo "  docker 없음 — SWE-bench 채점 시 필요"
fi
echo

echo "=== 완료. 다음 단계 ==="
cat <<'TXT'
  source ~/furiosa/bin/activate
  hf auth login                 # gated 모델 쓸 때만
  bash preflight.sh             # 환경 점검
  ./run_all.sh                  # 전체 측정 → REPORT.md
TXT
