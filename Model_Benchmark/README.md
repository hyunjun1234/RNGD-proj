# Model_Benchmark

Furiosa RNGD NPU와 NVIDIA GPU에서 같은 모델을 같은 방식으로 측정해, LLM 서빙 성능을 비교하는
프로젝트입니다. NPU를 도입할 때 판단 근거가 될 수치를 만드는 것이 목적입니다.

측정 도구는 OpenAI 호환 API만 호출하기 때문에, 서버를 furiosa-llm으로 띄우든 vLLM으로 띄우든
같은 코드로 측정할 수 있습니다. 덕분에 NPU와 GPU 결과를 같은 표 위에 놓고 비교할 수 있습니다.

## 폴더 구성

| 폴더 / 문서 | 내용 |
|---|---|
| [README_npu_gpu_result.md](README_npu_gpu_result.md) | NPU와 GPU 결과를 비교한 문서. 먼저 읽어보면 좋습니다 |
| [rngd-npu/](rngd-npu/README.md) | RNGD NPU 벤치마크 (furiosa-llm) |
| [bench-gpu/](bench-gpu/README.md) | NVIDIA GPU 벤치마크 (vLLM) |
| [ppt/](ppt/) | 발표 자료. `RNGD_Benchmark.pdf`와 빌드 스크립트 |

```
Model_Benchmark/
├── README.md                  이 문서
├── README_npu_gpu_result.md   NPU vs GPU 결과 비교
├── rngd-npu/                  NPU 벤치마크
│   ├── README.md
│   ├── REPORT.md              측정 결과 리포트 (자동 생성)
│   ├── configs/models.yaml    모델 목록과 측정 설정
│   ├── orchestrator.py        모델별 테스트 자동 실행
│   ├── runners/               테스트별 측정 코드
│   └── results/               측정 결과 원본 (JSON)
├── bench-gpu/                 GPU 벤치마크. 구조는 rngd-npu와 같음
│   └── results/_archive_pre_match/   조건 정렬 전 측정 (보관용)
└── ppt/
    ├── RNGD_Benchmark.pdf
    └── RNGD_Benchmark.pptx
```

각 측정 폴더는 따로 떼어서 쓸 수 있습니다. `bench-gpu/` 폴더만 GPU 서버에 복사하면
`setup.sh`로 환경을 만들고 `run_all.sh`로 측정까지 끝낼 수 있습니다.

## 무엇을 측정했나

다섯 가지를 측정했습니다. 각 항목은 실제로 궁금한 질문 하나에 대응합니다.

| 테스트 | 질문 | 측정 내용 |
|---|---|---|
| 1. 토큰 생성 속도 | 혼자 쓸 때 얼마나 빠른가 | 요청 한 건의 첫 토큰 지연, 토큰 생성 속도 |
| 2. 동시성 스케일링 | 동시 사용자 여러 명을 받을 수 있나 | 동시 요청 1~128명일 때의 처리량과 지연 |
| 3. 서버 옵션 | 기본 설정이 최선인가 | 서버 옵션을 바꿔가며 처리량 변화 측정 |
| 4. SWE-bench | 실제로 코드를 고칠 수 있나 | GitHub 이슈를 패치로 해결한 비율 |
| 5. 임베딩 / 리랭커 | 검색 단계는 얼마나 빠른가 | 임베딩·리랭커 모델의 처리량 |

### 왜 이렇게 측정하나

속도, 정확도, 운영 편의성을 모두 봐야 NPU 도입 여부에 답할 수 있기 때문입니다.

테스트 1과 2는 속도를 봅니다. 혼자 쓸 때의 속도와 동시 사용자가 많을 때의 속도는 완전히 다른 이야기입니다.
챗봇은 한 사람의 응답 속도가 중요하고, 사내 코드 도구는 동시 처리량이 중요합니다. 동시성 측정에서는
처리량이 한계에 다다르는 지점과 지연이 너무 길어지는 지점을 같이 보는데, 여기서 안전하게 받을 수 있는
최대 동시 사용자 수가 나옵니다.

테스트 3은 운영할 때 튜닝할 여지가 있는지를 봅니다. 서버 옵션의 기본값이 우리 작업에 맞는지는 미리 알 수 없어서,
한 번에 한 가지 옵션만 바꿔가며 그 효과를 따로따로 확인합니다. 전체 조합을 다 돌리면 시간이 너무 오래 걸리고
결과 해석도 어렵기 때문에 이 방식을 씁니다.

테스트 4는 정확도를 봅니다. 속도가 빨라도 코드를 못 고치면 의미가 없습니다. SWE-bench는 실제 GitHub 이슈를
받아 실제 테스트로 채점하기 때문에, 산업 현장에 가장 가까운 코드 평가입니다.

테스트 5는 검색 보조 모델을 봅니다. 코드 어시스턴트는 보통 임베딩으로 관련 코드를 찾고, 리랭커로 순서를 매기고,
LLM이 답을 만드는 3단계로 돕니다. 생성 모델만 빨라도 검색 단계가 느리면 전체가 느려지므로 같이 측정합니다.

