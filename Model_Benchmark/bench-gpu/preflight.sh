#!/usr/bin/env bash
# 측정 전 사전 점검 — GPU / vLLM / 의존성 / Docker / 디스크 / 모델 가용성.
set -u
cd "$(dirname "$0")"
[ -d .venv ] && source .venv/bin/activate

echo "=== GPU ==="
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv 2>/dev/null \
  || echo "  !! nvidia-smi 없음 — setup.sh / 드라이버 확인"
echo

echo "=== vLLM / torch CUDA ==="
python - <<'PY'
try:
    import vllm; print(f"  ok      vllm {vllm.__version__}")
except Exception as e:
    print(f"  !! vllm 미설치 — setup.sh 실행 ({type(e).__name__})")
try:
    import torch
    print(f"  ok      torch {torch.__version__} (CUDA build {torch.version.cuda})")
    if torch.cuda.is_available():
        print(f"  ok      torch.cuda — GPU {torch.cuda.device_count()}개 인식")
    else:
        print("  !! torch.cuda.is_available()=False — 드라이버 ↔ torch CUDA 불일치 의심.")
        print("     setup.sh 재설치(uv --torch-backend=auto)로 드라이버에 맞는 CUDA 휠 설치.")
except Exception as e:
    print(f"  !! torch: {type(e).__name__}: {e}")
PY
echo

echo "=== Python 의존성 ==="
python - <<'PY'
import importlib
for m in ["httpx", "yaml", "openai", "datasets"]:
    try:
        importlib.import_module(m); print(f"  ok      {m}")
    except Exception as e:
        print(f"  MISSING {m}: {e}")
for m in ["swebench"]:
    try:
        importlib.import_module(m); print(f"  ok      {m} (swebench 태스크용)")
    except Exception as e:
        print(f"  missing {m} (swebench 태스크 쓸 때만 필요)")
PY
echo

echo "=== Docker (SWE-bench 채점용) ==="
command -v docker >/dev/null 2>&1 && (docker info >/dev/null 2>&1 \
  && echo "  ok — docker 동작" || echo "  docker 데몬 비응답") \
  || echo "  docker 없음 — swebench 채점 시 필요"
echo

echo "=== 디스크 ==="
df -h . /var/lib/docker 2>/dev/null | grep -v '^Filesystem'
echo

echo "=== HF 모델 접근 확인 ==="
python - <<'PY'
from huggingface_hub import HfApi
import yaml
from pathlib import Path
api = HfApi()
cfg = yaml.safe_load(Path("configs/models.yaml").read_text())
for m in cfg["models"]:
    mid = m["id"]
    try:
        api.model_info(mid)
        gated = " (gated — HF_TOKEN 필요할 수 있음)" if mid.startswith("meta-llama/") else ""
        print(f"  ok   {mid}{gated}")
    except Exception as e:
        print(f"  !!   {mid}: {type(e).__name__} — gated면 `hf auth login`")
PY
echo

echo "=== 다음 단계 ==="
cat <<'TXT'
  ./run_all.sh                                    # 전체 파이프라인
  python orchestrator.py configs/models.yaml --tasks tps --models Qwen2.5-0.5B   # 단일 확인
TXT
