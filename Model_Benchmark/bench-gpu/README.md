# NVIDIA GPU 코드 생성 모델 벤치마크 (vLLM)

RNGD NPU에서 했던 측정(토큰 속도, 동시성 스케일링, 서버 옵션, SWE-bench, 임베딩·리랭커)을
NVIDIA GPU와 vLLM 위에서 똑같이 재현하는 폴더입니다. NPU와 같은 기준으로 비교하기 위한 것입니다.
이 폴더 하나만 GPU 서버에 복사하면 `setup.sh`가 필요한 것을 모두 설치합니다.

측정에는 RTX A6000 48GB 3장 중 2번 GPU를 씁니다(`configs/models.yaml`의 `cuda_visible_devices: "2"`).
0번과 1번은 다른 작업이 쓰고 있어 비워 둡니다. 전제 조건은 NVIDIA 드라이버 설치뿐이고
(`nvidia-smi`가 동작하면 됩니다), vLLM과 PyTorch, CUDA 휠, swebench는 `setup.sh`가 설치합니다.

## 빠른 시작

```bash
# 이 폴더를 GPU 서버로 복사
scp -r bench-gpu/  user@gpu-server:~/

# 환경 구축 (한 번만, 수 분 소요)
cd ~/bench-gpu
bash setup.sh

# 가상환경 활성화 (이후 매번)
source .venv/bin/activate

# 접근 제한 모델(meta-llama/*)을 쓸 때만
hf auth login

# 점검하고 전체 측정
bash preflight.sh
./run_all.sh
```

오래 걸리는 측정은 백그라운드로 돌리는 편이 낫습니다.

```bash
nohup ./run_all.sh > results/_run_logs/run.log 2>&1 &
tail -f results/_run_logs/run.log
```

## 폴더 구조

```
bench-gpu/
├── setup.sh              환경 구축 (한 번)
├── preflight.sh          GPU·vLLM·Docker·모델 점검
├── run_all.sh            전체 측정 파이프라인
├── eval_swebench.sh      SWE-bench 채점
├── requirements.txt      vllm 0.10.0+cu126 휠 고정
├── orchestrator.py       모델별로 테스트를 자동 실행
├── analyze.py            결과 모아서 표로 정리
├── report.py             종합 리포트(REPORT.md) 생성
├── swebench_eval.py      예측 파일을 Docker로 채점
├── configs/
│   └── models.yaml       모델 목록, 서버 인자, 측정 설정
├── runners/
│   ├── server.py         vllm serve 띄우고 내리는 관리
│   ├── tps.py            첫 토큰 지연, 토큰 간격, 처리량 측정
│   ├── memory_sweep.py   서버 옵션을 바꿔가며 측정
│   ├── embed_bench.py    임베딩·리랭커 처리량 측정
│   └── swebench_run.py   SWE-bench 추론
├── docs/
│   └── SWEBENCH_SETUP.md SWE-bench 설치와 채점 명령 정리
└── results/              측정 결과 (자동 생성)
    ├── <모델>/
    │   ├── tps/
    │   ├── sweep/
    │   ├── memsweep/
    │   └── swebench/
    ├── _server_logs/     vllm serve 로그
    ├── _run_logs/        단계별 실행 로그
    └── _archive_pre_match/   조건 정렬 전 측정 보관
```

## 측정 항목

다섯 가지를 측정합니다.

| 항목 | 측정 내용 | 보는 것 |
|---|---|---|
| tps | 요청 한 건을 보내며 첫 토큰 지연, 토큰 간격, 출력 속도 측정 | 사용자 한 명의 체감 속도 |
| sweep | 동시 요청 1~128명, 프롬프트 길이 256/1024/4096 조합 측정 | 동시 사용자를 받는 처리량 |
| memsweep | 서버 옵션을 한 번에 하나씩 바꿔가며 처리량 측정 | 옵션 튜닝의 효과 |
| swebench | SWE-bench Lite로 코드 패치를 만들고 Docker로 채점 | 실제 코드 수정 능력 |
| embed | 임베딩 모델의 배치별 처리량 측정 | 검색 단계 부하 |
| rerank | 리랭커 모델의 처리량 측정 | 검색 순위 매기기 부하 |

읽는 순서는 tps(개인 속도), sweep(다중 사용자), memsweep(튜닝 여지), swebench(정확도)입니다.
정확도가 0이면 다른 지표의 의미가 줄어듭니다.