### 측정한 모델

NPU와 GPU 모두 같은 두 모델을 측정했습니다.

| 모델 | 역할 | NPU 모델 id | GPU 모델 id | 컨텍스트 |
|---|---|---|---|--:|
| Qwen2.5-0.5B-Instruct | 동작 확인용 | furiosa-ai/Qwen2.5-0.5B-Instruct | Qwen/Qwen2.5-0.5B-Instruct | 4,096 |
| Llama-3.1-8B-Instruct | 코드 생성 후보 | furiosa-ai/Llama-3.1-8B-Instruct | meta-llama/Llama-3.1-8B-Instruct | 32,768 |

NPU prebuilt 모델은 컴파일할 때 컨텍스트 길이가 고정됩니다. 공정하게 비교하려고 GPU 쪽도 같은 길이로
맞췄습니다. 컨텍스트 외에 prefix caching, 동시성 측정 범위, SWE-bench 설정도 모두 일치시켰습니다.
맞춘 근거는 [README_npu_gpu_result.md의 측정 조건 항목](README_npu_gpu_result.md#측정-조건을-맞춘-방법)에 정리해 두었습니다.

임베딩·리랭커 모델(Qwen3-Embedding-8B, Qwen3-Reranker-8B)은 NPU에서만 측정했습니다.
32B, 70B 모델은 NPU prebuilt가 RNGD 4카드를 요구해서 현재 2카드 환경에서는 빠졌습니다.
`configs/models.yaml`에 정의는 되어 있어서, 4카드 환경이라면 `enabled: true`로 바꾸기만 하면
코드 수정 없이 측정됩니다.

## 측정 환경 준비

NPU 쪽은 furiosa-llm이 설치된 가상환경이 필요합니다.

```bash
source ~/furiosa/bin/activate
furiosa-llm --version
furiosa-smi info
```

GPU 쪽은 `bench-gpu/` 안에 별도 가상환경을 만듭니다.

```bash
cd bench-gpu
bash setup.sh
source .venv/bin/activate
nvidia-smi
```

모델 가중치는 HuggingFace 캐시(`~/.cache/huggingface/hub`)를 공유합니다.
`meta-llama/*` 같은 접근 제한 모델은 양쪽 모두 `hf auth login`이 필요합니다.
Docker는 SWE-bench 채점에만 쓰이고 다른 측정에는 필요 없습니다.

## 측정 실행

측정은 `preflight → smoke → gen → embed → swebench → report` 순서로 진행됩니다.
환경 점검을 하고, 작은 모델로 파이프라인이 도는지 확인한 뒤, 생성 모델을 측정하고,
임베딩과 SWE-bench를 거쳐 마지막에 리포트를 만듭니다.

`STAGE` 환경변수로 일부만 실행할 수 있습니다.

```bash
STAGE=smoke ./run_all.sh        # 30초, 파이프라인 점검만
STAGE=gen ./run_all.sh          # 생성 모델 측정 (수 시간)
STAGE=swebench ./run_all.sh     # SWE-bench 추론과 채점만
STAGE=report ./run_all.sh       # 결과 JSON으로 REPORT.md만 다시 생성
```

자세한 옵션과 문제 해결은 각 폴더의 README를 참고하시면 됩니다.

## SWE-bench 처음 시작하기

SWE-bench는 이 프로젝트에서 가장 복잡한 테스트라 따로 정리합니다. 본 프로젝트의 `orchestrator.py`가
이 과정을 자동으로 처리하지만, 원리를 알아두면 문제가 생겼을 때 대응하기 쉽습니다.
공식 안내는 [swebench.com 빠른 시작](https://www.swebench.com/SWE-bench/guides/quickstart/)에 있습니다.

### SWE-bench가 무엇인가

LLM이 GitHub 이슈를 코드 패치로 해결할 수 있는지를, 실제 테스트로 채점하는 벤치마크입니다.
객관식이 아니라 실행으로 확인합니다. 모델이 만든 코드가 표면적으로 그럴듯한지가 아니라,
실제로 동작하는지를 봅니다.

### 준비물

| 항목 | 이유 |
|---|---|
| x86_64 리눅스 | 채점 도구가 Docker 이미지를 만듭니다 |
| 실행 중인 Docker | 인스턴스마다 격리된 컨테이너에서 테스트를 돌립니다 |
| Python 3.10 이상 | swebench 패키지가 요구합니다 |
| 디스크 100GB 이상 | Docker 이미지와 인스턴스별 코드가 쌓입니다 |

macOS나 ARM은 공식 지원이 아닙니다. 이 프로젝트는 x86_64 리눅스를 전제로 합니다.

### 30분 안에 첫 채점 결과 보기

먼저 swebench를 설치합니다.

```bash
pip install swebench
# 또는 최신 버전이 필요하면
git clone https://github.com/SWE-bench/SWE-bench.git
cd SWE-bench && pip install -e .
```

데이터셋을 불러와 구조를 살펴봅니다.

```python
from datasets import load_dataset

# 300건짜리 Lite 데이터셋. 이 프로젝트가 쓰는 데이터셋입니다.
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
print(len(ds), ds.column_names)

# 추론용 oracle 데이터셋. text 컬럼에 프롬프트가 미리 들어 있습니다.
ds_oracle = load_dataset("princeton-nlp/SWE-bench_Lite_oracle", split="test")
print(ds_oracle[0]["text"][:500])
```

모델 없이 정답 패치로 채점기가 제대로 도는지 먼저 확인하면 좋습니다. 환경이 망가졌는지를
가장 빨리 알 수 있는 방법입니다.

```bash
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path gold \
    --instance_ids sympy__sympy-20590 \
    --max_workers 1 \
    --run_id validate-gold
```

`gold`는 정답 패치라서 해결 1건이 나와야 정상입니다. 안 나오면 Docker나 디스크,
권한 문제일 가능성이 높습니다.

다음으로 모델이 만든 패치를 담은 예측 파일을 만듭니다. 한 줄에 인스턴스 하나씩 들어가는 JSONL 형식입니다.

```jsonl
{"instance_id": "astropy__astropy-12907", "model_name_or_path": "my-model", "model_patch": "diff --git a/...\n..."}
```

`instance_id`는 데이터셋의 식별자와 정확히 같아야 하고, `model_patch`에는 형식에 맞는 unified diff
문자열이 들어가야 합니다. 마크다운 표시나 설명을 섞으면 안 됩니다. 본 프로젝트에서는
`runners/swebench_run.py`가 로컬 서버에 프롬프트를 보내고 응답에서 diff만 추려 이 형식으로 저장합니다.

이제 채점을 실행합니다.

```bash
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path predictions.jsonl \
    --max_workers 8 \
    --namespace swebench \
    --cache_level env \
    --run_id my_first_eval
```

`--namespace swebench`는 미리 빌드된 Docker 이미지를 받아오는 옵션입니다. 이 옵션이 없으면
12개 저장소의 기본 이미지를 직접 빌드하느라 몇 시간이 걸리므로, 항상 켜는 것이 좋습니다.
`--max_workers`는 동시에 돌릴 컨테이너 수인데, 워커마다 메모리를 몇 GB씩 쓰므로 메모리에 맞춰 정합니다.

채점이 끝나면 요약 리포트(`<모델이름>.<run_id>.json`)와 인스턴스별 실행 로그가 생깁니다.
요약 리포트에는 전체 건수, 해결 건수, 미해결 건수, 적용 실패 건수가 들어 있고,
해결 건수를 전체 건수로 나눈 값이 모델 점수입니다.

문제가 생기면 다음 순서로 확인합니다. 먼저 정답 패치(`gold`)로 다시 채점해서 환경 문제인지
모델 문제인지 가립니다. 그다음 실패한 인스턴스의 로그(`logs/run_evaluation/.../run_instance.log`)를
열어봅니다. 패치 형식이 깨졌다면 모델 응답에 마크다운 표시나 설명이 섞이지 않았는지 봅니다.
컨테이너를 만들 때 메모리가 부족하면 `--max_workers`를 줄입니다.

### 데이터셋 종류

| 데이터셋 | 쓰는 경우 |
|---|---|
| SWE-bench Lite (300건) | 처음 평가할 때. 비용과 시간이 적당합니다 |
| SWE-bench Verified (500건) | 사람이 검증한 데이터라 신뢰도가 가장 높습니다 |
| SWE-bench (2,294건) | 종합 점수를 비교할 때. 시간이 많이 듭니다 |
| SWE-bench Multimodal (517건) | 화면 요소가 있는 자바스크립트·UI 평가 |

본 프로젝트의 자동화 파이프라인에서는 위 과정이 한 줄로 끝납니다.

```bash
cd rngd-npu && SWEBENCH_N=50 python orchestrator.py configs/models.yaml --tasks swebench
bash eval_swebench.sh
```

SWE-bench의 동작 원리는 [bench-gpu/README.md](bench-gpu/README.md)에 더 자세히 정리해 두었습니다.

## 결과 보기

각 폴더의 `REPORT.md`가 측정 결과를 정리한 리포트입니다. 모델별 핵심 지표, 단일 요청 속도,
동시성 스케일링, 서버 옵션, SWE-bench, 임베딩·리랭커 처리량, 권장 설정, 종합 점수 순으로 들어 있습니다.

```bash
python analyze.py --csv all.csv   # 모든 측정 결과를 CSV로 내보내기
python report.py                  # REPORT.md 다시 생성
```

NPU와 GPU 결과를 함께 보려면 [README_npu_gpu_result.md](README_npu_gpu_result.md)를 참고하시면 됩니다.
