# Furiosa RNGD (furiosa-llm) — 코드 생성 모델 벤치마크 리포트

- 결과 데이터: `/home/jun/RNGD-proj/Model_Benchmark/rngd-npu/results`
- 측정 축: 단일 토큰 속도(tps) / 동시성 스케일링(sweep) / serve 옵션(memsweep) / SWE-bench / Embedding·Reranker
- 스케일링 분석 기준: prompt_len=1024, 효율배치=peak의 90% 도달 동시성, 감소판정=실패발생·처리량하락·TTFT_p95>10.0s

## 1. TL;DR — 모델별 핵심 지표

| 모델 | NPU | TTFT p50(s) | 단일 TPS | peak 합산 TPS@c | 효율 배치 | SWE-bench resolved |
|---|---|--:|--:|--:|--:|--:|
| `furiosa-ai/Llama-3.1-8B-Instruct` | npu:0 | 0.0326 | 54.5 | 2192@c128 | c128 | 0/50 (0.0%) |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | npu:0 | 0.0306 | 84.48 | 4120@c128 | c128 | 0/50 (0.0%) |
| `furiosa-ai/Qwen3-Embedding-8B` | npu:0 | — | — | — | — | — |
| `furiosa-ai/Qwen3-Reranker-8B` | npu:0 | — | — | — | — | — |

## 2. 단일 요청 토큰 생성 속도 (concurrency=1)

| 모델 | TTFT p50(s) | TTFT p95(s) | ITL p50(s) | 출력 TPS p50 | 합산 TPS |
|---|--:|--:|--:|--:|--:|
| `furiosa-ai/Llama-3.1-8B-Instruct` | 0.0326 | 0.037 | 0.01832 | 54.5 | 53.2 |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | 0.0306 | 0.0319 | 0.01189 | 84.48 | 83.83 |

## 3. 배치/동시성 스케일링 (prompt_len=1024)

### furiosa-ai/Llama-3.1-8B-Instruct

| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |
|--:|--:|--:|--:|--:|--:|
| 1 | 52.39 | 53.12 | 0.04 | 0.01877 | 0 |
| 2 | 99.82 | 50.99 | 0.0685 | 0.01943 | 0 |
| 4 | 191.61 | 50.67 | 0.1117 | 0.0196 | 0 |
| 8 | 335.14 | 47.46 | 0.1988 | 0.02062 | 0 |
| 16 | 636.7 | 41.68 | 0.2707 | 0.02289 | 0 |
| 32 | 1091.45 | 35.75 | 0.5244 | 0.02634 | 0 |
| 64 | 1646.55 | 26.9 | 0.9613 | 0.03432 | 0 |
| 128 | 2191.78 | 18.14 | 2.05 | 0.05005 | 0 |

- **효율 배치**: 동시성 128 (합산 2192 TPS, peak 2192 TPS@c128)
- **무감소 최대 동시성**: 128 · **성능 감소 시작**: 관측 안 됨

### furiosa-ai/Qwen2.5-0.5B-Instruct

| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |
|--:|--:|--:|--:|--:|--:|
| 1 | 70.61 | 71.33 | 0.0383 | 0.01405 | 0 |
| 2 | 140.32 | 70.92 | 0.0365 | 0.01413 | 0 |
| 4 | 262.07 | 68.82 | 0.0737 | 0.01401 | 0 |
| 8 | 480.77 | 67.99 | 0.1053 | 0.01418 | 0 |
| 16 | 1023.79 | 66.52 | 0.1705 | 0.0146 | 0 |
| 32 | 1932.22 | 62.76 | 0.3011 | 0.01506 | 0 |
| 64 | 3299.68 | 55.55 | 0.658 | 0.0152 | 0 |
| 128 | 4120.35 | 34.88 | 1.3328 | 0.02426 | 0 |

- **효율 배치**: 동시성 128 (합산 4120 TPS, peak 4120 TPS@c128)
- **무감소 최대 동시성**: 128 · **성능 감소 시작**: 관측 안 됨

## 4. serve 옵션 스윕 (memsweep) — KV cache / batch 설정 효과

baseline(furiosa-llm 기본값)에서 한 축씩만 바꿔 측정. 합산 TPS 기준 정렬.

### furiosa-ai/Llama-3.1-8B-Instruct

| serve 옵션 조합 | 합산 TPS | 실패 |
|---|--:|--:|
| `{"max_num_batched_tokens": 4096}` | 2288 | 0 |
| `{"max_model_len": 16384}` | 2274 | 0 |
| `{"max_model_len": 4096}` | 2272 | 0 |
| `{"max_model_len": 8192}` | 2271 | 0 |
| `baseline` | 2251 | 0 |
| `{"max_batch_size": 32}` | 2250 | 0 |
| `{"max_batch_size": 8}` | 2232 | 0 |
| `{"max_num_batched_tokens": 16384}` | 2139 | 0 |