몇 가지 측정 의도를 적어둡니다. 속도가 빠르다고 품질이 좋은 것은 아닙니다. 0.5B 모델은 단일 속도가
250 tok/s나 되지만 SWE-bench 점수는 0%입니다. 작고 빠른 모델이 정확하지는 않다는 것을 수치로 보여주려는
것입니다. sweep은 GPU가 동시 사용자를 늘려도 처리량이 떨어지지 않는 구간을 봅니다. peak의 90%에
도달하는 동시성을 효율 배치로 정의합니다(`report.py`의 `EFFICIENT_FRAC`). memsweep은 한 번에 한 옵션만
바꾸는 방식이라 옵션 하나하나의 효과는 보지만 옵션끼리의 상호작용은 보지 못합니다. 대신 결과 해석이
쉽습니다. SWE-bench는 고칠 파일을 미리 알려주는 oracle 방식을 써서, 검색 능력은 빼고 순수한
코드 편집 능력만 봅니다. NPU와 GPU를 비교할 때 변수를 줄이려는 것입니다.

## 모델 설정 (configs/models.yaml)

기본으로 켜져 있는 모델은 두 개입니다.

| 모델 | 역할 | serve_args |
|---|---|---|
| Qwen/Qwen2.5-0.5B-Instruct | 동작 확인용 | `--port 8001 --max-model-len 4096` |
| meta-llama/Llama-3.1-8B-Instruct | 코드 생성 후보 | `--max-model-len 32768 --tool-call-parser llama3_json` |

`--max-model-len`은 NPU prebuilt 모델의 컨텍스트 한도에 맞춘 값입니다. Qwen은 4,096(NPU 모델의
실행 한도), Llama는 32,768(NPU 모델 문서의 최대 컨텍스트)입니다. `--tool-call-parser`와
`--enable-prefix-caching`도 NPU 쪽 furiosa-llm 서버 인자와 똑같이 맞췄습니다. 이렇게 해야
NPU와 GPU 결과를 같은 표에서 비교할 수 있습니다. 자세한 내용은
[../README_npu_gpu_result.md](../README_npu_gpu_result.md)에 있습니다.

기본으로 꺼져 있는 모델은 필요할 때 yaml에서 `enabled: true`로 바꿉니다.

| 모델 | 켤 때 필요한 것 |
|---|---|
| Qwen/Qwen3-32B | bf16로 약 64GB라 A6000 한 장에 안 들어감. `--quantization fp8` 또는 GPU 2장 |
| meta-llama/Llama-3.3-70B-Instruct | bf16로 약 140GB. FP8 양자화 필요 (yaml에 이미 포함) |
| LGAI-EXAONE/EXAONE-4.0-32B | 라이선스 확인 후. 커스텀 코드면 `--trust-remote-code` |
| Qwen/Qwen3-Embedding-8B | vLLM 0.21 기준 `--runner pooling` 필요 |
| Qwen/Qwen3-Reranker-8B | vLLM 0.21에서는 `--task score`, pooling과 템플릿 설정 필요 |

새 모델을 추가하려면 `models:` 목록에 항목을 넣기만 하면 됩니다. 측정 코드는 건드릴 필요가 없습니다.
GPU를 여러 장 쓰려면 yaml 위쪽 `cuda_visible_devices`를 `"0,1"` 식으로 바꾸고 해당 모델 serve_args에
`--tensor-parallel-size 2`를 넣습니다.

공통 서버 인자와 측정 설정은 다음과 같습니다.

```yaml
common_serve_args:           # 모든 모델에 적용
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"
  - "--enable-prefix-caching"

sweep:
  batch_sizes: [1, 2, 4, 8, 16, 32, 64, 128]
  prompt_lens: [256, 1024, 4096]   # Qwen은 4K 한도라 4096 항목이 전부 실패함
  max_tokens: 256
  warmup_requests: 5
  measured_requests: 50

memsweep:                    # NPU memsweep과 비교할 수 있게 축을 맞춤
  baseline: {}
  axes:
    max_model_len: [4096, 8192, 16384]
    max_num_seqs: [8, 32]            # NPU의 max_batch_size에 대응
    max_num_batched_tokens: [4096, 16384]
```

`gpu_memory_utilization`은 NPU에 대응하는 옵션이 없어서 비교용 memsweep에서는 뺐습니다.

## 측정 실행

`run_all.sh`는 단계로 나뉘어 있고, `STAGE` 환경변수로 일부만 실행할 수 있습니다.

