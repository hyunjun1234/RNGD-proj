# Model_Benchmark

RNGD NPU와 NVIDIA GPU에서 LLM 서빙 성능을 동일 기준으로 측정·비교하는 벤치마크 자동화.

| 폴더 | 내용 |
|---|---|
| `rngd-npu/` | Furiosa RNGD NPU 벤치 (`furiosa-llm serve`) — [README](rngd-npu/README.md) |
| `gpu/` | NVIDIA GPU 벤치 (`vllm serve`) — rngd-npu 포트 — [README](gpu/README.md) |
| `ppt/` | 결과 발표자료 (`pptxgenjs` 빌드) + 디자인 스펙(`Design.md`) + 폰트 |

측정 축: 토큰 속도(tps) · 동시성 스케일링(sweep) · serve 옵션 OFAT(memsweep) · SWE-bench · Embedding/Reranker.

실행법은 각 폴더 README 참조. 공용 환경(furiosa venv·모델 캐시)은 [상위 README](../README.md) 참조.
