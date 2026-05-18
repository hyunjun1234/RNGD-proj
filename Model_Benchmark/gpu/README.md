# NVIDIA GPU 코드 생성 모델 벤치마크 (vLLM)

RNGD에서 하던 측정(토큰 속도 · 동시성 스케일링 · serve 옵션 · SWE-bench · 임베딩/리랭커)을
**NVIDIA GPU + vLLM**에서 그대로 수행하는 자동화 폴더. 이 폴더 하나만 GPU 서버에 복사하면 된다.

전제: GPU 서버에 **NVIDIA 드라이버만** 설치돼 있으면 됨 (`nvidia-smi` 동작). 나머지(vLLM·의존성)는 `setup.sh`가 설치. RTX PRO 6000(96GB) 1장 기준.

## 빠른 시작

```bash
# 0. 이 폴더를 GPU 서버로 복사
scp -r gpu/  user@gpu-server:~/        # 또는 git/rsync

# 1. 환경 구축 (한 번만 — vLLM·torch·CUDA·swebench 설치, 수 분)
cd ~/gpu
bash setup.sh

# 2. 가상환경 활성화 (이후 매 세션)
source .venv/bin/activate

# 3. gated 모델(meta-llama/*) 쓸 때만 — HF 토큰 로그인
hf auth login

# 4. 점검 → 전체 측정
bash preflight.sh
./run_all.sh                    # 측정 후 REPORT.md 생성
```

## 폴더 구조

```
gpu/
├── setup.sh              # 프레시 서버 환경 구축 (한 번)
├── preflight.sh          # GPU/vLLM/Docker/모델 점검
├── run_all.sh            # 전체 파이프라인
├── eval_swebench.sh      # SWE-bench Docker 채점
├── requirements.txt      # vllm + 측정 의존성
├── orchestrator.py       # 모델 × 태스크 자동 실행 (vllm serve)
├── analyze.py            # 결과 집계 / CSV
├── report.py             # 종합 리포트 → REPORT.md
├── swebench_eval.py      # 예측 jsonl → Docker 채점 드라이버
├── configs/
│   └── models.yaml       # 모델 목록 + vllm serve 인자
├── runners/
│   ├── server.py         # VllmServer — vllm serve 라이프사이클
│   ├── tps.py            # 단일 속도 측정
│   ├── memory_sweep.py   # serve 옵션 OFAT 스윕
│   ├── embed_bench.py    # 임베딩/리랭커 처리량
│   └── swebench_run.py   # SWE-bench 추론
├── docs/
│   └── SWEBENCH_SETUP.md # SWE-bench 설명 / 환경 구축
└── results/              # 측정 결과 (자동 생성)
```

## 측정 태스크

| 태스크 | 측정 | 대상 |
|---|---|---|
| `tps` | concurrency=1 TTFT/ITL/출력 TPS | 생성 모델 |
| `sweep` | concurrency{1~128} × prompt_len{256/1024/4096} 매트릭스 | 생성 모델 |
| `memsweep` | vllm serve 옵션 OFAT (max-model-len·max-num-seqs·gpu-memory-utilization) | 생성 모델 |
| `swebench` | SWE-bench Lite oracle single-shot 코드 패치 | 생성 모델 |
| `embed` | `/v1/embeddings` batch별 처리량 | embedding 모델 |
| `rerank` | rerank 처리량 | reranker 모델 |

## 모델 설정 — `configs/models.yaml`

`id`는 Hugging Face 모델 id. 기본 활성:

| 모델 | 역할 | 비고 |
|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct` | smoke | 파이프라인 검증용 |
| `meta-llama/Llama-3.1-8B-Instruct` | baseline | gated — `hf auth login` |
| `Qwen/Qwen3-32B` | main | bf16 ~64GB, 96GB GPU 1장 OK |
| `Qwen/Qwen3-Embedding-8B` | embedding | `--task embed` |
| `Qwen/Qwen3-Reranker-8B` | reranker | `--task score` |

기본 비활성(`enabled: false`) — 켜려면 yaml에서 `true`로:

- `meta-llama/Llama-3.3-70B-Instruct` — bf16 ~140GB > 96GB → `serve_args`에 `--quantization fp8` 포함됨(키면 FP8로 적재). gated.
- `LGAI-EXAONE/EXAONE-4.0-32B` — 모델 id·라이선스 확인 후 enable.

**새 모델 추가**: `models:` 리스트에 항목 추가 (`id`/`role`/`gen`/`enabled`/`serve_args`). 측정 코드 수정 불필요.

**다중 GPU**: `cuda_visible_devices: "0,1"` + 해당 모델 `serve_args`에 `["--tensor-parallel-size","2"]`.

## 실행

```bash
# 단계별 (STAGE: preflight|smoke|gen|embed|swebench|report|all)
STAGE=gen ./run_all.sh

# 특정 모델/태스크만 (모델은 substring 매칭)
python orchestrator.py configs/models.yaml --tasks tps,sweep --models Llama-3.1-8B

# 무엇이 실행될지 미리보기
python orchestrator.py configs/models.yaml --tasks tps --dry-run

# 장시간 → 백그라운드
nohup ./run_all.sh > results/_run_logs/run.log 2>&1 &
```

SWE-bench 범위: `SWEBENCH_N=300 python orchestrator.py configs/models.yaml --tasks swebench` (기본 50건).

## 결과

```bash
python analyze.py                 # task 결과 표
python analyze.py --csv out.csv   # CSV
python report.py                  # 종합 리포트 → REPORT.md
```

원본 JSON: `results/<model>/<task>/<timestamp>.json` · 서버 로그: `results/_server_logs/`

## RNGD 버전과의 차이

| | RNGD (`rngd-npu`) | GPU (이 폴더) |
|---|---|---|
| 서빙 | `furiosa-llm serve` | `vllm serve` |
| 모델 | furiosa prebuilt 아티팩트 | 원본 HF 모델 |
| 디바이스 | NPU PE 고정(tp 컴파일됨) | `CUDA_VISIBLE_DEVICES` + `--tensor-parallel-size` 자유 |
| serve 옵션 | max-batch-size 등 | max-model-len / max-num-seqs / gpu-memory-utilization |
| 측정 러너 | 동일 (OpenAI 호환 API) | 동일 — tps/sweep/swebench/embed 코드 공유 |

## 트러블슈팅

| 증상 | 조치 |
|---|---|
| `nvidia-smi` 없음 | NVIDIA 드라이버 설치 후 재부팅 |
| vLLM 기동 OOM | 모델 `serve_args`에 `--max-model-len 8192` 또는 `--gpu-memory-utilization 0.85` |
| gated 모델 403 | `hf auth login` + HF에서 라이선스 동의 |
| 70B가 안 올라감 | `--quantization fp8` (이미 yaml에 포함) 또는 다중 GPU `--tensor-parallel-size` |
| 서버 기동 실패 | `results/_server_logs/<model>_*.log` 확인 |
| SWE-bench 채점 | Docker 필요 — `docs/SWEBENCH_SETUP.md` 참조 |
| 임베딩/리랭커 task 오류 | vLLM 버전별 `--task` 값 차이 — `embed`/`embedding`, `score` 확인 |