| STAGE | 내용 |
|---|---|
| preflight | GPU, vLLM, Docker, 모델 접근 가능 여부 점검 |
| smoke | 작은 모델로 tps 한 번 (약 30초, 파이프라인 점검) |
| gen | 생성 모델 tps, sweep, memsweep 측정 |
| embed | 임베딩·리랭커 측정 |
| swebench | SWE-bench 추론과 채점 |
| report | analyze와 report 실행, REPORT.md 생성 |
| all (기본) | 위 전부 |

```bash
STAGE=smoke ./run_all.sh
STAGE=gen ./run_all.sh

# 특정 모델, 특정 항목만 (모델은 이름 일부로 지정)
python orchestrator.py configs/models.yaml --tasks tps,sweep --models Llama-3.1-8B

# 무엇이 실행될지 미리보기
python orchestrator.py configs/models.yaml --tasks tps --dry-run
```

SWE-bench는 환경변수로 범위를 조정합니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| SWEBENCH_DATASET | princeton-nlp/SWE-bench_Lite_oracle | 추론에 쓸 데이터셋 |
| SWEBENCH_N | 50 | 측정할 인스턴스 수. 0이면 전체 300건 |
| SWEBENCH_MAXTOK | 1024 | 응답 최대 토큰 |
| SWEBENCH_CONC | 8 | 동시 추론 요청 수 |
| SWEBENCH_FILTER_CONTEXT | 1 | 컨텍스트 한도를 넘는 인스턴스를 미리 제외 |
| SWEBENCH_RETRY_INVALID | 0 | 형식이 깨진 패치를 다시 만드는 횟수 |

전체 300건을 측정하려면 이렇게 합니다.

```bash
SWEBENCH_N=300 python orchestrator.py configs/models.yaml --tasks swebench
bash eval_swebench.sh
```

## 결과 보기

```bash
python analyze.py                 # 항목별 결과를 표로 출력
python analyze.py --csv out.csv   # CSV로 저장
python report.py                  # 종합 리포트(REPORT.md) 생성
```

측정 원본은 `results/<모델>/<항목>/<시각>.json`에, 서버 로그는 `results/_server_logs/`에,
단계별 로그는 `results/_run_logs/`에 쌓입니다.

`REPORT.md`는 여덟 부분으로 나뉩니다. 핵심 지표 요약, 단일 요청 속도, 동시성 스케일링, 서버 옵션,
SWE-bench, 임베딩·리랭커, 권장 설정, 종합 점수 순입니다. 종합 점수는 정확도(SWE-bench) 0.5,
peak 처리량 0.3, 단일 속도 0.2의 가중합으로 계산하고, 각 지표는 측정 모델 중 최댓값을 기준으로
정규화합니다.

## SWE-bench Lite 자세히 보기

