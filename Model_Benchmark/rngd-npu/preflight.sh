#!/usr/bin/env bash
# 벤치마크 전 사전 점검: 환경/모델 가용성/디스크/NPU 상태.
# 실행: bash preflight.sh
set -u

echo "=== SDK / Driver / Firmware ==="
furiosa-llm collect-env 2>/dev/null | grep -E 'furiosa-llm|Driver|firmware|torch|Python platform' | head -10
echo
furiosa-smi info || true
echo

echo "=== Docker (SWE-bench harness 평가에 필요) ==="
if command -v docker >/dev/null 2>&1; then
    docker version 2>/dev/null | head -5 || echo "docker 명령은 있으나 daemon 비응답"
else
    echo "docker 미설치 — SWE-bench 평가는 스킵하거나 다른 머신에서 진행"
fi
echo

echo "=== Python deps ==="
python3 -c "
import importlib, sys
need = ['furiosa_llm', 'httpx', 'yaml', 'asyncio']
optional = ['swebench']
for m in need:
    try:
        importlib.import_module(m)
        print(f'  ok      {m}')
    except Exception as e:
        print(f'  MISSING {m}: {e}')
for m in optional:
    try:
        importlib.import_module(m)
        print(f'  ok      {m} (optional)')
    except Exception as e:
        print(f'  missing {m} (optional, only needed for SWE-bench): {e}')
"
echo

echo "=== 디스크 (모델 다운로드 + Docker 이미지 캐시) ==="
df -h ~ /var/lib/docker 2>/dev/null | grep -v '^Filesystem'
echo

echo "=== HF 모델별 가용성 (각 모델의 SDK 호환 revision 자동 추정) ==="
python3 - <<'PY'
from huggingface_hub import HfApi
api = HfApi()
import yaml
from pathlib import Path
cfg = yaml.safe_load(Path("configs/models.yaml").read_text())
models = [m["id"] for m in cfg["models"]]
for mid in models:
    try:
        refs = api.list_repo_refs(mid)
        tags = [r.name for r in refs.tags]
        marker = ""
        if any(t.startswith("v2026.2") for t in tags):
            marker = " ✓ v2026.2 ready"
        elif any(t.startswith("v2026") for t in tags):
            marker = " △ v2026.x present"
        else:
            marker = " ✗ v2026 없음"
        print(f"  {mid}  tags={tags}{marker}")
    except Exception as e:
        print(f"  {mid}  ERROR: {e}")
PY
echo

echo "=== 권장 다음 단계 ==="
cat <<'TXT'
1) 위 점검에서 fail이 있으면 먼저 해결.
2) 가벼운 smoke run:
     python orchestrator.py configs/models.yaml --tasks tps --models Qwen2.5-0.5B
3) 본 벤치마크 (한 모델씩):
     python orchestrator.py configs/models.yaml --tasks tps,sweep --models Llama-3.1-8B
4) SWE-bench (Docker 필요):
     python orchestrator.py configs/models.yaml --tasks swebench --models Qwen3-32B
5) 결과 집계:
     python analyze.py
     python analyze.py --csv summary.csv
TXT
