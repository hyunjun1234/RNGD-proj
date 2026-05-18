# Furiosa RNGD — 코드 생성 모델 벤치마크 리포트

- 결과 데이터: `results/`
- 측정 축: 단일 토큰 속도(tps) / 동시성 스케일링(sweep) / serve 옵션(memsweep) / SWE-bench / Embedding·Reranker
- 스케일링 분석 기준: prompt_len=1024, 효율배치=peak의 90% 도달 동시성, 감소판정=실패발생·처리량하락·TTFT_p95>10.0s

## 1. TL;DR — 모델별 핵심 지표

| 모델 | NPU | TTFT p50(s) | 단일 TPS | peak 합산 TPS@c | 효율 배치 | SWE-bench resolved |
|---|---|--:|--:|--:|--:|--:|
| `furiosa-ai/Llama-3.1-8B-Instruct` | npu:0 | 0.0324 | 55.16 | 2197@c128 | c128 | 0/50 (0.0%) |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | npu:0 | 0.031 | 85.26 | 3983@c128 | c128 | 0/50 (0.0%) |
| `furiosa-ai/Qwen3-Embedding-8B` | npu:0 | — | — | — | — | — |
| `furiosa-ai/Qwen3-Reranker-8B` | npu:0 | — | — | — | — | — |

## 2. 단일 요청 토큰 생성 속도 (concurrency=1)

| 모델 | TTFT p50(s) | TTFT p95(s) | ITL p50(s) | 출력 TPS p50 | 합산 TPS |
|---|--:|--:|--:|--:|--:|
| `furiosa-ai/Llama-3.1-8B-Instruct` | 0.0324 | 0.0363 | 0.0182 | 55.16 | 54.88 |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | 0.031 | 0.0323 | 0.01177 | 85.26 | 84.67 |

## 3. 배치/동시성 스케일링 (prompt_len=1024)

동시 접속자 수(=concurrency)를 늘릴 때 합산 처리량과 지연이 어떻게 변하는지. **효율 배치**=가성비 정점, **무감소 최대**=실패·지연열화 없는 최대 동시성, **감소 시작**=이 동시성부터 성능 저하.

### furiosa-ai/Llama-3.1-8B-Instruct

| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |
|--:|--:|--:|--:|--:|--:|
| 1 | 51.95 | 53.68 | 0.0394 | 0.01862 | 0 |
| 2 | 101.14 | 51.41 | 0.0508 | 0.01938 | 0 |
| 4 | 191.1 | 50.48 | 0.1077 | 0.01979 | 0 |
| 8 | 343.59 | 48.48 | 0.1727 | 0.02025 | 0 |
| 16 | 648.99 | 42.16 | 0.3809 | 0.02306 | 0 |
| 32 | 1090.02 | 35.38 | 0.5078 | 0.02693 | 0 |
| 64 | 1635.61 | 26.84 | 0.9608 | 0.03475 | 0 |
| 128 | 2197.15 | 18.14 | 1.8499 | 0.05029 | 0 |

- **효율 배치**: 동시성 128 (합산 2197 TPS, peak 2197 TPS@c128의 100%)
- **무감소 최대 동시성**: 128
- **성능 감소 시작 동시성**: 관측 안 됨

### furiosa-ai/Qwen2.5-0.5B-Instruct

| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |
|--:|--:|--:|--:|--:|--:|
| 1 | 69.81 | 71.18 | 0.0374 | 0.01411 | 0 |
| 2 | 136.79 | 70.56 | 0.0608 | 0.01412 | 0 |
| 4 | 261.27 | 68.69 | 0.0653 | 0.01419 | 0 |
| 8 | 462.61 | 65.54 | 0.0985 | 0.01424 | 0 |
| 16 | 1008.49 | 65.5 | 0.1746 | 0.01459 | 0 |
| 32 | 1917.02 | 62.05 | 0.3043 | 0.01509 | 0 |
| 64 | 3349.92 | 55.16 | 0.6625 | 0.01498 | 0 |
| 128 | 3982.89 | 34.85 | 1.5845 | 0.02414 | 0 |

- **효율 배치**: 동시성 128 (합산 3983 TPS, peak 3983 TPS@c128의 100%)
- **무감소 최대 동시성**: 128
- **성능 감소 시작 동시성**: 관측 안 됨

## 4. serve 옵션 스윕 (memsweep) — KV cache / batch 설정 효과

baseline(furiosa-llm 기본값)에서 한 축씩만 바꿔 측정. 합산 TPS 기준 정렬.

### furiosa-ai/Llama-3.1-8B-Instruct

| serve 옵션 조합 | 합산 TPS | 실패 |
|---|--:|--:|
| `{"max_model_len": 4096}` | 2294 | 0 |
| `baseline` | 2276 | 0 |
| `{"max_num_batched_tokens": 4096}` | 2272 | 0 |
| `{"max_batch_size": 8}` | 2268 | 0 |
| `{"max_num_batched_tokens": 16384}` | 2266 | 0 |
| `{"max_batch_size": 32}` | 2265 | 0 |
| `{"max_model_len": 8192}` | 2251 | 0 |
| `{"max_model_len": 16384}` | 2133 | 0 |

