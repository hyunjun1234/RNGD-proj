# SWE-bench 환경 구축 & 사용

GitHub 실제 이슈를 코드 패치로 해결하는 능력을 측정하는 벤치마크. 모델이 만든
diff를 실제 repo 테스트로 채점한다.

## SWE-bench란

- 입력: GitHub 이슈 본문 + 해당 시점 repo 코드
- 출력(모델): unified diff (패치)
- 채점: 패치를 적용해 repo 테스트 실행 → `FAIL_TO_PASS` 통과 + `PASS_TO_PASS` 유지 시 **resolved**
- 인스턴스마다 Docker 컨테이너에서 격리 실행

## 변형(데이터셋 종류)

| 데이터셋 | 인스턴스 | 용도 |
|---|--:|---|
| `SWE-bench` (full) | 2,294 | 원본. 12개 Python repo |
| `SWE-bench_Lite` | 300 | 저비용 평가용 큐레이션 subset (자체 완결적 버그) |
| `SWE-bench_Verified` | 500 | 사람이 검증(해결 가능·테스트 공정) — 신뢰도 최상 |
| `SWE-bench_Multimodal` | 517 | 시각 요소 포함(JS/UI) |
| `SWE-bench_Multilingual` | 300 | 비-Python 언어 |

## context 제공 방식

| 방식 | 설명 |
|---|---|
| `oracle` | 정답 패치가 수정한 파일을 context로 제공 → 순수 코드 편집 능력 측정 |
| `bm25_13K` / `27K` / `40K` | BM25 검색으로 관련 파일 추출, 토큰 상한별 |
| `full` | repo 전체 |

## 실행 방식

- **single-shot**: 1회 호출로 diff 생성 (본 측정 방식)
- **agentic**: 에이전트가 repo 탐색·편집·테스트를 반복 (리더보드 상위 점수 방식)

## 본 벤치마크에서 사용한 구성

`SWE-bench_Lite` + `oracle` + `single-shot` + repo별 stratified 50건 subset.

---

## 요구사항

- x86_64 Linux, Docker (인스턴스별 컨테이너 실행)
- 디스크 수십~120GB (인스턴스 이미지)
- Python 3.10+

## 설치

```bash
git clone https://github.com/SWE-bench/SWE-bench.git
cd SWE-bench
pip install -e .
# 또는: pip install swebench
docker --version          # Docker 동작 확인
```

## 데이터셋 로드

```python
from datasets import load_dataset
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")          # 채점용(이슈+테스트)
oracle = load_dataset("princeton-nlp/SWE-bench_Lite_oracle", split="test")  # 추론 프롬프트(text 컬럼)
```

## 예측 파일 포맷 (predictions.jsonl)

한 줄 = 한 인스턴스:

```json
{"instance_id": "astropy__astropy-12907", "model_name_or_path": "my-model", "model_patch": "diff --git a/...\n--- a/...\n+++ b/...\n@@ ... @@\n..."}
```

## 채점 실행

```bash
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path predictions.jsonl \
    --max_workers 8 \
    --namespace swebench \      # Docker Hub의 prebuilt 이미지 pull (대량 빌드 생략)
    --cache_level env \
    --run_id my_run
```

- `--namespace swebench`: prebuilt 이미지 pull. `none`이면 로컬 빌드(수 시간).
- `--instance_ids id1 id2 ...`: 일부만 채점.
- 결과 리포트: `<model_safe>.<run_id>.json` (resolved/unresolved/error 카운트).

## 결과 해석

| 항목 | 의미 |
|---|---|
| `resolved` | 패치 적용 + 테스트 통과 |
| `unresolved` | 패치 적용됐으나 테스트 미통과 |
| `error` | malformed diff 등으로 patch 적용 불가 |
| `empty_patch` | 빈 패치 |

## 본 프레임워크 연동

`rngd-npu`에서는 `runners/swebench_run.py`가 추론(oracle 프롬프트 → 로컬 furiosa-llm
서버), `swebench_eval.py`가 채점(위 harness 호출)을 담당한다.
컨텍스트 필터링·patch sanity 검사·재시도는 모두 `runners/swebench_run.py` 안에서 처리된다.

```bash
source ~/furiosa/bin/activate
python orchestrator.py configs/models.yaml --tasks swebench --models <MODEL>  # 추론
bash eval_swebench.sh --models <MODEL>                                        # 채점
```