- **최적 조합**: `{"max_num_batched_tokens": 4096}` → 2287.84 TPS

### furiosa-ai/Qwen2.5-0.5B-Instruct

| serve 옵션 조합 | 합산 TPS | 실패 |
|---|--:|--:|
| `{"max_num_batched_tokens": 16384}` | 4570 | 0 |
| `{"max_batch_size": 32}` | 4339 | 0 |
| `{"max_model_len": 16384}` | 4281 | 0 |
| `{"max_model_len": 4096}` | 4251 | 0 |
| `baseline` | 4246 | 0 |
| `{"max_model_len": 8192}` | 4242 | 0 |
| `{"max_batch_size": 8}` | 4073 | 0 |
| `{"max_num_batched_tokens": 4096}` | 4012 | 0 |

- **최적 조합**: `{"max_num_batched_tokens": 16384}` → 4570.38 TPS

## 5. SWE-bench (코드 수정 정확도)

SWE-bench Lite oracle, single-shot. resolved=테스트 통과, unresolved=적용됐으나 미해결, 적용실패=malformed diff, 컨텍스트제외=서버 context 한계를 넘어 사전 제외.

| 모델 | resolved | unresolved | 적용실패 | 빈 패치 | 추론오류 | 컨텍스트제외 | 형식의심 | total | resolved % |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `furiosa-ai/Llama-3.1-8B-Instruct` | 0 | 14 | 36 | 0 | 0 | 0 | 48 | 50 | 0.0% |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | 0 | 1 | 2 | 47 | 47 | 0 | 3 | 50 | 0.0% |

> ⚠ `furiosa-ai/Llama-3.1-8B-Instruct`: 36/50 가 **적용실패** — 모델이 정확한 unified diff를 못 만든 비율이 높음. resolved %가 실제 코드 수정 능력보다 낮게 나올 수 있음 (diff 포맷 한계 + 모델 역량 혼재).

## 6. Embedding / Reranker 처리량

| 모델 | 종류 | batch=1 | batch=16 | batch=64 |
|---|---|--:|--:|--:|
| `furiosa-ai/Qwen3-Embedding-8B` | embed | 1.16 | 1.17 | 1.17 |
| `furiosa-ai/Qwen3-Reranker-8B` | rerank | 1.17 | — | — |

## 7. NPU 요구량 & 동시 접속자별 권장 서빙 설정

| 모델 | NPU 카드 | 권장 동시성(효율) | 무감소 한계 | 권장 serve 옵션 |
|---|---|--:|--:|---|
| `furiosa-ai/Llama-3.1-8B-Instruct` | 1 (npu:0) | 128 | 128 | `{"max_num_batched_tokens": 4096}` |
| `furiosa-ai/Qwen2.5-0.5B-Instruct` | 1 (npu:0) | 128 | 128 | `{"max_num_batched_tokens": 16384}` |
| `furiosa-ai/Qwen3-Embedding-8B` | 1 (npu:0) | — | — | `—` |
| `furiosa-ai/Qwen3-Reranker-8B` | 1 (npu:0) | — | — | `—` |

## 8. 종합 — 코드 생성 적합도 점수

정확도(SWE-bench 0.5) + peak 합산 TPS(0.3) + 단일 TPS(0.2) 가중합 (각 지표는 측정 모델 중 최대값 대비 정규화). embedding/reranker·smoke 제외.

측정 가능한 코드 생성 모델은 **`furiosa-ai/Llama-3.1-8B-Instruct`** 단독이다 (SWE-bench 0.0%, 단일 54 TPS, peak 합산 2192 TPS). 코드 생성 강력 후보인 32B/70B는 하드웨어 제약으로 제외돼 **모델 간 순위 비교는 성립하지 않는다** — 이 머신에서의 결론은 사실상 가용 모델 단독 선택이다.

### 측정 제외 모델 (하드웨어 제약)

아래 모델은 prebuilt 아티팩트가 `tensor_parallel=32` (RNGD 4장 = 32 PE)로 컴파일돼 있어 현재 머신 PE 예산 안에서 서빙 불가 → 평가 제외:

- `furiosa-ai/Qwen3-32B-FP8`
- `furiosa-ai/EXAONE-4.0-32B-FP8`
- `furiosa-ai/Llama-3.3-70B-Instruct`

> RNGD 4장 이상 머신에서 `configs/models.yaml`의 `enabled: true`로 바꾸면 코드 수정 없이 동일 파이프라인으로 측정된다. 32B/70B는 통상 SWE-bench 정확도가 8B보다 높으므로, 정확도 우선이라면 4장 환경 측정 권장.
