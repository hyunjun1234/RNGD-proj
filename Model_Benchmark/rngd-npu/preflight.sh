#!/usr/bin/env bash
# 측정 전 사전 점검 — NPU / furiosa-llm / 의존성 / Docker / 디스크 / 모델 가용성.
set -u
cd "$(dirname "$0")"
[ -f ~/furiosa/bin/activate ] && source ~/furiosa/bin/activate

echo "=== NPU (furiosa-smi) ==="
if command -v furiosa-smi >/dev/null 2>&1; then
  furiosa-smi info 2>/dev/null || echo "  !! furiosa-smi info 실패 — 드라이버/펌웨어 확인"
else
  echo "  !! furiosa-smi 없음 — Furiosa SDK 설치 필요"
fi
echo

echo "=== SDK / Driver / Firmware ==="
furiosa-llm collect-env 2>/dev/null | grep -E 'furiosa-llm|Driver|firmware|torch|Python platform' | head -10 \
  || echo "  !! furiosa-llm 없음 — Furiosa SDK 설치 필요"
echo

echo "=== Python 의존성 ==="
python - <<'PY'
import importlib
for m in ["furiosa_llm", "httpx", "yaml", "openai", "datasets", "transformers"]:
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

echo "=== 디스크 (모델 다운로드 + Docker 이미지 캐시) ==="
df -h ~ /var/lib/docker 2>/dev/null | grep -v '^Filesystem'
echo

echo "=== HF 모델별 가용성 (각 모델의 SDK 호환 revision 자동 추정) ==="
python - <<'PY'
from huggingface_hub import HfApi
import yaml
from pathlib import Path
api = HfApi()
cfg = yaml.safe_load(Path("configs/models.yaml").read_text())
for m in cfg["models"]:
    mid = m["id"]
    try:
        refs = api.list_repo_refs(mid)
        tags = [r.name for r in refs.tags]
        if any(t.startswith("v2026.2") for t in tags):
            marker = " ✓ v2026.2 ready"
        elif any(t.startswith("v2026") for t in tags):
            marker = " △ v2026.x present"
        else:
            marker = " ✗ v2026 없음"
        print(f"  {mid}  tags={tags}{marker}")
    except Exception as e:
        print(f"  {mid}  ERROR: {type(e).__name__} — gated면 `hf auth login`")
PY
echo

echo "=== 다음 단계 ==="
cat <<'TXT'
  ./run_all.sh                                                                # 전체 파이프라인
  python orchestrator.py configs/models.yaml --tasks tps --models Qwen2.5-0.5B  # 단일 확인
TXT
