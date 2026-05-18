# Furiosa RNGD 코드 생성 모델 벤치마크

`furiosa-llm serve`로 OpenAI 호환 API를 띄우고, 7개 모델 각각에 대해
**토큰 생성 속도 / 동시 접속자별 처리량 / 메모리·KV cache 한계 / SWE-bench / Embedding·Reranker 처리량**을 자동 측정합니다.

vLLM은 RNGD에 직접 붙지 않으므로, 본 프레임워크는 furiosa-llm을 OpenAI 호환 서버로 띄우고 vLLM 호환 클라이언트(`/v1/chat/completions`, `/v1/embeddings`, …)로 측정합니다. 클라이언트 도구(예: GenAI-Perf, vllm-bench)도 동일 endpoint에 그대로 연결 가능합니다.

## 디렉토리 구조

```
rngd-npu/
├── configs/
│   └── models.yaml              # 7개 모델 × role × serve_args + sweep grid
├── runners/
│   ├── server.py                # furiosa-llm serve 라이프사이클
│   ├── tps.py                   # TTFT/ITL/output_TPS, concurrency
│   ├── memory_sweep.py          # serve 인자 grid 스윕 (KV cache 등)
│   ├── embed_bench.py           # Qwen3-Embedding/Reranker
│   └── swebench_run.py          # BM25 → 예측 → Docker harness
├── orchestrator.py              # 모델 × 태스크 자동 실행
├── analyze.py                   # results/ 집계, CSV
├── report.py                    # 종합 리포트 (배치 스케일링 분석 + 적합도 점수)
├── swebench_eval.py             # 예측 jsonl → Docker harness 채점 드라이버
├── preflight.sh                 # 사전 점검 (env, NPU, Docker, 모델 가용성)
├── run_all.sh                   # 전체 파이프라인 실행
├── eval_swebench.sh             # swebench_eval.py 래퍼
├── docs/
│   ├── RUNNING_BENCHMARKS.md    # 새 모델 추가 / RNGD 증설 시 벤치마크 실행 가이드
│   └── COMPILING_MODELS.md      # HF 모델을 직접 컴파일해 RNGD에서 실행하기
└── results/                     # 결과 (자동 생성)
    └── <model_safe>/<task>/<timestamp>.json
```

## 빠른 시작

```bash
cd rngd-npu

# 0. 사전 점검 (NPU 상태, 모델 가용 revision, Docker)
bash preflight.sh

# 1. smoke (Qwen2.5-0.5B만, tps만)
STAGE=smoke ./run_all.sh

# 2. 생성 모델 전체: tps + sweep + memsweep
STAGE=gen ./run_all.sh

# 3. embedding/reranker
STAGE=embed ./run_all.sh

# 4. SWE-bench (Docker 필요, 시간 오래 걸림)
STAGE=swebench ./run_all.sh

# 5. 종합 리포트
STAGE=report ./run_all.sh

# 또는 한 번에
./run_all.sh
```

## 태스크 종류

| 태스크 | 설명 | 적용 대상 |
|---|---|---|
| `tps` | concurrency=1, stream으로 TTFT/ITL/output_TPS | 생성 모델 |
| `sweep` | concurrency × prompt_len 매트릭스 (request shape) | 생성 모델 |
| `memsweep` | serve 인자 OFAT 스윕 (baseline에서 한 축씩: max-model-len, max-batch-size, max-num-batched-tokens) | 생성 모델 |
| `embed` | `/v1/embeddings` 처리량, batch size별 | Qwen3-Embedding |
| `rerank` | `/v1/rerank` 또는 임베딩+코사인 fallback | Qwen3-Reranker |
| `swebench` | SWE-bench Lite oracle → 예측 생성 (채점은 `swebench_eval.py`) | 생성 모델 |

## 단일 태스크/모델 직접 실행

```bash
# 한 모델, 한 태스크
python orchestrator.py configs/models.yaml \
    --tasks sweep --models Llama-3.1-8B

# 여러 태스크 + 여러 모델 (substring 매칭)
python orchestrator.py configs/models.yaml \
    --tasks tps,sweep,memsweep --models Qwen3,EXAONE

# 어떤 게 실행될지만 먼저 확인
python orchestrator.py configs/models.yaml --tasks tps --dry-run
```

## 결과 분석

```bash
# 모든 task JSON을 모아 표 출력
python analyze.py

# CSV로
python analyze.py --csv summary.csv

# task 필터
python analyze.py --task sweep

# 종합 리포트 (REPORT.md 생성)
python report.py
```

## 결정 사항 / 제약

1. **vLLM 호환** — Furiosa-LLM이 vLLM과 동일한 OpenAI API를 제공. 클라이언트 도구는 그대로 사용. 본 프레임워크의 모든 측정 클라이언트는 OpenAI 호환 spec을 따름.
2. **Docker** — SWE-bench harness 평가에만 사용. 서빙 자체는 native furiosa-llm.
3. **NPU / 모델 크기 제약** — 이 머신은 RNGD 2장(16 PE). prebuilt 아티팩트는 `artifact.json`의 `model.parallel_config.tensor_parallel_size`로 PE 요구량이 고정됨: 0.5B=4, 8B=8, **32B·70B=32(RNGD 4장 필요)**. 따라서 32B·70B는 2장 머신에서 서빙 불가 → `models.yaml`에서 `enabled: false`. 카드당 8 PE, `-tp` 기본 4 → 1카드로 dp=2 자동. 4장 이상 머신에서는 `enabled: true`만으로 측정 가능.
4. **SWE-bench** — `run_api`는 OpenAI/Anthropic 모델명 하드코딩이라 미사용. `swebench_run.py`가 `SWE-bench_Lite_oracle`(text 컬럼 prebuilt)을 로컬 OpenAI 호환 서버로 single-shot diff 추론. 채점은 `--namespace swebench`로 prebuilt 이미지 pull.
5. **Coder 전용 모델** — `Qwen2.5-Coder-7B-Instruct` 등은 v2026.2 artifact가 push 안 됨 → 평가 제외.

## 트러블슈팅

- **서버 기동 실패** — `results/_server_logs/<model>_*.log` 확인. 가장 흔한 원인은 모델 artifact의 v2026.2 태그 부재 (각 모델 레포 refs를 `preflight.sh`로 사전 확인).
- **OOM** — `memsweep` 결과의 error 행 보고 `max_model_len` 또는 `max_batch_size` 줄여서 다시 측정.
- **prefix caching 자동 비활성화** — artifact가 extend bucket 미지원이면 자동 disable. 작은 모델에서 자주 발생, 큰 모델은 보통 지원.
- **SWE-bench 첫 실행이 매우 느림** — task별 base Docker 이미지를 빌드하기 때문 (수 시간). 이후 캐시.

## 환경변수

- `SWEBENCH_DATASET` — inference 데이터셋 (기본 `princeton-nlp/SWE-bench_Lite_oracle`).
- `SWEBENCH_N` — SWE-bench subset 크기 (기본 50, repo별 stratified). `0`/미설정-full(300).
- `SWEBENCH_MAXTOK` — 예측 응답 max_tokens (기본 4096).
- `SWEBENCH_CONC` — SWE-bench 동시 추론 요청 수 (기본 8).
- `USE_WTL_BACKEND=1` — 일부 모델에서 LTW → WTL 백엔드로 변경 (성능 개선 가능).
- `STAGE`, `CONFIG`, `MAX_WORKERS` — `run_all.sh` / `eval_swebench.sh`에서 사용.
