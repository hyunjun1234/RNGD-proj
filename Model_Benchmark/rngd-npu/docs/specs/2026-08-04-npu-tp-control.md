# NPU tp 제어 — `/model` 에 tp 축 추가 + 새 tp8 아티팩트 연결

날짜: 2026-08-04

## 목적

`/model` 에서 dp·pp 처럼 **tp 도 화살표로 고를 수 있게** 한다. 서버 `/mnt/nvme2n1p1/models/artifacts`
에 새로 빌드한 **tp8 v2 아티팩트 8종**을 라우터에 연결해, 지금까지 tp32(4장 독점·pp 불가)로만
쓰던 30B/32B 모델을 **tp8(1장·pp 조절 가능)** 로도 서빙한다.

## 실측 근거 (2026-08-04)

- `/mnt/nvme2n1p1/models/artifacts/*-tp8` 는 v2 아티팩트(`artifact.json`+`binary_bundle.zip`),
  내부에 `tensor_parallel_size=8, pipeline_parallel_size=1` 이 **구워져 있음**.
- **tp 는 빌드 타임 고정** — 로드 시 `-tp` 는 무시된다. 따라서 "tp 제어" = **서로 다른 빌드 선택**:
  tp32(fxb, 4장, `-pp` PanicException) ↔ tp8(v2, 1장, `-pp` 층분할 가능).
- 각 tp8 아티팩트의 `max_position_embeddings` == 기존 base 레지스트리 `ctx` (전부 일치) →
  tp8 변형은 base 의 ctx/tool/reasoning 을 그대로 상속.
- serve 바이너리: `~/furiosa` venv 는 부분 업그레이드로 깨짐(import 단계 사망). 작동본은
  `~/furiosa-3.0-test/bin/furiosa-llm` → 라우터가 `FURIOSA_LLM_BIN` 환경변수를 읽게 한다.
  참고 메모리: [[furiosa-venv-version-skew]] [[chat-service-model-catalog]]

### tp8 아티팩트 → 레지스트리 매핑

| 아티팩트 | base 모델 | 처리 |
|---|---|---|
| a3b-tp8 | Qwen3-30B-A3B-FP8 | `tps[8]` 추가 |
| a3b-inst-2507-tp8 | Qwen3-30B-A3B-Instruct-2507-FP8 | `tps[8]` |
| a3b-think-2507-tp8 | Qwen3-30B-A3B-Thinking-2507-FP8 | `tps[8]` |
| coder-tp8 | Qwen3-Coder-30B-A3B-Instruct-FP8 | `tps[8]` |
| exaone4-tp8 | EXAONE-4.0-32B-FP8 | `tps[8]` |
| qwen3-32b-tp8 | Qwen3-32B-FP8 | `tps[8]` |
| coder-bf16-tp8 | **(신규)** Qwen3-Coder-30B-A3B-Instruct (BF16) | 새 base, tool=None(채팅전용) |
| llama31-8b-tp8 | Llama-3.1-8B-Instruct | path 를 fxb→이 v2 로 **재지정**(pp 잠금해제, tp 동일) |

기본 tp 는 base 그대로(30B/32B 는 tp32) 유지 → 맨이름(`Qwen3-32B-FP8`)은 하위호환. tp8 은 선택지.

## 설계

### 변형 ID 스킴
`Base@tp{N}@dp{N}@pp{N}` — 각 축이 기본값이면 접미사 생략(tp 는 base 기본 tp, dp1/pp1).
- `Qwen3-32B-FP8` = tp32·dp1·pp1 (기본)
- `Qwen3-32B-FP8@tp8` = tp8·dp1·pp1
- `Qwen3-32B-FP8@tp8@pp2` = tp8·pp2 (2장 층분할)

### 유효 조합 (PE 패킹)
카드 1장 = 8 PE. 인스턴스 하나 = tp·pp PE, dp 개 = tp·pp·dp PE. `need = ceil(dp·pp / max(1, 8//tp))`.
- tp32 → 4장 독점 → dp1·pp1 뿐.
- tp8 → 1장/인스턴스 → dp·pp ≤ 4 (v2 라 pp 허용).
- tp4(Qwen2.5-0.5B) → 카드당 2개 패킹(기존 동작 유지).

