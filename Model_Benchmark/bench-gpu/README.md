# NVIDIA GPU 코드 생성 모델 벤치마크 (vLLM)

RNGD NPU에서 수행한 측정(**토큰 속도 · 동시성 스케일링 · serve 옵션 · SWE-bench · 임베딩/리랭커**)을
**NVIDIA GPU + vLLM** 위에서 그대로 재현해 NPU와 동일 축으로 비교하기 위한 자동화 폴더.
이 폴더 하나만 GPU 서버에 복사하면 끝난다 — `setup.sh`가 모든 의존성을 깐다.

> **사용 하드웨어**: RTX A6000 48GB ×3 중 GPU 2를 사용 (`cuda_visible_devices: "2"` in `configs/models.yaml`).
> GPU 0·1은 타작업이 점유 중이라 비워 둔다. 96GB 클래스로 올리면 70B FP16도 1장에 적재 가능.

전제: **NVIDIA 드라이버만** 설치돼 있으면 됨(`nvidia-smi` 동작). vLLM·PyTorch·CUDA 휠·swebench는 `setup.sh`가 깐다.

---

## 목차

1. [빠른 시작](#1-빠른-시작)
2. [폴더 구조](#2-폴더-구조)
3. [측정 태스크 — 무엇을 왜 재나](#3-측정-태스크--무엇을-왜-재나)
4. [모델 설정](#4-모델-설정--configsmodelsyaml)
5. [실행 단계](#5-실행-단계)
6. [결과 보기](#6-결과-보기)
7. **[SWE-bench Lite 깊이 분석 — LLM을 어떻게 채점하나](#7-swe-bench-lite-깊이-분석--llm을-어떻게-채점하나)**
8. [RNGD 버전과의 차이](#8-rngd-버전과의-차이)
9. [트러블슈팅](#9-트러블슈팅)

---

## 1. 빠른 시작

```bash
# 0. 이 폴더를 GPU 서버로 복사
scp -r bench-gpu/  user@gpu-server:~/        # 또는 git/rsync

# 1. 환경 구축 (한 번만 — vLLM 0.10.0 cu126 휠 + torch + swebench 설치, 수 분)
cd ~/bench-gpu
bash setup.sh

# 2. 가상환경 활성화 (이후 매 세션)
source .venv/bin/activate

# 3. gated 모델(meta-llama/*) 쓸 때만 — HF 토큰 로그인
hf auth login

# 4. 점검 → 전체 측정 → 리포트
bash preflight.sh
./run_all.sh                    # 측정 종료 후 REPORT.md 자동 생성
```

장시간 실행은 백그라운드 권장:

```bash
nohup ./run_all.sh > results/_run_logs/run.log 2>&1 &
tail -f results/_run_logs/run.log
```

---

## 2. 폴더 구조

```
bench-gpu/
├── setup.sh              # 프레시 서버 환경 구축 (한 번)
├── preflight.sh          # GPU/vLLM/Docker/모델 점검
├── run_all.sh            # 전체 파이프라인 (STAGE 단계별)
├── eval_swebench.sh      # SWE-bench Docker 채점 드라이버
├── requirements.txt      # vllm 0.10.0+cu126 휠 고정 + 측정 의존성
├── orchestrator.py       # 모델 × 태스크 자동 실행 (vllm serve 라이프사이클)
├── analyze.py            # 결과 집계 / CSV
├── report.py             # 종합 리포트 → REPORT.md
├── swebench_eval.py      # 예측 jsonl → Docker harness 채점 드라이버
├── configs/
│   └── models.yaml       # 모델 목록 + vllm serve 인자 + sweep/memsweep grid
├── runners/
│   ├── server.py         # VllmServer — vllm serve 라이프사이클 / health 대기 / 정리
│   ├── tps.py            # TTFT·ITL·합산 TPS 측정 (stream)
│   ├── memory_sweep.py   # serve 옵션 OFAT 스윕 (서버 재기동 반복)
│   ├── embed_bench.py    # 임베딩/리랭커 throughput
│   └── swebench_run.py   # SWE-bench 추론 (oracle 프롬프트 + 컨텍스트 필터 + patch sanity)
├── docs/
│   └── SWEBENCH_SETUP.md # SWE-bench 설치/포맷/채점 명령 레퍼런스
└── results/              # 측정 결과 (자동 생성)
    ├── <model_safe>/
    │   ├── tps/<timestamp>.json
    │   ├── sweep/<timestamp>.json
    │   ├── memsweep/<n>.json + memsweep_summary.json
    │   └── swebench/
    │       ├── swebench_<ts>.json       # 추론 단계 요약
    │       ├── preds/<model>__preds.jsonl
    │       ├── eval_result.json         # harness 채점 결과
    │       └── logs/                    # Docker harness 인스턴스 로그
    ├── _server_logs/                    # vllm serve stderr
    └── _run_logs/                       # run_all.sh 단계별 로그
```

---

## 3. 측정 태스크 — 무엇을 왜 재나

| 태스크 | 무엇을 재나 | 왜 재나 | 산출 핵심 지표 |
|---|---|---|---|
| `tps` | concurrency=1, 단일 요청을 stream으로 받아 TTFT·ITL·출력 TPS | **사용자 1명 체감 속도**. 첫 토큰까지 얼마나 빠른가, 토큰이 얼마나 부드럽게 흐르는가 | `ttft_s_p50/p95`, `itl_s_p50`, `output_tps_per_request_p50` |
| `sweep` | concurrency × prompt_len 매트릭스 (1~128 동시성, prompt 256/1024/4096) | **동시 사용자 N명 처리량**. 어디서 saturate되고 어디서 latency가 SLA를 넘는가 | `aggregate_output_tps`, `failures` |
| `memsweep` | `--max-model-len` · `--max-num-seqs` · `--gpu-memory-utilization` OFAT 스윕 | 기본값이 정말 최적인가, 메모리·KV 캐시·배치 한도를 만지면 처리량이 얼마나 움직이는가 | combo별 `aggregate_output_tps` |
| `swebench` | SWE-bench Lite oracle + single-shot으로 코드 패치 생성 → Docker harness 채점 | **모델이 실제로 코드를 고칠 수 있는가**. 속도가 빨라도 정확도가 0이면 의미 없다 | `resolved` / `total` |
| `embed` | `/v1/embeddings`로 batch=1/4/16/64 throughput | **RAG·시멘틱 검색**의 대표 부하 — embedding 모델 비교용 | `throughput_inputs_per_s`, `p50/p95_latency_s` |
| `rerank` | `/v1/rerank` (지원 안 하면 임베딩+코사인 fallback) | RAG 파이프라인의 rerank 단계 부하 | `throughput_pairs_per_s` |

> **읽는 순서**: `tps`(개인 속도) → `sweep`(다중 사용자) → `memsweep`(튜닝 여지) → `swebench`(정확도). 정확도가 0이면 다른 지표는 의미가 줄어든다.

### 측정 의도

- **속도 ≠ 품질**: 0.5B 모델은 단일 TPS가 250, 8B는 42지만 SWE-bench resolved는 둘 다 0%. 작은 모델은 **빠르고 멍청**하다는 사실을 수치로 보여준다.
- **batch 효율**: `sweep`은 "GPU가 한 번에 몇 명을 받아도 처리량이 줄지 않는가"를 본다. 90% peak에 도달하는 동시성을 **효율 배치(efficient_c)** 로 정의한다(`report.py` `EFFICIENT_FRAC=0.90`).
- **memsweep은 OFAT**: baseline에서 한 축씩 움직인다. 그리드 전수가 아니라 "옵션 하나당 영향"을 본다 — 결합 효과는 보지 못하지만 디버깅이 쉽다.
- **SWE-bench oracle**: "올바른 파일이 주어졌을 때 패치를 만들 수 있는가"를 본다. 검색 능력은 빠지고 **순수 코드 편집 능력**만 측정 → NPU/GPU 비교에서 인프라 변수를 줄이려는 목적.

---

## 4. 모델 설정 — `configs/models.yaml`

`id`는 Hugging Face 모델 id (원본 HF 모델 — RNGD prebuilt 아티팩트가 아님). 기본 활성:

| 모델 | 역할 | 비고 |
|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct` | smoke + 비교 baseline | 파이프라인 검증 + 작은 모델 속도 상한 |
| `meta-llama/Llama-3.1-8B-Instruct` | baseline | gated — `hf auth login` 필수 |

기본 비활성(`enabled: false`) — 켜려면 yaml에서 `true`로:

| 모델 | 켜는 조건 |
|---|---|
| `Qwen/Qwen3-32B` | bf16 ~64GB > A6000 48GB 1장 → `--quantization fp8` 또는 `--tensor-parallel-size 2` 필요 |
| `meta-llama/Llama-3.3-70B-Instruct` | bf16 ~140GB → `--quantization fp8` (이미 yaml에 포함) 또는 다중 GPU |
| `LGAI-EXAONE/EXAONE-4.0-32B` | 라이선스 확인 후 enable. 커스텀 코드면 `--trust-remote-code` |
| `Qwen/Qwen3-Embedding-8B` | vLLM 0.21 기준 `--runner pooling` 필요 |
| `Qwen/Qwen3-Reranker-8B` | vLLM 0.21은 `--task score`만 가능 / pooling+jinja 템플릿 셋업 필요 |

**새 모델 추가**: `models:` 리스트에 항목 추가 (`id`/`role`/`gen`/`enabled`/`serve_args`). 측정 코드 수정 불필요.

**다중 GPU**: yaml 최상단 `cuda_visible_devices: "0,1"` + 해당 모델 `serve_args`에 `["--tensor-parallel-size","2"]`.

### sweep / memsweep grid

```yaml
sweep:
  batch_sizes: [1, 2, 4, 8, 16, 32, 64, 128]
  prompt_lens: [256, 1024, 4096]
  max_tokens: 256
  warmup_requests: 5
  measured_requests: 50

memsweep:
  baseline: {}
  axes:
    max_model_len: [4096, 8192, 16384]
    max_num_seqs: [64, 256]
    gpu_memory_utilization: [0.85, 0.95]
```

---

## 5. 실행 단계

`run_all.sh`는 단계로 나뉜다 — 환경변수 `STAGE`로 부분 실행 가능.

| STAGE | 내용 |
|---|---|
| `preflight` | GPU·vLLM·torch CUDA·Docker·HF 모델 가용성 점검 |
| `smoke` | `preflight` + Qwen2.5-0.5B tps 1회 (~30s, 파이프라인 검증) |
| `gen` | `preflight` + `smoke` + 모든 생성 모델 tps/sweep/memsweep |
| `embed` | embedding/reranker 측정 |
| `swebench` | SWE-bench 추론 + Docker 채점 (Docker 필요) |
| `report` | `analyze.py` + `report.py` → CSV + REPORT.md |
| `all` (기본) | preflight → smoke → gen → embed → swebench → report |

```bash
# 단계별 실행
STAGE=smoke ./run_all.sh
STAGE=gen ./run_all.sh

# 특정 모델/태스크만 (모델은 substring 매칭)
python orchestrator.py configs/models.yaml --tasks tps,sweep --models Llama-3.1-8B

# 무엇이 실행될지 미리보기
python orchestrator.py configs/models.yaml --tasks tps --dry-run
```

### SWE-bench 환경변수 (orchestrator의 `swebench` 태스크)

| 변수 | 기본값 | 의미 |
|---|---|---|
| `SWEBENCH_DATASET` | `princeton-nlp/SWE-bench_Lite_oracle` | 추론용 oracle 데이터셋 (text 컬럼에 프롬프트 prebuilt) |
| `SWEBENCH_N` | `50` | 추론 인스턴스 수 (repo별 stratified). `0` 또는 미설정 시 전체 300 |
| `SWEBENCH_MAXTOK` | `1024` | 응답 max_tokens |
| `SWEBENCH_CONC` | `8` | 동시 추론 요청 수 |
| `SWEBENCH_FILTER_CONTEXT` | `1` | 서버 max_model_len 초과 인스턴스 사전 제외 |
| `SWEBENCH_MAX_INPUT_TOKENS` | (자동) | 입력 토큰 상한 override |
| `SWEBENCH_DROP_INVALID_PATCH` | `0` | 형식상 깨진 diff를 빈 패치로 저장 |
| `SWEBENCH_RETRY_INVALID` | `0` | 깨진 diff 재생성 횟수 |

예: 전체 300건을 8동시로:

```bash
SWEBENCH_N=300 python orchestrator.py configs/models.yaml --tasks swebench
bash eval_swebench.sh
```

---

## 6. 결과 보기

```bash
python analyze.py                   # task별 결과 표 (stdout)
python analyze.py --csv out.csv     # CSV
python report.py                    # 종합 리포트 → REPORT.md
```

원본 데이터 경로:
- 측정 JSON: `results/<model_safe>/<task>/<timestamp>.json`
- 서버 로그: `results/_server_logs/<model_safe>_<ts>.log`
- 단계 로그: `results/_run_logs/{preflight,smoke,gen,embed,swebench,report}.log`

`REPORT.md` 8 섹션: TL;DR → 단일 TPS → 스케일링 → memsweep → SWE-bench → embed/rerank → 권장 서빙 → 종합 점수.

### 종합 점수(`report.py` §8) 공식

```
score = 0.5 * (SWE-bench_resolved% / max)      # 정확도
      + 0.3 * (peak_aggregate_TPS / max)        # 다중 사용자 처리량
      + 0.2 * (single_TPS / max)                # 단일 사용자 속도
```

(embedding/reranker·smoke 모델은 점수 계산에서 제외)

---

## 7. SWE-bench Lite 깊이 분석 — LLM을 어떻게 채점하나

> 데이터셋 출처: [huggingface.co/datasets/SWE-bench/SWE-bench_Lite](https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite)
> 논문: [Jimenez et al. 2023 — *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?*](https://arxiv.org/abs/2310.06770)

### 7.1 한 줄 요약

SWE-bench Lite는 **실제 GitHub 이슈를 LLM이 코드 패치로 해결할 수 있는지**를, **실제 테스트 슈트로** 채점하는 벤치마크다.
객관식이 아니다. "이 코드 잘 짠 것 같아요"식 LLM-as-judge도 아니다. **모델이 만든 patch를 진짜 repo에 apply하고, 진짜 pytest를 돌려서, 그 결과로 점수가 매겨진다.**

### 7.2 데이터셋 구조

- **분할**: test 300건 + dev 23건 = 총 323건 (`load_dataset("princeton-nlp/SWE-bench_Lite", split="test")`)
- **소스**: 11개 인기 Python repo (django, flask, sympy, scikit-learn, matplotlib, sphinx, pytest, requests, xarray, astropy, pylint 등)
- **포맷**: parquet, 1.22 MB. 코드 자체는 데이터셋에 없고 `repo` + `base_commit`으로 GitHub에서 가져온다.

각 인스턴스가 가진 컬럼:

| 컬럼 | 내용 | 누가 쓰나 |
|---|---|---|
| `instance_id` | `astropy__astropy-12907` 형식의 식별자 | 모델 입력·채점 매칭 |
| `repo` | `astropy/astropy` | Docker 이미지 선택 |
| `base_commit` | 해당 이슈 발생 시점의 commit SHA | repo checkout |
| `problem_statement` | 이슈 제목 + 본문 (원문 그대로) | **모델 프롬프트** |
| `hints_text` | 이슈에 달린 사전 코멘트 (PR 전) | 보조 컨텍스트 (보통 미사용) |
| `patch` | 사람이 만든 정답 PR 코드 patch (테스트 제외) | 채점 비교용·oracle context |
| `test_patch` | 정답 PR에 포함된 테스트 patch | **채점**에 적용 |
| `FAIL_TO_PASS` | 패치 전 fail → 패치 후 pass여야 하는 테스트 목록 (JSON) | **resolved 판정** |
| `PASS_TO_PASS` | 패치 전후 모두 pass여야 하는 테스트 목록 | **회귀 판정** |
| `version` | 환경 셋업에 쓸 repo 버전 | Docker 이미지 빌드 |
| `environment_setup_commit` | 환경 셋업용 commit | venv·apt 의존성 결정 |

### 7.3 모델에게 주는 입력 / 받는 출력

**입력** (본 측정이 사용한 oracle 변형 기준):
- 시스템 프롬프트: "expert software engineer. produce one valid unified diff patch."
- 사용자 프롬프트(`text` 컬럼): `problem_statement` + **정답 patch가 수정한 파일들의 원문** + 패치 형식 가이드

**출력**: **unified diff** 한 덩어리. 예:

```diff
diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py
--- a/astropy/modeling/separable.py
+++ b/astropy/modeling/separable.py
@@ -242,8 +242,8 @@ def _separable(transform):
-        return _coord_matrix(transform, 'left', transform.n_outputs)
+        return _separable_compound(transform)
```

본 프로젝트는 `swebench.inference.make_datasets.utils.extract_diff`로 응답에서 diff 블록만 추출하고,
`runners/swebench_run.py::_patch_sanity_error`로 unified diff 구조 검증(`---`/`+++`/`@@` header, hunk 라인 카운트 일치)을 한 번 더 한다.

### 7.4 컨텍스트 제공 방식 — oracle vs BM25 vs full

| 변형 | 모델이 보는 것 | 무엇을 측정하나 |
|---|---|---|
| `oracle` | 정답 patch가 건드린 파일을 통째로 제공 | **순수 코드 편집·생성** — "올바른 파일이 있을 때 패치를 만들 수 있나" |
| `bm25_13K` / `27K` / `40K` | BM25로 이슈와 관련 있는 파일을 N토큰 한도까지 검색해 제공 | 편집 + **검색** 능력 |
| `full` | repo 전체 | 편집 + 검색 + 긴 컨텍스트 처리 |

**본 측정은 `oracle` 사용** — 이유: NPU vs GPU 비교에서 검색 품질(embedding 모델 차이, BM25 인덱스 노이즈)이 변수로 들어오지 않게 하려는 것. "인프라가 같은 패치 생성 작업을 얼마나 빠르고 정확하게 처리하는가"만 본다.

대응 HF 데이터셋: `princeton-nlp/SWE-bench_Lite_oracle` (text 컬럼에 프롬프트 prebuilt).

### 7.5 실행 방식 — single-shot vs agentic

| 방식 | 흐름 | 본 측정 |
|---|---|---|
| **single-shot** | 1회 API 호출 → diff 1개 | ✅ 사용 |
| **agentic** | LLM이 repo 탐색·편집·테스트·재시도 반복 (SWE-agent, Aider 등) | ❌ 미사용 |

리더보드 상위 점수는 거의 다 agentic이다. single-shot은 **모델 자체 능력의 lower bound**를 본다 — agent 프레임워크 변수 없이 모델만 평가.

### 7.6 채점 메커니즘 — `FAIL_TO_PASS` / `PASS_TO_PASS`

Docker 컨테이너 안에서 다음 순서로 실행된다:

```
1. base_commit으로 repo checkout
2. environment_setup_commit 기준으로 venv·apt 의존성 설치
3. test_patch 적용 → 이슈 검증용 테스트 추가
4. model_patch 적용 → 모델이 만든 코드 변경 시도
5. FAIL_TO_PASS + PASS_TO_PASS 테스트 전부 실행
6. 결과 비교
```

**resolved 조건** (둘 다 만족해야 1점):
- 모든 `FAIL_TO_PASS` 테스트가 **pass** (이슈가 실제로 해결됐다)
- 모든 `PASS_TO_PASS` 테스트가 **pass** (기존 기능을 부수지 않았다)

이 중 하나라도 어기면 카테고리로 분류:

| 결과 | 의미 | 자주 보이는 케이스 |
|---|---|---|
| `resolved` | 위 두 조건 모두 OK | 만점 |
| `unresolved` | patch는 적용됐지만 테스트 실패 | 코드는 변경됐으나 이슈 미해결 / 회귀 발생 |
| `error` | patch apply 실패 (malformed diff, 잘못된 파일 경로 등) | **0.5B 모델이 가장 많이 막히는 지점** |
| `empty_patch` | 모델이 빈 출력 | "모르겠음" |

본 측정 결과(50건 subset 기준 — `bench-gpu/REPORT.md` 참조):
- Qwen2.5-0.5B-Instruct: resolved 0 / unresolved 1 / **error 42** / 컨텍스트 제외 7 → 0%
- Llama-3.1-8B-Instruct: resolved 0 / unresolved 17 / error 33 → 0%

→ 두 모델 모두 0%지만 **error vs unresolved 비율**이 의미 있다. 8B는 적어도 "구조적으로 올바른 diff"를 17건 만들었고, 0.5B는 대부분 diff 문법조차 못 맞춘다.

### 7.7 변형 데이터셋 비교

| 데이터셋 | 인스턴스 | 특징 | 용도 |
|---|--:|---|---|
| `SWE-bench` (full) | 2,294 | 12개 Python repo 전체 | 원본·종합 평가 |
| `SWE-bench_Lite` | **300** | 자체 완결적 버그만 큐레이션 | **저비용 평가용 (본 측정)** |
| `SWE-bench_Verified` | 500 | 사람이 "해결 가능하고 테스트가 공정함"을 검증 | 신뢰도 최상 |
| `SWE-bench_Multimodal` | 517 | JS/UI (시각 요소 포함) | 비전 LLM |
| `SWE-bench_Multilingual` | 300 | 비-Python | 다언어 LLM |

`Lite`를 고른 이유: 300건이라 8시간 안에 전체 추론·채점이 끝나고, 자체 완결적 버그만 모여 있어 single-shot oracle 평가에 적합하다.

### 7.8 본 측정에서 본 한계와 우회

| 한계 | 우회 |
|---|---|
| `swebench.inference.run_api`는 OpenAI/Anthropic 모델명에 하드코딩(`MODEL_LIMITS`) | 자체 추론 루프 작성 (`runners/swebench_run.py`) — 로컬 OpenAI 호환 서버로 직접 호출 |
| Lite 인스턴스 중 일부는 oracle text가 모델 max_model_len을 초과 | `_filter_by_context`로 server `/models`에서 max_model_len 읽어 사전 제외 → `n_filtered_context`로 카운트 |
| 모델이 markdown fence/설명을 섞어 보내 patch apply 실패 | `extract_diff` + `_patch_sanity_error`로 diff만 추출 + 구조 검증 |
| 작은 모델은 매번 깨진 diff 생성 | `SWEBENCH_RETRY_INVALID=N`으로 N회 재생성 가능 (기본 0 — single-shot 유지) |

### 7.9 본 측정 구성 한 줄 요약

> **dataset**: `princeton-nlp/SWE-bench_Lite_oracle`  ·  **subset**: repo별 stratified 50건
> **mode**: single-shot · temperature=0.0 · max_tokens=1024 · concurrency=8
> **grading**: `swebench.harness.run_evaluation` (Docker, `--namespace swebench` prebuilt 이미지 pull)

---

## 8. RNGD 버전과의 차이

| 항목 | RNGD (`rngd-npu/`) | GPU (이 폴더) |
|---|---|---|
| 서빙 | `furiosa-llm serve` | `vllm serve` |
| 모델 | furiosa prebuilt 아티팩트 (`furiosa-ai/*`) | 원본 HF 모델 |
| 디바이스 | NPU PE 고정 (tp 컴파일됨, `--devices npu:0`) | `CUDA_VISIBLE_DEVICES` + `--tensor-parallel-size` 자유 |
| serve 옵션 (memsweep) | `max-batch-size`, `max-num-batched-tokens` | `max-model-len`, `max-num-seqs`, `gpu-memory-utilization` |
| 측정 러너 | 동일 — OpenAI 호환 API 공유 | 동일 — `tps/sweep/swebench/embed` 코드 공유 |
| SWE-bench 흐름 | 동일 (`runners/swebench_run.py` 공유) | 동일 |

서버 계층만 다르고 측정 코드는 100% 공유한다 — 측정 축이 같아 NPU/GPU 결과를 직접 비교 가능.

---

## 9. 트러블슈팅

| 증상 | 조치 |
|---|---|
| `nvidia-smi` 없음 | NVIDIA 드라이버 설치 후 재부팅. Ubuntu: `sudo apt-get install -y nvidia-driver-560` |
| vLLM import 실패 | `setup.sh` 재실행. `requirements.txt`가 vLLM 0.10.0+cu126 휠을 고정 — 드라이버 575+로 올리면 더 최신 vLLM 가능 |
| `cudaErrorInsufficientDriver(35)` 샘플링 단계 | `run_all.sh`가 이미 `VLLM_USE_FLASHINFER_SAMPLER=0` 설정. flashinfer가 더 새 CUDA로 빌드돼 발생 |
| vLLM 기동 OOM | 모델 `serve_args`에 `--max-model-len 8192` 또는 `--gpu-memory-utilization 0.85` 추가 |
| gated 모델 403 | `hf auth login` + HuggingFace 웹에서 모델 페이지 라이선스 동의 |
| 70B 안 올라감 | `--quantization fp8` (이미 yaml에 포함) 또는 다중 GPU `--tensor-parallel-size 2` |
| 서버 기동 실패 일반 | `results/_server_logs/<model_safe>_*.log` 확인 |
| SWE-bench 채점 단계 멈춤 | Docker 필요 — `docker info` 확인. 첫 실행은 prebuilt 이미지 pull로 수십 GB 다운로드 |
| 임베딩/리랭커 task 오류 | vLLM 버전별 task 인자 차이 — 0.21은 `--runner pooling`, 이전은 `--task embed/score` |
| `transformers` AttributeError | `requirements.txt`가 `transformers==4.53.2`로 고정. 최신으로 올리지 말 것 (vLLM 0.10.0과 토크나이저 API 불일치) |

추가 SWE-bench 환경 셋업·트러블슈팅은 [`docs/SWEBENCH_SETUP.md`](docs/SWEBENCH_SETUP.md).
