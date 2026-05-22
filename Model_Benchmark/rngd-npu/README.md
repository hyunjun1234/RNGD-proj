# Furiosa RNGD 코드 생성 모델 벤치마크 (furiosa-llm)

RNGD NPU에서 모델마다 토큰 속도, 동시성 스케일링, 서버 옵션, SWE-bench, 임베딩·리랭커를
자동으로 측정하는 폴더입니다. `bench-gpu`(NVIDIA GPU + vLLM) 폴더와 측정 항목, 측정 코드를
똑같이 맞춰서 NPU와 GPU 결과를 직접 비교할 수 있게 했습니다.

전제 조건은 `~/furiosa` 가상환경에 Furiosa SDK와 furiosa-llm이 설치돼 있는 것입니다
(`furiosa-llm`, `furiosa-smi` 명령이 동작하면 됩니다). httpx, openai, datasets, swebench 같은
나머지 의존성은 `setup.sh`가 설치합니다.

## 빠른 시작

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu

# 측정 도구 의존성 설치 (한 번만)
bash setup.sh

# furiosa 가상환경 활성화 (이후 매번)
source ~/furiosa/bin/activate

# 접근 제한 모델을 쓸 때만
hf auth login

# 점검하고 전체 측정
bash preflight.sh
./run_all.sh
```

## 폴더 구조

```
rngd-npu/
├── setup.sh              측정 도구 의존성 설치
├── preflight.sh          NPU·SDK·Docker·모델 점검
├── run_all.sh            전체 측정 파이프라인
├── eval_swebench.sh      SWE-bench 채점
├── requirements.txt      측정용 추가 의존성
├── orchestrator.py       모델별로 테스트를 자동 실행
├── analyze.py            결과 모아서 표로 정리
├── report.py             종합 리포트(REPORT.md) 생성
├── swebench_eval.py      예측 파일을 Docker로 채점
├── configs/
│   └── models.yaml       모델 목록, 서버 인자, 측정 설정
├── runners/
│   ├── server.py         furiosa-llm serve 띄우고 내리는 관리
│   ├── tps.py            첫 토큰 지연, 토큰 간격, 처리량 측정
│   ├── memory_sweep.py   서버 옵션을 바꿔가며 측정
│   ├── embed_bench.py    임베딩·리랭커 처리량 측정
│   └── swebench_run.py   SWE-bench 추론
├── docs/
│   ├── SWEBENCH_SETUP.md   SWE-bench 설명과 환경 구축
│   ├── RUNNING_BENCHMARKS.md
│   └── COMPILING_MODELS.md HF 모델을 직접 컴파일하는 방법
├── artifacts/            직접 빌드한 모델 (선택)
└── results/              측정 결과 (자동 생성)
```

## 측정 항목

| 항목 | 측정 내용 | 대상 |
|---|---|---|
| tps | 요청 한 건의 첫 토큰 지연, 토큰 간격, 출력 속도 | 생성 모델 |
| sweep | 동시 요청 1~128명, 프롬프트 256/1024/4096 조합 | 생성 모델 |
| memsweep | 서버 옵션을 한 번에 하나씩 바꿔가며 처리량 측정 | 생성 모델 |
| swebench | SWE-bench Lite로 코드 패치를 만들고 채점 | 생성 모델 |
| embed | 임베딩 모델의 배치별 처리량 | 임베딩 모델 |
| rerank | 리랭커 모델의 처리량 | 리랭커 모델 |

## 모델 설정 (configs/models.yaml)

모델 id의 `furiosa-ai/*`는 RNGD용으로 미리 컴파일된 prebuilt 모델입니다. 기본으로 켜져 있는 모델은
다음과 같습니다.

| 모델 | 역할 | 비고 |
|---|---|---|
| furiosa-ai/Qwen2.5-0.5B-Instruct | 동작 확인용 | 파이프라인 점검용, PE 4 |
| furiosa-ai/Llama-3.1-8B-Instruct | 코드 생성 후보 | v2026.2 검증, PE 8, 1카드 |
| furiosa-ai/Qwen3-Embedding-8B | 임베딩 | PE 8 |
| furiosa-ai/Qwen3-Reranker-8B | 리랭커 | PE 8 |

기본으로 꺼져 있는 모델은 RNGD 4장 이상 환경에서 켭니다.

`furiosa-ai/Qwen3-32B-FP8`, `furiosa-ai/EXAONE-4.0-32B-FP8`, `furiosa-ai/Llama-3.3-70B-Instruct`는
prebuilt 모델이 `tensor_parallel=32`로 컴파일돼 있어서 RNGD 4장(32 PE)이 있어야 서빙됩니다.
4장 환경이라면 yaml에서 `enabled: true`로 바꾸기만 하면 됩니다.

새 모델은 `models:` 목록에 항목을 추가하면 되고, 측정 코드는 건드릴 필요가 없습니다.
NPU를 여러 개 쓰려면 yaml 위쪽 `devices`를 `"npu:0,npu:1"`로 바꾸거나 모델 serve_args에
`--devices npu:0,npu:1`을 넣습니다.

## 측정 실행

`run_all.sh`는 단계로 나뉘어 있고, `STAGE` 환경변수로 일부만 실행할 수 있습니다.
단계는 `preflight`, `smoke`, `gen`, `embed`, `swebench`, `report`, `all`입니다.

```bash
STAGE=gen ./run_all.sh

# 특정 모델, 특정 항목만 (모델은 이름 일부로 지정)
python orchestrator.py configs/models.yaml --tasks tps,sweep --models Llama-3.1-8B

# 무엇이 실행될지 미리보기
python orchestrator.py configs/models.yaml --tasks tps --dry-run

# 오래 걸리면 백그라운드로
nohup ./run_all.sh > results/_run_logs/run.log 2>&1 &
```

SWE-bench 범위는 환경변수로 조정합니다.

```bash
# 전체 300건 측정
SWEBENCH_N=300 python orchestrator.py configs/models.yaml --tasks swebench

# 컨텍스트 필터와 재시도 켜기
SWEBENCH_FILTER_CONTEXT=1 SWEBENCH_RETRY_INVALID=1 python orchestrator.py ...
```

환경변수 전체 목록은 `runners/swebench_run.py`의 설명 주석에 있습니다.

## 결과 보기

```bash
python analyze.py                 # 항목별 결과를 표로 출력
python analyze.py --csv out.csv   # CSV로 저장
python report.py                  # 종합 리포트(REPORT.md) 생성
```

측정 원본은 `results/<모델>/<항목>/<시각>.json`에, 서버 로그는 `results/_server_logs/`에 쌓입니다.

## GPU(bench-gpu) 버전과 다른 점

| 항목 | RNGD (이 폴더) | GPU (bench-gpu) |
|---|---|---|
| 서빙 | furiosa-llm serve | vllm serve |
| 모델 | furiosa prebuilt 모델 | 원본 HuggingFace 모델 |
| 디바이스 지정 | NPU PE 고정 (`--devices npu:0`) | `CUDA_VISIBLE_DEVICES`와 `--tensor-parallel-size` |
| 컨텍스트 한도 | 모델 컴파일 시 고정 (Qwen 4K, Llama 32K) | `--max-model-len`으로 NPU에 맞춤 |
| memsweep 옵션 | max-model-len, max-batch-size, max-num-batched-tokens | max-model-len, max-num-seqs, max-num-batched-tokens |
| 측정 코드 | 동일 (OpenAI 호환 API 사용) | 동일 |

NPU와 GPU 결과를 같은 조건으로 비교한 내용은
[../README_npu_gpu_result.md](../README_npu_gpu_result.md)에 정리해 두었습니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| `Required PEs: N, Actual: M` | 컴파일된 tp와 가용 PE가 다름. 작은 tp로 다시 빌드하거나 `--devices`를 늘림 |
| 서버 기동 실패 | `results/_server_logs/`의 해당 모델 로그 확인. 흔한 원인은 v2026.2 태그 없음 |
| memsweep에서 메모리 부족 | `max_model_len`이나 `max_batch_size`를 줄여 다시 측정 |
| prefix caching이 자동으로 꺼짐 | 모델에 extend bucket이 없으면 정상 동작. 작은 모델에서 흔함 |
| SWE-bench 첫 실행이 매우 느림 | 항목별 기본 Docker 이미지를 빌드함 (수 시간). 이후로는 캐시됨 |
| 접근 제한 모델 다운로드 실패 | `hf auth login` 후 HuggingFace 웹에서 라이선스 동의 |