SWE-bench는 이 프로젝트에서 가장 복잡한 테스트라 따로 정리합니다.
데이터셋은 [HuggingFace의 SWE-bench_Lite](https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite),
원 논문은 [Jimenez et al. 2023](https://arxiv.org/abs/2310.06770)입니다.

### 한 줄로 말하면

SWE-bench Lite는 실제 GitHub 이슈를 LLM이 코드 패치로 해결할 수 있는지를 실제 테스트로 채점하는
벤치마크입니다. 객관식이 아니고, "코드가 잘 짜인 것 같다"는 식의 판단도 아닙니다. 모델이 만든 패치를
진짜 저장소에 적용하고, 진짜 pytest를 돌려서, 그 결과로 점수가 매겨집니다.

### 데이터셋 구조

테스트셋 300건과 개발셋 23건, 합쳐서 323건입니다. django, flask, sympy, scikit-learn, matplotlib,
sphinx, pytest, requests, xarray, astropy, pylint 등 인기 있는 파이썬 저장소 11개에서 가져왔습니다.
파일 크기는 1.22MB로 작은데, 코드 자체는 데이터셋에 없고 저장소 주소와 커밋 해시만 들어 있어서
채점할 때 GitHub에서 코드를 받아옵니다.

각 인스턴스가 가진 정보는 이렇습니다.

| 컬럼 | 내용 |
|---|---|
| instance_id | `astropy__astropy-12907` 형식의 식별자 |
| repo | 저장소 이름 (`astropy/astropy`) |
| base_commit | 이슈가 발생한 시점의 커밋 |
| problem_statement | 이슈 제목과 본문. 모델 프롬프트로 들어감 |
| patch | 사람이 만든 정답 패치 (테스트 코드 제외) |
| test_patch | 정답 PR에 들어 있던 테스트 코드 |
| FAIL_TO_PASS | 패치 전에는 실패하고 패치 후 통과해야 하는 테스트 목록 |
| PASS_TO_PASS | 패치 전후 모두 통과해야 하는 테스트 목록 |
| version, environment_setup_commit | 채점 환경을 만들 때 쓰는 정보 |

### 모델에게 주는 입력과 받는 출력

이 프로젝트가 쓰는 oracle 방식에서는, 모델에게 이슈 설명과 함께 정답 패치가 고친 파일들의 원본 코드를
줍니다. 모델은 그 이슈를 해결하는 unified diff를 하나 만들어 돌려줍니다. 예를 들면 이런 형태입니다.

```diff
diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py
--- a/astropy/modeling/separable.py
+++ b/astropy/modeling/separable.py
@@ -242,8 +242,8 @@ def _separable(transform):
-        return _coord_matrix(transform, 'left', transform.n_outputs)
+        return _separable_compound(transform)
```

본 프로젝트는 모델 응답에서 diff 부분만 추려내고(`extract_diff`), diff 구조가 제대로 됐는지
한 번 더 확인합니다(`runners/swebench_run.py`의 `_patch_sanity_error`).

### 컨텍스트를 주는 방식

SWE-bench에는 모델에게 코드를 얼마나 보여주느냐에 따라 세 가지 방식이 있습니다.

| 방식 | 모델이 보는 것 | 측정하는 능력 |
|---|---|---|
| oracle | 정답 패치가 고친 파일을 통째로 줌 | 순수한 코드 편집 능력 |
| bm25 | 검색으로 관련 있어 보이는 파일을 토큰 한도까지 줌 | 편집 능력 + 검색 능력 |
| full | 저장소 전체를 줌 | 편집 + 검색 + 긴 문맥 처리 |

본 프로젝트는 oracle을 씁니다. NPU와 GPU를 비교할 때 검색 품질 같은 변수가 끼어들지 않게 하려는
것입니다. 인프라가 같은 작업을 얼마나 빠르고 정확하게 처리하는지만 봅니다.

### 실행 방식

한 번 호출해서 패치 하나를 받는 single-shot 방식과, 에이전트가 저장소를 탐색하고 수정하고 테스트하기를
반복하는 agentic 방식이 있습니다. 리더보드 상위 점수는 대부분 agentic 방식인데, 본 프로젝트는
single-shot을 씁니다. 에이전트 도구의 영향을 빼고 모델 자체의 능력을 봅니다.

### 채점하는 방법

Docker 컨테이너 안에서 이런 순서로 진행됩니다. 먼저 base_commit으로 저장소를 받고, 환경을 설치하고,
test_patch를 적용해 검증용 테스트를 추가합니다. 그다음 모델이 만든 패치를 적용하고,
FAIL_TO_PASS와 PASS_TO_PASS 테스트를 모두 돌립니다.

해결(resolved)로 인정받으려면 두 조건을 모두 만족해야 합니다. FAIL_TO_PASS 테스트가 전부 통과해서
이슈가 실제로 해결됐고, PASS_TO_PASS 테스트도 전부 통과해서 기존 기능을 망가뜨리지 않았어야 합니다.
하나라도 어기면 결과가 이렇게 나뉩니다.

| 결과 | 의미 |
|---|---|
| resolved | 위 두 조건을 모두 만족. 만점 |
| unresolved | 패치는 적용됐지만 테스트를 통과하지 못함 |
| error | 패치 적용 자체가 실패 (형식이 깨진 diff 등) |
| empty_patch | 모델이 빈 답을 냄 |

이 프로젝트의 측정 결과는 다음과 같습니다(`REPORT.md` 참고).

- Qwen2.5-0.5B: 해결 0, 미해결 1, 적용 실패 2, 컨텍스트 초과로 제외 47건. 채점된 3건 중 0%
- Llama-3.1-8B: 해결 0, 미해결 18, 적용 실패 29, 제외 3건. 채점된 47건 중 0%

Qwen은 컨텍스트가 4K로 짧아 oracle 프롬프트(보통 5K~30K 토큰) 대부분이 들어가지 못해 47건이
제외됐습니다. 8B는 47건을 채점했지만 그중 29건이 적용 실패였습니다. 모델이 형식에 맞는 unified diff를
잘 만들지 못한다는 뜻입니다. 두 모델 모두 해결 0%인데, 같은 모델의 NPU 결과와 거의 일치합니다.
정확도는 장비와 무관하다는 점을 보여줍니다. 자세한 NPU·GPU 대조는
[../README_npu_gpu_result.md](../README_npu_gpu_result.md#테스트-4-코드-수정-정확도-swe-bench)에 있습니다.

### 데이터셋 종류

| 데이터셋 | 건수 | 특징 |
|---|--:|---|
| SWE-bench (full) | 2,294 | 원본. 파이썬 저장소 12개 |
| SWE-bench Lite | 300 | 풀기 비교적 명확한 버그만 추린 것. 이 프로젝트가 쓰는 것 |
| SWE-bench Verified | 500 | 사람이 풀 수 있는 문제인지 검증함. 신뢰도가 가장 높음 |
| SWE-bench Multimodal | 517 | 화면 요소가 있는 자바스크립트·UI |
| SWE-bench Multilingual | 300 | 파이썬이 아닌 언어 |

Lite를 고른 이유는 300건이라 8시간 안에 추론과 채점이 끝나고, 풀기 명확한 버그만 모여 있어
single-shot oracle 평가에 맞기 때문입니다.

### 측정하면서 손본 부분

swebench 패키지의 `run_api`는 OpenAI나 Anthropic 모델 이름이 코드에 박혀 있어서 로컬 모델로는
못 씁니다. 그래서 추론 루프를 따로 만들어 로컬 서버에 직접 요청합니다(`runners/swebench_run.py`).
Lite 인스턴스 중 일부는 oracle 텍스트가 모델 컨텍스트 한도를 넘는데, 서버의 `/models`에서
한도를 읽어 그런 인스턴스를 미리 제외합니다. 모델이 마크다운 표시나 설명을 섞어 보내면 패치 적용이
실패하므로, diff만 추려내고 구조를 확인합니다.

### 본 측정 설정 요약

데이터셋은 `princeton-nlp/SWE-bench_Lite_oracle`, 50건을 저장소별로 고르게 뽑았습니다.
방식은 single-shot, temperature 0, 응답 최대 1024 토큰, 동시 추론 8건입니다.
채점은 `swebench.harness.run_evaluation`을 Docker로 돌리고, `--namespace swebench`로
미리 빌드된 이미지를 받아 씁니다.

## RNGD 버전과 다른 점

| 항목 | RNGD (rngd-npu/) | GPU (이 폴더) |
|---|---|---|
| 서빙 | furiosa-llm serve | vllm serve |
| 모델 | furiosa prebuilt 모델 | 원본 HuggingFace 모델 |
| 디바이스 지정 | NPU PE 고정 (`--devices npu:0`) | `CUDA_VISIBLE_DEVICES`와 `--tensor-parallel-size` |
| 컨텍스트 한도 | 모델 컴파일 시 고정 (Qwen 4K, Llama 32K) | `--max-model-len`으로 NPU에 맞춤 |
| memsweep 옵션 | max-model-len, max-batch-size, max-num-batched-tokens | max-model-len, max-num-seqs, max-num-batched-tokens |
| 측정 코드 | 동일 (OpenAI 호환 API 사용) | 동일 |

서버 계층만 다르고 측정 코드는 똑같이 씁니다. 측정 기준이 같으므로 NPU와 GPU 결과를 직접 비교할 수
있습니다. 비교 분석은 [../README_npu_gpu_result.md](../README_npu_gpu_result.md)를 보시면 됩니다.

## 문제 해결

| 증상 | 조치 |
|---|---|
| nvidia-smi가 없음 | NVIDIA 드라이버 설치 후 재부팅 |
| vLLM import 실패 | `setup.sh` 다시 실행. requirements.txt가 vLLM 0.10.0+cu126 휠로 고정돼 있음 |
| 샘플링 단계에서 CUDA 드라이버 오류 | `run_all.sh`가 `VLLM_USE_FLASHINFER_SAMPLER=0`을 이미 설정함 |
| vLLM 기동 중 메모리 부족 | 모델 serve_args에 `--max-model-len 8192`이나 `--gpu-memory-utilization 0.85` 추가 |
| 접근 제한 모델 403 | `hf auth login` 후 HuggingFace 웹에서 라이선스 동의 |
| 70B 모델이 안 올라감 | `--quantization fp8` 또는 GPU 여러 장 사용 |
| 서버 기동 실패 | `results/_server_logs/`의 해당 모델 로그 확인 |
| SWE-bench 채점이 멈춤 | Docker가 켜져 있는지 확인. 첫 실행은 이미지 받느라 수십 GB 다운로드 |
| transformers 관련 오류 | requirements.txt가 `transformers==4.53.2`로 고정. 최신으로 올리지 말 것 |

SWE-bench 설치와 채점 명령은 [docs/SWEBENCH_SETUP.md](docs/SWEBENCH_SETUP.md)에 더 정리돼 있습니다.
