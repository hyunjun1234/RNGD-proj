# Model_Benchmark — RNGD NPU vs NVIDIA GPU LLM 서빙 벤치마크

Furiosa **RNGD NPU**와 **NVIDIA GPU(vLLM)** 위에서 같은 모델·같은 측정 축으로 LLM 서빙 성능을 재고,
NPU 도입의 정량적 근거를 만드는 자동화 프로젝트.

> **핵심 아이디어**: 측정 러너(`tps/sweep/swebench/embed`)는 **OpenAI 호환 API**를 통해 동일 코드로 동작한다.
> 서버 계층(furiosa-llm vs vllm)만 바뀌므로 두 결과를 같은 표 위에 올려놓고 비교할 수 있다.

| 폴더 | 내용 |
|---|---|
| [`rngd-npu/`](rngd-npu/README.md) | Furiosa RNGD NPU 벤치 (`furiosa-llm serve`) — 측정 본진 |
| [`bench-gpu/`](bench-gpu/README.md) | NVIDIA GPU 벤치 (`vllm serve`) — 동일 측정 축 포팅 |
| [`ppt/`](ppt/) | 발표 자료 (`pptxgenjs` 빌드) + 디자인 스펙(`Design.md`) + 폰트 + `RNGD_Benchmark.pdf` |

---

## 목차

