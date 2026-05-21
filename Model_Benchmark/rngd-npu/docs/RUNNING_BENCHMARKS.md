# 벤치마크 실행 — 새 모델 추가 / RNGD 증설

`rngd-npu` 프레임워크로 새 모델·신규 하드웨어에서 벤치마크(tps·sweep·memsweep·
swebench·embed·rerank)를 돌리는 절차.

## 환경

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu
bash setup.sh                        # 측정 클라이언트 의존성 (한 번만)
source ~/furiosa/bin/activate
```

## 1. 모델이 이 머신에서 돌아가는지 확인 (필수 선행)

PE 예산: RNGD 1장 = 8 PE. 이 머신 = 2장 = 16 PE. 모델 PE = `tp × pp`.

```bash
python3 - <<'PY'
import json
from huggingface_hub import hf_hub_download
for mid in ["furiosa-ai/Llama-3.1-8B-Instruct", "furiosa-ai/Qwen3-32B-FP8"]:
    a = json.load(open(hf_hub_download(mid, "artifact.json")))
    pc = a["model"]["parallel_config"]
    pe = pc["tensor_parallel_size"] * pc.get("pipeline_parallel_size", 1)
    print(f"{mid}: {pe} PE, RNGD {pe/8:.1f}장, {'OK' if pe<=16 else '불가'}")
PY
```

실측 (참고):

| 모델 | PE | 카드 | 2장 머신 |
|---|--:|--:|:--:|
| Qwen2.5-0.5B-Instruct | 4 | 0.5 | ✅ |
| Llama-3.1-8B-Instruct | 8 | 1 | ✅ |
| Qwen3-Embedding-8B / Reranker-8B | 8 | 1 | ✅ |
| Qwen3-32B-FP8 / EXAONE-4.0-32B-FP8 / Llama-3.3-70B | 32 | 4 | ❌ |

PE 초과 모델 enable 시 → `furiosa-llm`이 `Required PEs: N` 으로 실패.

## 2. 모델 추가 — `configs/models.yaml`

`models:` 리스트에 항목 추가:

```yaml
  - id: furiosa-ai/Llama-3.1-8B-Instruct   # HF id 또는 로컬 아티팩트 절대경로(/로 시작)
    revision: null                          # HF revision, null=furiosa 기본 태그
    role: baseline                          # smoke|baseline|main|large|embedding|reranker
    gen: true                               # 생성 모델=true, embedding/reranker=false
    enabled: true                           # false=SKIP
    serve_args: ["--tool-call-parser", "llama3_json"]   # 모델별 furiosa-llm serve 인자
```

| 종류 | 설정 |
|---|---|
| reasoning 생성 모델 (Qwen3/EXAONE) | `gen: true`, `serve_args: ["--reasoning-parser","qwen3"]` (또는 `exaone4`) |
| Llama 계열 | `gen: true`, `serve_args: ["--tool-call-parser","llama3_json"]` |
| embedding | `gen: false`, `role: embedding`, `serve_args: []` |
| reranker | `gen: false`, `role: reranker`, `serve_args: []` |
| 멀티카드 모델 | `serve_args`에 `["--devices","npu:0,npu:1"]` 추가 |

## 3. 실행

```bash
# 미리보기
python orchestrator.py configs/models.yaml --tasks tps,sweep --dry-run

# 특정 모델/태스크 (모델은 substring 매칭)
python orchestrator.py configs/models.yaml --tasks tps,sweep,memsweep,swebench --models Llama-3.1-8B

# 단계별 전체 파이프라인 (STAGE: preflight|smoke|gen|embed|swebench|report|all)
STAGE=gen ./run_all.sh

# 장시간 → 백그라운드
nohup python -u orchestrator.py configs/models.yaml \
  --tasks tps,sweep,memsweep,swebench,embed,rerank \
  > results/_run_logs/run.log 2>&1 &
tail -f results/_run_logs/run.log
```

사전 점검: `bash preflight.sh`

## 4. SWE-bench 채점 (Docker)

`swebench` 태스크는 예측 생성까지만. 채점은 분리 실행:

```bash
bash eval_swebench.sh                        # 전체
bash eval_swebench.sh --models Llama-3.1-8B   # 특정 모델
```

범위 조정 / 동작 튜닝 (환경변수):

```bash
SWEBENCH_N=300 python orchestrator.py configs/models.yaml --tasks swebench   # 전체 300건
# 기본 SWEBENCH_N=50 (repo별 stratified)
SWEBENCH_FILTER_CONTEXT=1 SWEBENCH_RETRY_INVALID=1 \
SWEBENCH_DROP_INVALID_PATCH=1 SWEBENCH_MAXTOK=2048 ...
```

전체 환경변수: `runners/swebench_run.py` docstring 참조.

## 5. 결과

```bash
python analyze.py                 # task 결과 표
python analyze.py --csv out.csv   # CSV
python report.py                  # 종합 리포트 → REPORT.md
```

원본 JSON: `results/<model_safe>/<task>/<timestamp>.json`

## 6. RNGD 카드 증설 시

코드 수정 불필요 — `configs/models.yaml`만 변경:

```bash
furiosa-smi info     # 새 카드 수 확인 → PE 예산 = 카드수 × 8
```

1. 1절 PE 체크로 새 예산에 들어오는 모델 → `enabled: true`
2. 멀티카드 모델은 `serve_args`에 `--devices npu:0,npu:1,npu:2,npu:3`
3. 큰 모델이 c=128에서도 안 꺾이면 `sweep.batch_sizes`에 더 큰 값 추가
4. 재실행 (3절)

## 7. 태스크

| 태스크 | 측정 | 대상 |
|---|---|---|
| `tps` | concurrency=1 TTFT/ITL/출력 TPS | 생성 |
| `sweep` | concurrency × prompt_len 매트릭스 | 생성 |
| `memsweep` | serve 옵션 OFAT 스윕 (조합마다 재기동) | 생성 |
| `swebench` | SWE-bench Lite oracle single-shot diff 예측 | 생성 |
| `embed` | `/v1/embeddings` batch별 처리량 | embedding |
| `rerank` | rerank 처리량 | reranker |

## 8. 트러블슈팅

| 증상 | 조치 |
|---|---|
| `Required PEs: N` | PE 초과 → 1절 확인, 카드 증설 또는 `enabled:false` |
| 서버 기동 실패 | `results/_server_logs/<model>_*.log` 확인 |
| OOM (memsweep error 행) | `max_model_len` / `max_batch_size` 축소 후 재측정 |
| prefix caching 자동 비활성 | artifact에 extend bucket 없으면 정상 동작 (소형 모델 흔함) |
| sweep 긴 prompt_len 전부 실패 | 모델 context보다 prompt가 김 → 짧은 prompt_len 행 참고 |

## 체크리스트

```
[ ] source ~/furiosa/bin/activate
[ ] 1절 PE 체크 — 서빙 가능 여부
[ ] configs/models.yaml 항목 추가
[ ] orchestrator.py ... --dry-run 확인
[ ] bash preflight.sh
[ ] orchestrator.py ... --tasks tps,sweep,memsweep,swebench --models <NEW>
[ ] bash eval_swebench.sh --models <NEW>
[ ] python report.py → REPORT.md
```
