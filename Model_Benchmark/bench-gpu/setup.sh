#!/usr/bin/env bash
# 프레시 NVIDIA GPU 서버 환경 구축 — 한 번만 실행.
# 전제: NVIDIA 드라이버는 설치돼 있음(nvidia-smi 동작). vLLM/Python 의존성은 이 스크립트가 설치.
set -uo pipefail
cd "$(dirname "$0")"

echo "=== 1. GPU 확인 ==="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
else
  echo "!! nvidia-smi 없음 — NVIDIA 드라이버를 먼저 설치해야 vLLM이 동작합니다."
  echo "   Ubuntu: sudo apt-get install -y nvidia-driver-560 (또는 최신) 후 재부팅"
fi
echo

echo "=== 2. Python 가상환경(.venv) 생성 ==="
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel >/dev/null
echo "  .venv 생성 완료"
echo

echo "=== 3. vLLM + 측정 의존성 설치 (수 분 소요 — torch/CUDA 포함) ==="
# requirements.txt가 vLLM 0.10.0 cu126 휠을 직접 고정한다(드라이버 570 = CUDA 12.8 상한).
# 기본 PyPI `vllm`(cu129)은 이 드라이버에서 못 돈다 — 자세한 건 requirements.txt 주석.
pip install -U uv
uv pip install -r requirements.txt
echo

echo "=== 4. SWE-bench 설치 (swebench 태스크용) ==="
pip install swebench || echo "  swebench 설치 실패 — swebench 태스크 빼고 진행 가능"
echo

echo "=== 5. Docker 확인 (SWE-bench 채점에 필요) ==="
if command -v docker >/dev/null 2>&1; then
  docker --version
  docker info >/dev/null 2>&1 || echo "  !! docker 데몬 비응답 — sudo systemctl start docker"
else
  echo "  docker 없음 — SWE-bench 채점 시 필요. https://docs.docker.com/engine/install/"
fi
echo

echo "=== 완료. 다음 단계 ==="
cat <<'TXT'
  source .venv/bin/activate
  hf auth login                 # gated 모델(meta-llama/*) 쓸 때만
  bash preflight.sh             # 환경 점검
  ./run_all.sh                  # 전체 측정 → REPORT.md
TXT