1. [무엇을 측정했나 — 그리고 왜](#1-무엇을-측정했나--그리고-왜)
2. [폴더 구조](#2-폴더-구조)
3. [공용 환경 — Furiosa venv·모델 캐시](#3-공용-환경--furiosa-venv모델-캐시)
4. [실행 흐름](#4-실행-흐름)
5. **[SWE-bench 처음 시작하기 — 공식 quickstart 기반](#5-swe-bench-처음-시작하기--공식-quickstart-기반)**
6. [결과·리포트 보는 법](#6-결과리포트-보는-법)

---

## 1. 무엇을 측정했나 — 그리고 왜

총 **5개 축**으로 측정. 각 축은 "사용자가 실제로 신경 쓰는 질문 하나"에 대응한다.

| # | 태스크 | 질문 | 무엇으로 답하나 |
|---|---|---|---|
| 1 | `tps` | "혼자 쓸 때 얼마나 빠른가?" | concurrency=1로 TTFT(첫 토큰 지연), ITL(토큰 간 지연), 출력 TPS |
| 2 | `sweep` | "동시 사용자 N명을 안정적으로 받을 수 있나?" | concurrency 1~128 × prompt 256/1024/4096 매트릭스로 처리량과 latency 동시 측정 |
| 3 | `memsweep` | "기본 serve 옵션이 정말 최적인가?" | KV 캐시/배치/메모리 옵션 OFAT 스윕 (한 축씩) |
| 4 | `swebench` | "이 모델이 실제로 코드를 고칠 수 있나?" | SWE-bench Lite oracle single-shot — 실제 GitHub 이슈를 패치로 해결한 비율 |
| 5 | `embed`/`rerank` | "RAG 검색 단계는 얼마나 빨리 도나?" | embedding/reranker throughput (batch별) |

### 왜 이 5개인가

> **속도 + 정확도 + 운영성** 세 축을 모두 본다 — 어느 하나라도 빠지면 NPU 도입 결정에 답이 안 된다.

#### 1·2번 — 속도 (tps + sweep)

- **혼자 쓸 때(`tps`)와 다중 사용자(`sweep`)는 완전히 다른 시나리오**다.
- 챗봇은 `tps`(체감 응답 속도)가 중요하고, 사내 코드 어시스턴트는 `sweep`(동시성 처리량)이 중요하다.
- `sweep`에서 **처리량이 saturate되는 지점**과 **latency가 SLA를 깨는 지점**을 같이 본다 → 운영에서 "안전한 최대 동시성"이 나온다.

#### 3번 — 운영 튜닝 여지 (memsweep)

- vLLM/furiosa-llm 기본값이 정말 우리 워크로드에 맞는지는 미리 모른다.
- `--max-model-len`을 줄이면 KV 캐시 메모리가 풀려 더 큰 배치를 받을 수 있는 **trade-off**가 있는데, 그 영향이 모델마다 다르다.
- **OFAT(One-Factor-At-a-Time)** 로 한 축씩 움직여서 옵션 하나의 효과를 분리해 본다 — 전체 grid는 시간이 폭발하고, 결과 디버깅도 어렵다.

#### 4번 — 정확도 (swebench)

- **속도가 빨라도 코드 수정이 안 되면 무용지물**이다. 작은 모델(0.5B)은 단일 TPS가 250이지만 SWE-bench 0%다.
- SWE-bench는 **실제 GitHub 이슈를 받아 실제 pytest로 채점**하는 — 산업계에서 가장 가까운 코드 벤치마크.
- `oracle` + `single-shot`을 선택한 이유: NPU vs GPU 비교에서 **인프라 외 변수**(검색 품질·에이전트 프레임워크)를 빼고 모델 자체의 코드 편집 능력만 본다.

#### 5번 — RAG 보조 (embed/rerank)

- 코드 어시스턴트의 실제 파이프라인은 "embedding 검색 → rerank → LLM 생성"의 3단 구조.
- 생성 모델만 빨라도 검색/rerank가 병목이면 전체가 느려진다 → 같은 디바이스에서 embedding/reranker도 잴 필요가 있다.

### 사용한 모델

NPU와 GPU 양쪽 모두 같은 두 모델을 baseline으로 측정 — 비교의 기준선:

| 모델 | 의도 | NPU | GPU |
|---|---|---|---|
| `Qwen2.5-0.5B-Instruct` | smoke + 작은 모델 속도 상한 | `furiosa-ai/Qwen2.5-0.5B-Instruct` (PE 4) | `Qwen/Qwen2.5-0.5B-Instruct` |
| `Llama-3.1-8B-Instruct` | 실용 사이즈 baseline (gated) | `furiosa-ai/Llama-3.1-8B-Instruct` (PE 8) | `meta-llama/Llama-3.1-8B-Instruct` |

추가 모델(32B·70B·embedding·reranker)은 `configs/models.yaml`에 정의돼 있고, `enabled: true`로 켜면 측정에 포함된다.

---

## 2. 폴더 구조

```
Model_Benchmark/
├── README.md                       # 이 문서 — 프로젝트 진입점
├── rngd-npu/                       # ── NPU 벤치 ────────────────────
│   ├── README.md                   #     상세 사용법
│   ├── REPORT.md                   #     실측 결과 리포트
│   ├── configs/models.yaml         #     모델·sweep·memsweep grid
│   ├── orchestrator.py             #     모델 × 태스크 자동 실행
│   ├── runners/                    #     tps/sweep/memsweep/swebench/embed
│   ├── docs/                       #     SWE-bench 셋업, 모델 컴파일 가이드
│   └── results/                    #     원본 측정 JSON + 로그
├── bench-gpu/                      # ── GPU 벤치 (NPU 포트) ─────────
│   ├── README.md                   #     상세 사용법 + SWE-bench 깊이 분석
│   ├── REPORT.md                   #     실측 결과 리포트
│   ├── configs/models.yaml         #     동일 구조 — vllm 인자 사용
│   ├── orchestrator.py             #     NPU와 동일 — server 계층만 다름
│   ├── runners/                    #     동일 측정 코드 (vllm 호환)
│   ├── docs/SWEBENCH_SETUP.md
│   └── results/
└── ppt/                            # ── 발표 자료 ───────────────────
    ├── Design.md                   #     디자인 스펙
    ├── build.js                    #     pptxgenjs 빌드 스크립트
    ├── RNGD_Benchmark.pdf
    └── RNGD_Benchmark.pptx
```

각 측정 폴더는 **자기 완결적**이다 — `bench-gpu/`만 들고 GPU 서버에 가서 `setup.sh` → `run_all.sh`로 끝난다.

---

## 3. 공용 환경 — Furiosa venv·모델 캐시

### NPU 쪽

```bash
# Furiosa SDK·furiosa-llm 설치된 venv 활성화 (NPU 측정의 전제)
source ~/furiosa/bin/activate
furiosa-llm --version
furiosa-smi info
```

### GPU 쪽

```bash
# 별도 venv (bench-gpu/.venv) — setup.sh가 생성
cd bench-gpu
bash setup.sh
source .venv/bin/activate
nvidia-smi
```

### 공통

- **모델 캐시**: HuggingFace는 `~/.cache/huggingface/hub` 공유. NPU/GPU 양쪽 모두 같은 가중치를 받는다.
- **gated 모델**(`meta-llama/*`): 두 환경 모두 `hf auth login` 필요.
- **Docker**: SWE-bench 채점에만 필요. 측정 자체에는 불필요.

---

## 4. 실행 흐름

NPU와 GPU 각각 동일 흐름:

```
preflight  →  smoke  →  gen  →  embed  →  swebench  →  report
   ↑             ↑        ↑          ↑           ↑           ↑
환경 점검    파이프라인   tps+sweep   embedding   추론+채점   REPORT.md
(GPU/NPU·    검증(작은    +memsweep   /reranker  (Docker)    자동 생성
 SDK·docker  모델 1회)   (생성 모델)
 ·HF 모델)
```

각 단계는 환경변수 `STAGE`로 분리 실행 가능:

```bash
STAGE=smoke ./run_all.sh        # 30초 — 파이프라인이 망가지지 않았는지만 확인
STAGE=gen ./run_all.sh          # 생성 모델 전부 (수 시간)
STAGE=swebench ./run_all.sh     # 추론 + 채점만 (수 시간 — 첫 실행은 Docker 빌드/pull 시간 추가)
STAGE=report ./run_all.sh       # JSON 결과 → REPORT.md만 다시 생성
```

자세한 환경변수·플래그·트러블슈팅은 각 폴더 README를 본다.

---

## 5. SWE-bench 처음 시작하기 — 공식 quickstart 기반

> 출처: [swebench.com/SWE-bench/guides/quickstart](https://www.swebench.com/SWE-bench/guides/quickstart/) · [github.com/SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench)
>
> 이 섹션은 SWE-bench를 처음 접하는 사람이 **30분 안에 첫 채점 결과를 본 적이 있다고 말할 수 있게** 한다.
> 본 프로젝트에서는 `rngd-npu/` · `bench-gpu/`의 `orchestrator swebench` 태스크가 이 흐름을 자동화하지만, 원리를 알면 디버깅이 쉬워진다.

### 5.1 SWE-bench를 한 문장으로

> "**LLM이 GitHub 이슈를 코드 패치로 해결할 수 있는지를, 실제 pytest로 채점하는** 벤치마크."

객관식이 아니라 **실행 기반(execution-based)** 평가다 → 모델 출력의 표면적 유사성이 아니라 "코드가 실제로 동작하는가"를 본다.

### 5.2 사전 준비물

| 항목 | 왜 필요 | 확인 |
|---|---|---|
| Linux x86_64 | swebench harness가 Docker 이미지를 만든다 | `uname -m` → `x86_64` |
| Docker (실행 중) | 인스턴스별 격리 컨테이너에서 테스트 실행 | `docker info` |
| Python 3.10+ | swebench 패키지 의존 | `python --version` |
| 디스크 ~120GB | prebuilt Docker 이미지 + 인스턴스별 코드 | `df -h .` |
| (옵션) HF 토큰 | gated 모델 사용 시 | `hf auth login` |

> ⚠️ **macOS / ARM은 비공식 지원**. 본 측정은 x86_64 Linux 전제.

### 5.3 30분 워크스루 — 0건에서 채점 결과까지

#### 1단계. 설치 (한 번)

```bash
# 옵션 A: 안정 버전
pip install swebench

# 옵션 B: 최신 main (개발용)
git clone https://github.com/SWE-bench/SWE-bench.git
cd SWE-bench && pip install -e .
```

#### 2단계. 데이터셋 로드해 보기

```python
from datasets import load_dataset

# 300건 Lite (저비용 평가용 — 본 측정이 쓰는 것)
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
print(len(ds), ds.column_names)
# 300, ['repo', 'instance_id', 'base_commit', 'patch', 'test_patch',
#       'problem_statement', 'hints_text', 'created_at', 'version',
#       'FAIL_TO_PASS', 'PASS_TO_PASS', 'environment_setup_commit']

# 추론용 oracle (text 컬럼에 프롬프트가 prebuilt돼 있음)
ds_oracle = load_dataset("princeton-nlp/SWE-bench_Lite_oracle", split="test")
print(ds_oracle[0]["text"][:500])
```

#### 3단계. gold patch로 "harness 자체가 동작하는가" 검증

모델 없이도 정답 patch(`gold`)로 채점기를 굴려볼 수 있다 — 환경이 깨졌는지 가장 빨리 확인하는 방법:

```bash
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path gold \
    --instance_ids sympy__sympy-20590 \
    --max_workers 1 \
    --run_id validate-gold
```

`gold`는 정답 patch라서 **resolved=1**이 나와야 정상이다. 안 나오면 Docker / 디스크 / 권한 문제.

#### 4단계. 예측 파일 만들기 (`predictions.jsonl`)

채점기는 **한 줄에 한 인스턴스**의 JSONL을 받는다:

```jsonl
{"instance_id": "astropy__astropy-12907", "model_name_or_path": "my-model", "model_patch": "diff --git a/...\n--- a/...\n+++ b/...\n@@ ... @@\n..."}
{"instance_id": "django__django-13551",  "model_name_or_path": "my-model", "model_patch": "diff --git a/...\n..."}
```

필수 키 3개:
- `instance_id` — 데이터셋의 인스턴스 식별자와 정확히 일치
- `model_name_or_path` — 보고서에 모델 이름이 들어가는 용도
- `model_patch` — **valid unified diff** 문자열 (markdown 펜스·설명 금지)

> 본 프로젝트는 `runners/swebench_run.py`가 로컬 OpenAI 호환 서버(furiosa-llm 또는 vllm)에 oracle 텍스트를 보내고 `extract_diff`로 diff만 추려서 이 포맷으로 자동 저장한다.

#### 5단계. 채점 실행

```bash
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path predictions.jsonl \
    --max_workers 8 \
    --namespace swebench \
    --cache_level env \
    --run_id my_first_eval
```

**주요 플래그**:

| 플래그 | 의미 | 권장값 |
|---|---|---|
| `--dataset_name` | 채점에 쓸 데이터셋 | `princeton-nlp/SWE-bench_Lite` (추론과 일치) |
| `--predictions_path` | jsonl 경로. 특수값 `gold`는 정답 patch | 직접 만든 jsonl |
| `--max_workers` | 동시 컨테이너 수 | CPU/16, 메모리/8GB 중 작은 값 |
| `--namespace swebench` | Docker Hub의 **prebuilt 이미지를 pull** — 12개 repo × N개 버전 base 이미지를 로컬 빌드하는 수 시간을 절약 | 항상 `swebench` 권장 |
| `--cache_level env` | 환경 이미지까지만 캐시(인스턴스 이미지는 재사용 안 함) | `env`(기본) 또는 `instance`(디스크 더 씀, 재실행 빠름) |
| `--run_id` | 결과 파일명에 들어감 | `<날짜>_<모델>` 같이 식별 가능하게 |
| `--instance_ids ID1 ID2 ...` | 일부만 채점 | 디버깅 시 |

#### 6단계. 결과 읽기

채점이 끝나면 두 파일이 생긴다:

```
<model_name_or_path safe>.<run_id>.json      # 요약 리포트
logs/run_evaluation/<run_id>/<model>/<instance>/   # 인스턴스별 실행 로그
```

요약 리포트 핵심 필드:

```json
{
  "total_instances": 50,
  "submitted_instances": 50,
  "completed_instances": 17,        // patch가 적용되어 테스트까지 돈 수
  "resolved_instances": 0,          // 이슈 해결한 수 (resolved=만점)
  "unresolved_instances": 17,       // 적용됐으나 테스트 실패
  "empty_patch_instances": 0,       // 빈 patch
  "error_instances": 33,            // patch apply 실패 (malformed diff 등)
  "resolved_ids": [],
  "unresolved_ids": ["..."],
  "error_ids": ["..."]
}
```

**resolved 비율** = `resolved_instances / total_instances` — 이게 모델 점수.

#### 7단계. 막혔을 때 디버깅 순서

1. **gold로 다시 검증** — 환경이 깨진 건지 모델 문제인지 분리
2. **error 인스턴스 하나 골라 로그 보기** — `logs/run_evaluation/<run_id>/<model>/<instance>/test_output.txt` / `report.json`
3. **invalid patch면 모델 응답 본문 확인** — markdown 펜스·설명문이 섞였는지, `---`/`+++`/`@@` 줄이 있는지
4. **Docker 컨테이너 만들 때 OOM 나면** — `--max_workers` 줄이기 (각 워커가 수 GB 사용)
5. **인스턴스 이미지 pull 실패** — `docker pull swebench/sweb.eval.x86_64.<repo>__<instance>:latest` 수동 시도

### 5.4 변형 / 더 어려운 평가

| 데이터셋 | 사용 시점 |
|---|---|
| `SWE-bench_Lite` (300) | **처음 평가** — 비용·시간 적당 |
| `SWE-bench_Verified` (500) | 신뢰도 최상 — 사람이 "해결 가능 + 테스트 공정"을 검증 |
| `SWE-bench` (2,294) | 종합 점수 비교 — 시간 많이 듬 |
| `SWE-bench_Multimodal` (517) | 비전 LLM (JS/UI) |
| `SWE-bench_Multilingual` (300) | 비-Python |

### 5.5 본 프로젝트에서 한 줄 실행

자동화된 본 프로젝트 파이프라인에서는 위 4·5단계가 한 줄로 끝난다:

```bash
# NPU
cd rngd-npu && SWEBENCH_N=50 python orchestrator.py configs/models.yaml --tasks swebench
bash eval_swebench.sh

# GPU
cd bench-gpu && SWEBENCH_N=50 python orchestrator.py configs/models.yaml --tasks swebench
bash eval_swebench.sh
```

데이터셋·context 방식·channel별 세부 작동 원리는 [`bench-gpu/README.md §7`](bench-gpu/README.md#7-swe-bench-lite-깊이-분석--llm을-어떻게-채점하나) 참조.

---

## 6. 결과·리포트 보는 법

각 폴더의 `REPORT.md`가 자동 생성되는 8-섹션 비교 리포트다:

1. **TL;DR** — 모델별 핵심 지표 한 표
2. **단일 요청 토큰 속도** (`tps`)
3. **배치/동시성 스케일링** (`sweep`, prompt_len=1024 기준)
4. **serve 옵션 스윕** (`memsweep`)
5. **SWE-bench** — resolved / unresolved / error / 빈 패치 / 컨텍스트 제외 카운트
6. **Embedding / Reranker** — batch별 throughput
7. **GPU/NPU & 동시 접속자별 권장 서빙 설정**
8. **종합 점수** — `정확도 0.5 + peak TPS 0.3 + 단일 TPS 0.2` 가중합

원본 데이터:

```bash
# CSV로 모든 task 결과 일괄 export
python analyze.py --csv all.csv

# 종합 리포트 다시 생성
python report.py
```

---

## 다음 단계

- NPU 실행 → [`rngd-npu/README.md`](rngd-npu/README.md)
- GPU 실행 → [`bench-gpu/README.md`](bench-gpu/README.md)
- SWE-bench 깊이 이해 → [`bench-gpu/README.md §7`](bench-gpu/README.md#7-swe-bench-lite-깊이-분석--llm을-어떻게-채점하나)
- 발표 자료 → [`ppt/RNGD_Benchmark.pdf`](ppt/RNGD_Benchmark.pdf)
