# NPU 에이전트 라우팅 — 서브에이전트가 역할별 NPU 모델을 쓰게

날짜: 2026-07-23

## 목적

openclaude 서브에이전트(`/agents`, Task 도구)가 opus/gpt-4o 가 아니라 우리 NPU 라우터의
모델을 쓰게 한다. 나아가 에이전트(역할)마다 다른 NPU 모델을 지정해, 여러 모델이 각자
역할을 맡아 협업하는 자동화의 기반을 만든다.

## 실측 규명 (코드 + 실기)

- 서브에이전트 모델은 `settings.json`(userSettings, `$OPENCLAUDE_CONFIG_DIR/settings.json`)의
  `agentModels`(라우트키 메뉴) + `agentRouting`(에이전트→라우트키) 로 결정된다.
  읽기: `getInitialSettings()` → `resolveAgentRunModelRouting()`(agentRouting.ts:175).
- 우선순위: **Task 도구 명시 model > `agentRouting[name] > [subagentType] > [default]` > frontmatter model > 상속(inherit)**.
- 크로스-프로바이더 라우트로 인정되려면 `base_url` 과 `api_key` 가 **둘 다** 있어야 한다(하나만이면 스킵).
- `model` 은 라우터 REGISTRY 의 bare id(예: `Qwen3-4B-FP8`, `Qwen3-Coder-30B-A3B-Instruct-FP8`).
  `furiosa/` 접두사 붙이면 404.
- shim 환경에서 `inherit`/`haiku`/`sonnet` 은 부모(세션) NPU 모델을 상속하지만 `opus` 는
  `OPENAI_MODEL` 로 매핑된다 — 그래서 역할 고정에는 agentRouting 을 쓴다.
- **실기 검증(4장):** 메인 Qwen3-4B(npu0) 세션에서 general-purpose 서브에이전트를
  `agentRouting:{"general-purpose":"npu-8b"}` 로 스폰 → 라우터가 Qwen3-8B(npu1)를 별도
  로드, 서브에이전트가 그 모델로 응답. 두 모델 동시 상주 확인.

## install.sh 가 심는 기본 설정 (`FURIO_AGENT_ROUTING=0` 로 끔)

`settings.json` 에 병합(이미 있으면 보존):

```json
{
  "agentModels": {
    "npu-small": { "base_url": "<SDI_SERVER>/v1", "api_key": "<키|dummy>", "model": "Qwen3-4B-FP8" },
    "npu-8b":    { "base_url": "<SDI_SERVER>/v1", "api_key": "<키|dummy>", "model": "Qwen3-8B-FP8" },
    "npu-coder": { "base_url": "<SDI_SERVER>/v1", "api_key": "<키|dummy>", "model": "Qwen3-Coder-30B-A3B-Instruct-FP8" },
    "npu-70b":   { "base_url": "<SDI_SERVER>/v1", "api_key": "<키|dummy>", "model": "Llama-3.3-70B-Instruct" }
  },
  "agentRouting": { "default": "npu-small" }
}
```

`default → npu-small(1장)`: 모든 서브에이전트를 경량 NPU 모델로. 메인 세션 모델은 `/model`
로 고른 것 그대로(여기 영향 없음).

## 역할별 배정 (사용자가 편집)

`settings.json` 의 `agentRouting` 에 **에이전트 이름**을 키로 추가한다(이름이 default 보다 우선):

```json
"agentRouting": {
  "general-purpose": "npu-coder",   // 코드 생성 역할 → 30B 코더
  "Explore":         "npu-small",   // 탐색 → 4B
  "default":         "npu-small"
}
```

## ⚠️ NPU 4장 예산 (동시성 제약)

| 모델 | 카드 | 동시 상주 |
|---|---|---|
| Qwen3-4B-FP8 / Qwen3-8B-FP8 / Qwen2.5-0.5B-Instruct | 1 | 카드 합 ≤4 면 여러 개 동시 |
| Qwen3-Coder-30B-A3B-Instruct-FP8 / Llama-3.3-70B-Instruct / gpt-oss-120b | 4 | 각각 4장 독점 → 동시 불가(시분할·콜드스타트) |

- **진짜 병렬 역할**: 1장 모델들로 구성(예: A=4B, B=8B, C=0.5B).
- **대형(30B/70B)**: 품질↑ 이지만 한 번에 하나 → 번갈아 쓰면 evict/콜드스타트 스래싱.

## 다음 단계 (완전 자동화 — 미착수, 설계 예정)

- 역할 = 에이전트(위 라우팅), 외부 동작(GitHub push/pull, 코드 전달) = **MCP 서버**(openclaude 는 MCP 완전 지원).
- 자동 트리거: teams/coordinator 모드(모델 주도 위임), proactive(주기 tick), cron 예약,
  라이프사이클 훅(Stop/SubagentStop/TaskCompleted/TeammateIdle), goal 루프.
- 서브에이전트 '분배' 결정 자체는 콘텐츠 규칙 라우터가 아니라 **메인 모델이 Task 도구를
  호출**하는 model-driven 방식 — 오케스트레이터 에이전트 + teams + 이벤트 트리거 조합으로 구성.
