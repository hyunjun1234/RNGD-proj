# NVIDIA GPU (vLLM) — 코드 생성 모델 벤치마크 리포트

- 결과 데이터: `/home/jun/RNGD-proj/Model_Benchmark/bench-gpu/results`
- 측정 축: 단일 토큰 속도(tps) / 동시성 스케일링(sweep) / serve 옵션(memsweep) / SWE-bench / Embedding·Reranker
- 스케일링 분석 기준: prompt_len=1024, 효율배치=peak의 90% 도달 동시성, 감소판정=실패발생·처리량하락·TTFT_p95>10.0s

## 1. TL;DR — 모델별 핵심 지표

| 모델 | TTFT p50(s) | 단일 TPS | peak 합산 TPS@c | 효율 배치 | SWE-bench resolved |
|---|--:|--:|--:|--:|--:|
| `Qwen/Qwen2.5-0.5B-Instruct` | 0.0135 | 249.04 | 11423@c128 | c128 | 0/3 (0.0%) |
| `meta-llama/Llama-3.1-8B-Instruct` | 0.0359 | 41.93 | 3634@c128 | c128 | 0/47 (0.0%) |

## 2. 단일 요청 토큰 생성 속도 (concurrency=1)

| 모델 | TTFT p50(s) | TTFT p95(s) | ITL p50(s) | 출력 TPS p50 | 합산 TPS |
|---|--:|--:|--:|--:|--:|
| `Qwen/Qwen2.5-0.5B-Instruct` | 0.0135 | 0.0212 | 0.00401 | 249.04 | 247.5 |
| `meta-llama/Llama-3.1-8B-Instruct` | 0.0359 | 0.0411 | 0.02393 | 41.93 | 41.69 |

## 3. 배치/동시성 스케일링 (prompt_len=1024)

### Qwen/Qwen2.5-0.5B-Instruct

| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |
|--:|--:|--:|--:|--:|--:|
| 1 | 243.95 | 248.14 | 0.0199 | 0.00403 | 0 |
| 2 | 439.62 | 223.42 | 0.0237 | 0.00448 | 0 |
| 4 | 838.69 | 222.17 | 0.0306 | 0.00449 | 0 |
| 8 | 1481.89 | 211.0 | 0.0469 | 0.00472 | 0 |
| 16 | 3003.72 | 196.69 | 0.0708 | 0.00507 | 0 |
| 32 | 5535.3 | 182.83 | 0.1199 | 0.00546 | 0 |
| 64 | 7147.12 | 124.63 | 0.495 | 0.00796 | 0 |
| 128 | 11422.89 | 97.04 | 0.2385 | 0.01004 | 0 |

- **효율 배치**: 동시성 128 (합산 11423 TPS, peak 11423 TPS@c128)
- **무감소 최대 동시성**: 128 · **성능 감소 시작**: 관측 안 됨

### meta-llama/Llama-3.1-8B-Instruct

| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |
|--:|--:|--:|--:|--:|--:|
| 1 | 41.27 | 41.59 | 0.0461 | 0.02403 | 0 |
| 2 | 79.54 | 40.24 | 0.0491 | 0.02485 | 0 |
| 4 | 151.25 | 39.72 | 0.0734 | 0.02516 | 0 |
| 8 | 271.85 | 38.47 | 0.0836 | 0.02597 | 0 |
| 16 | 579.54 | 37.02 | 0.1021 | 0.02699 | 0 |
| 32 | 1122.48 | 36.09 | 0.1388 | 0.02758 | 0 |
| 64 | 2047.87 | 32.93 | 0.2087 | 0.03018 | 0 |
| 128 | 3633.89 | 29.45 | 0.3177 | 0.03366 | 0 |

- **효율 배치**: 동시성 128 (합산 3634 TPS, peak 3634 TPS@c128)
- **무감소 최대 동시성**: 128 · **성능 감소 시작**: 관측 안 됨

## 4. serve 옵션 스윕 (memsweep)

baseline(vLLM 기본값)에서 한 축씩 변경. 합산 TPS 기준 정렬.

### Qwen/Qwen2.5-0.5B-Instruct

| serve 옵션 조합 | 합산 TPS | 실패 |
|---|--:|--:|
| `baseline` | 11854 | 0 |
| `{"max_model_len": 4096}` | 11691 | 0 |
| `{"max_model_len": 8192}` | 11433 | 0 |
| `{"max_num_batched_tokens": 16384}` | 11416 | 0 |
| `{"max_model_len": 16384}` | 11229 | 0 |
| `{"max_num_batched_tokens": 4096}` | 11183 | 0 |
| `{"max_num_seqs": 32}` | 5589 | 0 |
| `{"max_num_seqs": 8}` | 1649 | 0 |

- **최적 조합**: `{}` → 11854.02 TPS

### meta-llama/Llama-3.1-8B-Instruct

| serve 옵션 조합 | 합산 TPS | 실패 |
|---|--:|--:|
| `{"max_model_len": 4096}` | 3671 | 0 |
| `{"max_model_len": 8192}` | 3656 | 0 |
| `baseline` | 3616 | 0 |
| `{"max_num_batched_tokens": 16384}` | 3613 | 0 |
| `{"max_num_batched_tokens": 4096}` | 3611 | 0 |
| `{"max_model_len": 16384}` | 3604 | 0 |
| `{"max_num_seqs": 32}` | 1144 | 0 |
| `{"max_num_seqs": 8}` | 306 | 0 |

- **최적 조합**: `{"max_model_len": 4096}` → 3671.33 TPS

## 5. SWE-bench (코드 수정 정확도)

SWE-bench Lite oracle, single-shot. resolved=테스트 통과, unresolved=적용됐으나 미해결, 적용실패=malformed diff, 컨텍스트제외=서버 context 한계를 넘어 사전 제외.

| 모델 | resolved | unresolved | 적용실패 | 빈 패치 | 추론오류 | 컨텍스트제외 | 형식의심 | total | resolved % |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `Qwen/Qwen2.5-0.5B-Instruct` | 0 | 1 | 2 | 0 | 0 | 47 | 3 | 3 | 0.0% |
| `meta-llama/Llama-3.1-8B-Instruct` | 0 | 18 | 29 | 0 | 0 | 3 | 46 | 47 | 0.0% |

## 6. Embedding / Reranker 처리량

| 모델 | 종류 | batch=1 | batch=16 | batch=64 |
|---|---|--:|--:|--:|

## 7. GPU & 동시 접속자별 권장 서빙 설정

- GPU: `CUDA_VISIBLE_DEVICES=2`

| 모델 | 권장 동시성(효율) | 무감소 한계 | 권장 serve 옵션 |
|---|--:|--:|---|
| `Qwen/Qwen2.5-0.5B-Instruct` | 128 | 128 | `baseline` |
| `meta-llama/Llama-3.1-8B-Instruct` | 128 | 128 | `{"max_model_len": 4096}` |

## 8. 종합 — 코드 생성 적합도 점수

정확도(SWE-bench 0.5) + peak 합산 TPS(0.3) + 단일 TPS(0.2) 가중합 (각 지표는 측정 모델 중 최대값 대비 정규화). embedding/reranker·smoke 제외.

| 순위 | 모델 | 종합점수 | SWE-bench % | 단일 TPS | peak 합산 TPS |
|--:|---|--:|--:|--:|--:|
| 1 | `meta-llama/Llama-3.1-8B-Instruct` | 0.500 | 0.0 | 41.9 | 3634 |

> **종합 1위: `meta-llama/Llama-3.1-8B-Instruct`** (종합점수 0.500).