- **최적 조합**: `{"max_model_len": 4096}` → 2294.43 TPS

### furiosa-ai/Qwen2.5-0.5B-Instruct

| serve 옵션 조합 | 합산 TPS | 실패 |
|---|--:|--:|
| `{"max_num_batched_tokens": 16384}` | 4617 | 0 |
| `{"max_model_len": 8192}` | 4294 | 0 |
| `{"max_model_len": 4096}` | 4233 | 0 |
| `{"max_batch_size": 32}` | 4159 | 0 |
| `{"max_model_len": 16384}` | 4156 | 0 |
| `{"max_num_batched_tokens": 4096}` | 4095 | 0 |
| `baseline` | 3835 | 0 |
| `{"max_batch_size": 8}` | 3773 | 0 |

- **최적 조합**: `{"max_num_batched_tokens": 16384}` → 4617.21 TPS

## 5. SWE-bench (코드 수정 정확도)

SWE-bench Lite oracle, single-shot diff 생성. **resolved**=테스트 통과, **unresolved**=패치 적용됐으나 미해결, **적용실패**=malformed diff 등으로 patch 적용 불가(harness error), **추론오류**=서버 응답 실패(context 초과 등).

| 모델 | resolved | unresolved | 적용실패 | 빈 패치 | 추론오류 | total | resolved % |
|---|--:|--:|--:|--:|--:|--:|--:|
| `furiosa-ai/Llama-3.1-8B-Instruct` | 0 | 23 | 27 | 0 | 0 | 50 | 0.0% |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | 0 | 0 | 0 | 50 | 50 | 50 | 0.0% |

> ⚠ `furiosa-ai/Llama-3.1-8B-Instruct`: 27/50 가 **적용실패** — 모델이 정확한 unified diff를 못 만든 비율이 높음. resolved %가 실제 코드 수정 능력보다 낮게 나올 수 있음 (diff 포맷 한계 + 모델 역량 혼재).

## 6. Embedding / Reranker 처리량

| 모델 | 종류 | batch=1 | batch=16 | batch=64 |
|---|---|--:|--:|--:|
| `furiosa-ai/Qwen3-Embedding-8B` | embed | 1.16 | 1.17 | 1.17 |
| `furiosa-ai/Qwen3-Reranker-8B` | rerank | 1.17 | — | — |

## 7. NPU 요구량 & 동시 접속자별 권장 서빙 설정

| 모델 | NPU 카드 | 권장 동시성(효율) | 무감소 한계 | 권장 serve 옵션 |
|---|---|--:|--:|---|
| `furiosa-ai/Llama-3.1-8B-Instruct` | 1 (npu:0) | 128 | 128 | `{"max_model_len": 4096}` |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | 1 (npu:0) | 128 | 128 | `{"max_num_batched_tokens": 16384}` |
| `furiosa-ai/Qwen3-Embedding-8B` | 1 (npu:0) | — | — | `—` |
| `furiosa-ai/Qwen3-Reranker-8B` | 1 (npu:0) | — | — | `—` |

## 8. 종합 — 코드 생성 적합도 점수

코드 생성 모델 선정은 **정확도(SWE-bench) > 처리량 > 지연** 우선순위로 평가. 각 지표를 측정된 모델 중 최대값 대비 0~1로 정규화 후 가중합 (SWE-bench 0.5, peak 합산 TPS 0.3, 단일 TPS 0.2). embedding/reranker(생성 모델 아님)와 smoke 역할(파이프라인 검증용 0.5B)은 제외.

측정 가능한 코드 생성 모델은 **`furiosa-ai/Llama-3.1-8B-Instruct`** 단독이다 (SWE-bench 0.0%, 단일 55 TPS, peak 합산 2197 TPS). 코드 생성 강력 후보인 32B/70B는 하드웨어 제약으로 제외돼 **모델 간 순위 비교는 성립하지 않는다** — 이 머신에서의 결론은 사실상 가용 모델 단독 선택이다.

### 측정 제외 모델 (하드웨어 제약)

아래 모델은 prebuilt 아티팩트가 `tensor_parallel=32` (RNGD 4장 = 32 PE)로 컴파일돼 있어 현재 2장(16 PE) 머신에서 서빙 불가 → 평가 제외:

- `furiosa-ai/Qwen3-32B-FP8`
- `furiosa-ai/EXAONE-4.0-32B-FP8`
- `furiosa-ai/Llama-3.3-70B-Instruct`

> RNGD 4장 이상 머신에서 `configs/models.yaml`의 `enabled: true`로 바꾸면 코드 수정 없이 동일 파이프라인으로 측정된다. 32B/70B는 통상 SWE-bench 정확도가 8B보다 높으므로, 정확도 우선이라면 4장 환경 측정 권장.
