# Furiosa RNGD 코드 생성 모델 벤치마크 (furiosa-llm)

RNGD에서 7개 모델 각각에 대해 **토큰 속도 · 동시성 스케일링 · serve 옵션 · SWE-bench · 임베딩/리랭커**를
자동 측정. `bench-gpu`(NVIDIA GPU + vLLM 버전)와 동일한 측정 축·동일한 OpenAI 호환 클라이언트를
사용해 결과를 직접 비교 가능하게 한다.

전제: `~/furiosa` 가상환경에 **Furiosa SDK + furiosa-llm**이 설치돼 있음 (`furiosa-llm`, `furiosa-smi` 동작).
나머지(httpx·openai·datasets·swebench)는 `setup.sh`가 설치.

## 빠른 시작

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu

# 1. 측정 클라이언트 의존성 설치 (한 번만)
bash setup.sh

# 2. furiosa venv 활성화 (이후 매 세션)
source ~/furiosa/bin/activate

# 3. gated 모델 쓸 때만 — HF 토큰 로그인
hf auth login

# 4. 점검 → 전체 측정
bash preflight.sh
./run_all.sh                    # 측정 후 REPORT.md 생성
```

## 폴더 구조

```
rngd-npu/
├── setup.sh              # 측정 클라이언트 의존성 설치 (furiosa venv 위에)
├── preflight.sh          # NPU/SDK/Docker/모델 점검
├── run_all.sh            # 전체 파이프라인 (STAGE 단계별)
├── eval_swebench.sh      # SWE-bench Docker 채점
├── requirements.txt      # 측정용 추가 의존성
├── orchestrator.py       # 모델 × 태스크 자동 실행 (furiosa-llm serve)
├── analyze.py            # 결과 집계 / CSV
├── report.py             # 종합 리포트 → REPORT.md
├── swebench_eval.py      # 예측 jsonl → Docker 채점 드라이버
├── configs/
│   └── models.yaml       # 모델 목록 + serve_args + sweep/memsweep grid
├── runners/
│   ├── server.py         # FuriosaServer — furiosa-llm serve 라이프사이클
│   ├── tps.py            # 단일 속도/스트림 측정
│   ├── memory_sweep.py   # serve 옵션 OFAT 스윕
│   ├── embed_bench.py    # 임베딩/리랭커 처리량
│   └── swebench_run.py   # SWE-bench 추론(컨텍스트 필터/patch sanity/retry)
├── docs/
│   ├── SWEBENCH_SETUP.md   # SWE-bench 설명 / 환경 구축
│   ├── RUNNING_BENCHMARKS.md
│   └── COMPILING_MODELS.md # HF 모델 직접 컴파일 (RNGD prebuilt에 없을 때)
├── artifacts/            # 직접 빌드한 아티팩트 (선택)
└── results/              # 측정 결과 (자동 생성)
```

## 측정 태스크

| 태스크 | 측정 | 대상 |
|---|---|---|
| `tps` | concurrency=1 TTFT/ITL/출력 TPS | 생성 모델 |
| `sweep` | concurrency{1~128} × prompt_len{256/1024/4096} 매트릭스 | 생성 모델 |
| `memsweep` | furiosa-llm serve 옵션 OFAT (max-model-len·max-batch-size·max-num-batched-tokens) | 생성 모델 |
| `swebench` | SWE-bench Lite oracle single-shot 코드 패치 | 생성 모델 |
| `embed` | `/v1/embeddings` batch별 처리량 | embedding 모델 |
| `rerank` | rerank 처리량 (실패 시 임베딩+코사인 fallback) | reranker 모델 |

## 모델 설정 — `configs/models.yaml`

`id`는 HF 모델 id (furiosa-ai/* = prebuilt 아티팩트). 기본 활성:

| 모델 | 역할 | 비고 |
|---|---|---|
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | smoke | 파이프라인 검증용 (PE 4) |
| `furiosa-ai/Llama-3.1-8B-Instruct` | baseline | v2026.2 검증 (PE 8, 1카드) |
| `furiosa-ai/Qwen3-Embedding-8B` | embedding | PE 8 |
| `furiosa-ai/Qwen3-Reranker-8B` | reranker | PE 8 |

기본 비활성(`enabled: false`) — RNGD 4장 이상에서 켜기:

- `furiosa-ai/Qwen3-32B-FP8` · `furiosa-ai/EXAONE-4.0-32B-FP8` · `furiosa-ai/Llama-3.3-70B-Instruct`
  — prebuilt 아티팩트가 `tensor_parallel=32` (RNGD 4장 = 32 PE)로 하드 컴파일됨.

**새 모델 추가**: `models:` 리스트에 항목 추가. 측정 코드 수정 불필요.
**다중 NPU**: `devices: "npu:0,npu:1"` (top-level) 또는 모델 `serve_args`에 `["--devices","npu:0,npu:1"]`.

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

SWE-bench 범위 조정 (환경변수):

```bash
SWEBENCH_N=300 python orchestrator.py configs/models.yaml --tasks swebench   # 전체 300건
SWEBENCH_FILTER_CONTEXT=1 SWEBENCH_RETRY_INVALID=1 ...                       # 컨텍스트 필터/재시도
```

자세한 환경변수 목록은 `runners/swebench_run.py` docstring 참조.

## 결과

```bash
python analyze.py                 # task 결과 표
python analyze.py --csv out.csv   # CSV
python report.py                  # 종합 리포트 → REPORT.md
```

원본 JSON: `results/<model>/<task>/<timestamp>.json` · 서버 로그: `results/_server_logs/`

## GPU(`bench-gpu`) 버전과의 차이

| | RNGD (이 폴더) | GPU (`bench-gpu`) |
|---|---|---|
| 서빙 | `furiosa-llm serve` | `vllm serve` |
| 모델 | furiosa prebuilt 아티팩트 | 원본 HF 모델 |
| 디바이스 | NPU PE 고정(tp 컴파일됨) — `--devices npu:0` | `CUDA_VISIBLE_DEVICES` + `--tensor-parallel-size` 자유 |
| 컨텍스트 한도 | artifact 컴파일 시 고정 (Qwen 4K · Llama 32K) | `--max-model-len`으로 NPU 한도에 맞춤 |
| serve 옵션(memsweep) | `max-model-len` / `max-batch-size` / `max-num-batched-tokens` | `max-model-len` / `max-num-seqs` / `max-num-batched-tokens` |
| 측정 러너 | 동일 (OpenAI 호환 API) | 동일 — tps/sweep/swebench/embed 코드 공유 |

> **NPU vs GPU 실측 비교 분석**: [`../README_npu_gpu_result.md`](../README_npu_gpu_result.md) —
> 같은 모델·같은 조건으로 측정한 두 디바이스의 속도·동시성·SWE-bench 결과 대조.

## 트러블슈팅

| 증상 | 조치 |
|---|---|
| `Required PEs: N, Actual: M` | 빌드 tp ≠ 가용 PE → 작은 tp 재빌드 또는 `--devices` 늘리기 |
| 서버 기동 실패 | `results/_server_logs/<model>_*.log` 확인 (가장 흔한 원인: v2026.2 태그 부재) |
| OOM (memsweep error 행) | `max_model_len` / `max_batch_size` 축소 후 재측정 |
| prefix caching 자동 비활성 | artifact에 extend bucket 없으면 정상 동작 (작은 모델 흔함) |
| SWE-bench 첫 실행이 매우 느림 | task별 base Docker 이미지 빌드 (수 시간). 이후 캐시 |
| gated 모델 다운로드 실패 | `hf auth login` + HF에서 라이선스 동의 |