pp 는 **v2 아티팩트에서만** 허용(fxb 는 PanicException). tp8 변형은 항상 v2 → pp 허용.

### 라우터 변경 (`furiosa_router.py`)
1. `FURIOSA_LLM = env(FURIOSA_LLM_BIN, 기존기본)`; `NVME_ART = env(FURIO_ARTIFACTS, /mnt/nvme2n1p1/models/artifacts)`.
2. 레지스트리: 위 표대로 `tps` 추가 / llama 재지정 / bf16 신규.
3. `parse_variant → (base, tp, dp, pp)`, `variant_id(base, tp, dp, pp)`, `tp_choices(base)`,
   `resolve_art(reg, tp)`, `par_choices(base, tp)`, `all_model_ids()` 3중 중첩.
4. `_start` 가 파싱된 tp + 해석된 아티팩트 경로 사용. `model_desc`/status 가 tp 반영.
5. `/router/models` 응답에 base 별 구조화 메타(`tp_default`, `tps[]`) 포함 → 클라이언트로 전달.

### 클라이언트 변경 (openclaude 포크)
- `npuVariants.ts`: `NpuVariant.tp` 추가, SUFFIX 정규식에 `tp`, `NpuAxis += 'tp'`,
  `stepNpuAxis`/`npuAxisValues`/`npuAxisAllValues` 를 3축으로 일반화, `variantId`/`describeNpuVariant` tp 포함.
  base 별 기본 tp·tp 목록은 새 env `FURIO_NPU_META`(라우터 `/router/models` 유래)에서 읽음.
- `ModelPicker.tsx`: `npuConfig {tp,dp,pp}`, tab 이 tp→dp→pp 순환, tp 행 렌더.
- dist 재빌드 → `openclaude-npu.patch` 갱신.
- `install.sh`: 래퍼에 `FURIO_NPU_META` 주입(FURIO_MODEL_DESCRIPTIONS 과 동일 파이프라인).

## 단계 (위험 최소화 순서)
1. **라우터 먼저** — 순수함수 유닛테스트 + 라이브 serve 검증(`Qwen3-32B-FP8@tp8` 1장,
   `Llama-3.1-8B-Instruct@pp2` v2 pp 층분할). 이 단계만으로 `furio --model Qwen3-32B-FP8@tp8@pp2` 사용 가능.
2. **클라이언트** — tp 축 UI + 빌드 + mock 스모크 + 라이브 e2e.
3. 배포: 라우터는 재시작만. 클라이언트는 dist 재빌드 후 각 PC `install.sh` 재실행(사용자 승인함).

## 후속: pp 기본값(pp_default) — 1장 초과 모델 (2026-08-04 추가)

BF16 코더(`coder-bf16-tp8`, 57GB)는 1장(47.5GB)에 안 들어가 **pp1 이 OOM**. 그래서 tp 축과
대칭으로 **모델별 기본 pp** 를 도입:
- 레지스트리 `pp_opts=[2,3,4]` → par_choices 가 pp1 을 빼고 2·3·4 만 노출, dp 는 1(대형이라 복제 안 함).
- `pp_default(base)=pp_opts[0]`(=2). variant_id 는 pp==기본 pp 면 `@pp` 생략 → **맨이름이 pp2 를 뜻함**.
  parse_variant 는 `@pp` 없으면 pp_default 로 채운다. (일반 모델은 pp_default=1 로 기존과 동일.)
- `/router/models` 가 `pp_default` 를 실어 보내고, 클라이언트는 `FURIO_NPU_META` 로 받아 pp 축을
  `[2·3·4]`(기본 2)로 라벨링(tp 와 같은 메커니즘). 실기검증: 기본(pp2) npu:0,1·pp3 npu:0,1,2 둘 다 "pong".

## 비고
- coder(FP8/BF16) 계열은 `qwen3_coder` 파서가 2026.3.0 CLI 에 없어 tool calling 불가 → 채팅 전용.
- llama fxb→v2 재지정은 serve 동등 + pp 만 추가(저위험). 되돌리려면 path 원복.
