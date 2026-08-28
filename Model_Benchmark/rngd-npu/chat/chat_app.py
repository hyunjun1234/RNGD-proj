#!/usr/bin/env python3
"""Furiosa RNGD Chat — furiosa-llm serve 위의 대화 인터페이스.

furiosa-apps(github.com/furiosa-ai/furiosa-apps) 의 디자인과 두 기능을 우리 채팅에 통합:
- **furiosa 인터페이스 디자인**: 순수 검정 테마 + 로고/Furiosa RNGD Chat/DEMO 헤더,
  빨강(전송)·시안(메트릭 제목)·보라(라인·배지) 강조 (chat-playground 원본 팔레트).
- **실시간 성능 대시보드(우측 컬럼)**: TPS·TTFT·TPOT·E2E·Power/card·Temp·Util.
  토큰 타이밍은 스트리밍 생성에서, 전력/온도/사용률은 furiosa-smi 파싱(npu_metrics.py).
- **RAG(선택)**: 사이드바에서 켜면 업로드 문서에서 근거를 찾아 컨텍스트로 주입+출처 각주.
  기본 TF-IDF(의존성·NPU 0), furiosa 임베딩/리랭커 서버 있으면 그걸 사용(rag_store.py).

기존 디테일은 그대로 유지(요구사항):
- on-demand serve: 모델을 고르면 필요한 카드를 비우고 띄움. tp8 은 복제(dp)·레이어분할(pp)을
  골라(dp×pp ≤ 4장) 띄우고, tp32 는 4장 고정(dp·pp 비활성). 카드 회계는 실제 serve 의
  --devices/-pp/-dp 로 항상 정확히.
- 상태 LED: 🟢 떠 있음 / 🟡 전환중(이 dot만 깜빡) / 🔴 꺼짐·실패.
- 질문은 입력 즉시 대화창에 뜨고, 답변은 토큰 단위로 흘러나옴(스트리밍).
- max_tokens 는 생성 시 (컨텍스트 - 프롬프트)로 자동 클램프 → 컨텍스트 초과 에러 안 남.
- 대화 사이드바(새 채팅·검색·최근·선택 삭제) + 서버 디스크 영구 저장.
- 전송 버튼(↑)은 생성 중 중지(■)로 바뀜. 메시지의 ↻ 아이콘으로 다시 생성.
"""
import os
import re
import json
import base64
import signal
import subprocess
import threading
import time
import warnings
import datetime as dt
from pathlib import Path

# 부팅 경고 정리: 5.50 에는 아직 대체 API(launch theme/css, Chatbot buttons,
# api_visibility)가 없어 마이그레이션이 불가하므로, "Gradio 6.0" 예고용
# DeprecationWarning 만 정밀하게 끈다(다른 경고는 그대로 보이게 둠).
warnings.filterwarnings("ignore", message=r".*Gradio 6\.0.*", category=DeprecationWarning)

import gradio as gr  # noqa: E402
import httpx  # noqa: E402
from openai import OpenAI  # noqa: E402

import npu_metrics  # noqa: E402  실시간 성능 대시보드(TPS·TTFT·TPOT·E2E·Power) — furiosa chat-playground 이식
import rag_store    # noqa: E402  선택적 RAG(문서 검색 후 컨텍스트 주입) — furiosa rag(kotaemon) 패턴 이식

# 로컬 legacy(v2) tp8 아티팩트 저장소. 예전 rngd-npu/artifacts 는 비었고, 2026-07 재빌드분은
# 공용 모델 저장소(nvme2)로 옮겨졌다. CHAT_ARTIFACTS 로 덮어쓸 수 있다.
ARTIFACTS = Path(os.environ.get("CHAT_ARTIFACTS", "/mnt/nvme2n1p1/models/artifacts"))
# 프리빌트 저장소(furiosa-ai/*)를 serve 가 해석할 HF 캐시. /etc/profile.d/hf-cache.sh 와 같은 값이며,
# 로그인 셸을 안 거치고 뜬 경우(setsid·systemd)에도 자식 serve 가 같은 캐시를 보도록 여기서 못박는다.
HF_HUB_CACHE = os.environ.get("HF_HUB_CACHE", "/mnt/nvme2n1p1/models/hf/hub")
# serve 바이너리. venv 가 깨졌을 때 다른 venv 로 갈아끼울 수 있게 환경변수로 뺀다
# (2026-07-31 ~/furiosa 의 furiosa-torch 만 2026.3.0 으로 올라가 furiosa-models 2026.2.0 과
#  충돌하며 serve 가 import 단계에서 죽은 전례 — FURIOSA_LLM_BIN 으로 우회 가능).
FURIOSA_LLM = os.environ.get("FURIOSA_LLM_BIN", str(Path.home() / "furiosa/bin/furiosa-llm"))
HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "serve_logs"
CONV_DIR = HERE / "conversations"
LOG_DIR.mkdir(exist_ok=True)
CONV_DIR.mkdir(exist_ok=True)

# 실시간 대시보드·RAG 전역(서버 1개 = 공유 상태). MGR(ServeManager)와 같은 위상.
METRICS = npu_metrics.Metrics()
RAG = rag_store.RagStore()


def _logo_data_uri():
    """furiosa Symbol.png(칩 아이콘)을 base64 data URI 로 — 헤더에 인라인(파일 서빙 경로 무관)."""
    p = HERE / "assets" / "Symbol.png"
    try:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
    except Exception:
        return ""


LOGO_URI = _logo_data_uri()

# ── 모델 카탈로그 (2026-08-04 전면 갱신) ───────────────────────────────────
# 옛 카탈로그는 ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts 를 가리켰으나 그 폴더는 .gitkeep 만
# 남아 12종 전부 死경로였다. 지금 실재하는 두 갈래를 노출한다.
#
#   src="art"  로컬 legacy(v2) tp8 아티팩트 — /mnt/nvme2n1p1/models/artifacts (2026-07-29 빌드, 8종)
#              tp8 로 빌드해 뒀으므로 serve 때 -pp 로 층을 쪼갤 수 있다(= pp 커스텀 가능).
#   src="hub"  furiosa-ai 프리빌트 저장소 — HF_HUB_CACHE(/mnt/nvme2n1p1/models/hf/hub)
#              대부분 tp32(4장 독점)로 박혀 있고, FXB 번들은 pp 를 런타임이 거부한다(no_pp).
#
# 필드
#   name       드롭다운 표시명. **고유해야 한다**(DISPLAY2KEY 의 키) — 같은 모델의 tp8/tp32 판을
#              구분해야 하므로 이름에 tp 를 직접 넣는다.
#   port       고정 포트(모델마다 유일). 라우터(:8400/백엔드 :8410+)와 겹치지 않는 8000~8024 대역.
#   kind       "tp8"(카드 1장 단위, dp·pp 선택) | "tp32"(4장 고정, dp·pp 비활성)
#   src/sub    "art"→ARTIFACTS 하위 디렉토리명 / "hub"→HF 저장소 ID(furiosa-llm 이 캐시에서 해석)
#   ctx        아티팩트 총 컨텍스트 — artifact.json 의 최대 attention_size 실측
#   prompt_max 한 번에 넣을 수 있는 프롬프트 상한(생략 시 ctx). kv_heads=4 인 30B-A3B 계열은
#              append(chunked prefill) 버킷이 65536 에서 막혀 65,408 이 상한이다.
#              ⚠️ 서버는 초과 요청을 200 OK 로 받은 뒤 스케줄러에서 실패한다 — 클라이언트가 잘라야 한다.
#   pp_min     최소이자 기본 pp. 최대 컨텍스트로 쓸 때 1장(47.5G)에 안 들어가면 2 이상.
#              (짧게 쓰면 pp1 로도 뜨지만, UI 는 최대 컨텍스트 기준으로 안전하게 고른다.)
#   no_pp      True 면 pp 선택 불가 — FXB 아티팩트는 런타임이 PanicException 으로 거절(2026-07-22 실측)
#   pe         인스턴스 하나가 쓰는 PE 수(기본 8 = 카드 1장). 8 미만이면 카드 일부(npu:X:0-N)만
#              쓰고 dp·pp 는 1 고정.
#   tool       --tool-call-parser 값 또는 None    reasoning  --reasoning-parser 값 또는 None
#              ⚠️ furiosa-llm 2026.3.0 이 받는 값은 constants.py:TOOL_PARSER_NAMES 에 하드코딩된
#              {hermes, llama3_json, llama4_json, openai, solar_open} 뿐이다(2026-08-04 실측).
#              Qwen3-Coder 계열 전용 qwen3_coder 파서는 이 목록에 없어 주면 serve 가 즉시
#              'invalid choice' 로 죽는다 → 아래 coder 3종은 tool=None(채팅 전용)으로 둔다.
#              (coding-agent/furiosa_patches/ 의 로컬 파서는 __init__.py 등록만 해서는 안 되고
#               constants.py 목록까지 손봐야 한다 — 그 패치가 들어오면 여기서 qwen3_coder 로 바꿀 것.)
#   extra      그 밖의 serve 인자
#
# 근거: legacy_moe_build/README.md §0-A(빌드 실측표)·§0.5(파서)·§4.1(pp),
#       coding-agent/furiosa_router.py REGISTRY(프리빌트 파서·tp), 각 artifact.json 직접 파싱.
CATALOG = {
    # ── 로컬 tp8 아티팩트 (2026-07-29 빌드) — pp 를 UI 에서 바꿀 수 있는 유일한 갈래 ──
    # kv_heads=4 계열(coder·a3b-*)은 총 컨텍스트가 262144 여도 프롬프트는 65,408 까지만 된다.
    # ⚠️ model_type=qwen3_moe 인 것(coder·coder-bf16·a3b·a3b-inst-2507·a3b-think-2507)은
    #    serve 게이트가 거부한다 — `PanicException: Unsupported model metadata`.
    #    **양자화와 무관하다**: fp8·bf16 둘 다 막히는 것을 2026-08-04 에 실측했다.
    #    연산은 이미 컴파일돼 있고 게이트만 메타데이터를 보므로 artifact.json 의 model_type 을
    #    qwen3 로 위장하면 뜬다: `bash masquerade_moe.sh --apply`
    #    (README §3-1, validate_catalog.py 가 자동으로 잡아 명령까지 찍어 준다.)
#    "coder":            dict(name="Qwen3-Coder-30B-A3B-Inst-FP8 tp8", port=8000, kind="tp8",
#                             src="art", sub="coder-tp8", ctx=262144, prompt_max=65408,
#                             pp_min=2, tool=None, reasoning=None),
    # bf16 56.9G. pp4 실측 분할은 13.5/14.1/14.1/15.8 GiB → pp2 면 27.6/29.9 GiB.
    # 예전 pp2 상한(29.7G) 턱밑이라 한동안 pp4 로 강제했으나, 2026-08-04 에 pp2 로 실제 기동해
    # 정상 동작을 확인하고 기본을 pp2 로 내렸다(카드 2장만 쓰므로 다른 모델과 같이 띄울 수 있다).
    # 최대 컨텍스트(262144)로 길게 쓰면 KV 가 장당 12 GiB 라 빠듯하니, 그때는 UI 에서 pp4 를 고를 것.
#    "coder-bf16":       dict(name="Qwen3-Coder-30B-A3B-Inst bf16 tp8", port=8001, kind="tp8",
#                             src="art", sub="coder-bf16-tp8", ctx=262144, prompt_max=65408,
#                             pp_min=2, tool=None, reasoning=None),
#    "a3b-inst-2507":    dict(name="Qwen3-30B-A3B-Instruct-2507-FP8 tp8", port=8002, kind="tp8",
#                             src="art", sub="a3b-inst-2507-tp8", ctx=262144, prompt_max=65408,
#                             pp_min=2, tool="hermes", reasoning=None),
#    "a3b-think-2507":   dict(name="Qwen3-30B-A3B-Thinking-2507-FP8 tp8", port=8003, kind="tp8",
#                             src="art", sub="a3b-think-2507-tp8", ctx=262144, prompt_max=65408,
#                             pp_min=2, tool="hermes", reasoning="qwen3"),
    # ❌ a3b(Qwen3-30B-A3B-FP8) — **아티팩트가 고장이라 비활성**(2026-08-04 실측).
    # 위장 후 serve 는 정상적으로 뜨는데(게이트 통과·Uvicorn running·가중치 29.0G 로드 OK)
    # **생성이 0 토큰**이다. /v1/completions 로 채팅 템플릿을 우회해도 빈 문자열이라
    # 샘플링·파서·템플릿 문제가 아니다. temperature 0 에선 질문과 무관한 반복 텍스트가 나온다.
    # 같은 위장을 적용한 coder·a3b-inst-2507·a3b-think-2507 은 전부 정상 생성하므로
    # 위장 방식의 문제가 아니라 이 빌드만의 문제다(빌드 로그는 SUCCEEDED, ERROR 0건).
    # hf_configs 도 정상 3종과 max_position_embeddings(40960) 빼고 전부 동일.
    # → 재빌드 후 되살릴 것. 그때 이 주석을 지우고 아래 항목을 복구하면 된다.
    # "a3b":            dict(name="Qwen3-30B-A3B-FP8 tp8", port=8004, kind="tp8",
    #                        src="art", sub="a3b-tp8", ctx=40960,
    #                        pp_min=1, tool="hermes", reasoning="qwen3"),
    "qwen3-32b":        dict(name="Qwen3-32B-FP8 tp8", port=8005, kind="tp8",
                             src="art", sub="qwen3-32b-tp8", ctx=40960,
                             pp_min=1, tool="hermes", reasoning="qwen3"),
    # 가중치 30.8G + KV 256KiB/token — 131072 를 다 쓰면 1장 초과라 pp2.
    "exaone4":          dict(name="EXAONE-4.0-32B-FP8 tp8", port=8006, kind="tp8",
                             src="art", sub="exaone4-tp8", ctx=131072,
                             pp_min=2, tool="hermes", reasoning="exaone4"),
    "llama31-8b":       dict(name="Llama-3.1-8B-Instruct tp8", port=8007, kind="tp8",
                             src="art", sub="llama31-8b-tp8", ctx=131072,
                             pp_min=1, tool="llama3_json", reasoning=None),

    # ── furiosa-ai 프리빌트 (HF 캐시) — tp32 는 4장 독점이라 한 번에 하나만 뜬다 ──
    "hub-gpt-oss-120b":     dict(name="gpt-oss-120b tp32", port=8010, kind="tp32",
                                 src="hub", sub="furiosa-ai/gpt-oss-120b", ctx=131072,
                                 tool="openai", reasoning=None),
    "hub-solar-100b":       dict(name="Solar-Open-100B-NVFP4A16 tp32", port=8011, kind="tp32",
                                 src="hub", sub="furiosa-ai/Solar-Open-100B-NVFP4A16", ctx=131072,
                                 tool="solar_open", reasoning="solar_open"),
    "hub-llama-70b":        dict(name="Llama-3.3-70B-Instruct tp32", port=8012, kind="tp32",
                                 src="hub", sub="furiosa-ai/Llama-3.3-70B-Instruct", ctx=131072,
                                 tool="llama3_json", reasoning=None),
    "hub-qwen3-32b":        dict(name="Qwen3-32B-FP8 tp32", port=8013, kind="tp32",
                                 src="hub", sub="furiosa-ai/Qwen3-32B-FP8", ctx=40960,
                                 tool="hermes", reasoning="qwen3"),
    "hub-exaone4":          dict(name="EXAONE-4.0-32B-FP8 tp32", port=8014, kind="tp32",
                                 src="hub", sub="furiosa-ai/EXAONE-4.0-32B-FP8", ctx=131072,
                                 tool="hermes", reasoning="exaone4"),
    # enable_thinking 템플릿 kwargs 없이는 추론이 안 나온다(available_model.md 비고).
    "hub-kexaone-236b":     dict(name="K-EXAONE-236B-A23B-NVFP4A16 tp32", port=8015, kind="tp32",
                                 src="hub", sub="furiosa-ai/K-EXAONE-236B-A23B-NVFP4A16", ctx=262144,
                                 tool="hermes", reasoning="deepseek_v3",
                                 extra=["--default-chat-template-kwargs", '{"enable_thinking": true}']),
    "hub-a3b-inst-2507":    dict(name="Qwen3-30B-A3B-Instruct-2507-FP8 tp32", port=8016, kind="tp32",
                                 src="hub", sub="furiosa-ai/Qwen3-30B-A3B-Instruct-2507-FP8", ctx=262144,
                                 tool="hermes", reasoning=None),
    "hub-a3b-think-2507":   dict(name="Qwen3-30B-A3B-Thinking-2507-FP8 tp32", port=8017, kind="tp32",
                                 src="hub", sub="furiosa-ai/Qwen3-30B-A3B-Thinking-2507-FP8", ctx=262144,
                                 tool="hermes", reasoning="qwen3"),
    "hub-a3b":              dict(name="Qwen3-30B-A3B-FP8 tp32", port=8018, kind="tp32",
                                 src="hub", sub="furiosa-ai/Qwen3-30B-A3B-FP8", ctx=40960,
                                 tool="hermes", reasoning="qwen3"),
    "hub-coder":            dict(name="Qwen3-Coder-30B-A3B-Inst-FP8 tp32", port=8019, kind="tp32",
                                 src="hub", sub="furiosa-ai/Qwen3-Coder-30B-A3B-Instruct-FP8", ctx=262144,
                                 tool=None, reasoning=None),
    # 멀티모달(VL) — 이 UI 는 텍스트만 보내므로 텍스트 채팅으로만 쓴다.
    "hub-qwen3-vl-32b":     dict(name="Qwen3-VL-32B-Instruct tp32", port=8020, kind="tp32",
                                 src="hub", sub="furiosa-ai/Qwen3-VL-32B-Instruct", ctx=262144,
                                 tool="hermes", reasoning=None),
    # 아래 4종은 프리빌트인데도 1장짜리라 tp32 처럼 4장을 묶지 않는다.
    # Llama-3.1-8B 는 v2 아티팩트라 pp 가 되고, Qwen3-8B/4B 는 FXB 라 pp 가 막힌다(no_pp).
    "hub-llama31-8b":       dict(name="Llama-3.1-8B-Instruct tp8 (prebuilt)", port=8021, kind="tp8",
                                 src="hub", sub="furiosa-ai/Llama-3.1-8B-Instruct", ctx=131072,
                                 pp_min=1, tool="llama3_json", reasoning=None),
    "hub-qwen3-8b":         dict(name="Qwen3-8B-FP8 tp8 (prebuilt)", port=8022, kind="tp8",
                                 src="hub", sub="furiosa-ai/Qwen3-8B-FP8", ctx=40960,
                                 pp_min=1, no_pp=True, tool="hermes", reasoning="qwen3"),
    "hub-qwen3-4b":         dict(name="Qwen3-4B-FP8 tp8 (prebuilt)", port=8023, kind="tp8",
                                 src="hub", sub="furiosa-ai/Qwen3-4B-FP8", ctx=40960,
                                 pp_min=1, no_pp=True, tool="hermes", reasoning="qwen3"),
    # tp4 — 카드 하나의 앞 4 PE 만 쓴다(npu:X:0-3). dp·pp 는 1 고정.
    "hub-qwen2.5-0.5b":     dict(name="Qwen2.5-0.5B-Instruct tp4 (prebuilt)", port=8024, kind="tp8",
                                 src="hub", sub="furiosa-ai/Qwen2.5-0.5B-Instruct", ctx=32768,
                                 pe=4, tool="hermes", reasoning=None),
    # 임베딩/리랭커(furiosa-ai/Qwen3-Embedding-8B·Qwen3-Reranker-8B)는 채팅 모델이 아니라 뺐다 —
    # /v1/embeddings·/v1/rerank 로 쓰는 것이고 라우터(:8400)가 이미 노출한다.
}
DISPLAY2KEY = {m["name"]: k for k, m in CATALOG.items()}
DISPLAY_NAMES = [m["name"] for m in CATALOG.values()]
# 이름·포트가 겹치면 드롭다운/상태패널이 조용히 어긋나므로 임포트 시점에 잡는다.
assert len(DISPLAY2KEY) == len(CATALOG), "CATALOG name 중복"
assert len({m["port"] for m in CATALOG.values()}) == len(CATALOG), "CATALOG port 중복"
# 기본 선택 = 가장 가볍고(15G) pp1 로 1장에 뜨는 로컬 tp8 모델.
DEFAULT_MODEL = CATALOG["llama31-8b"]["name"]
# 프리빌트(src="hub") 모델의 첫 기동은 HF 다운로드(수십~백 GB)를 포함할 수 있어 라우터와 같은
# 2400 초를 기본으로 둔다. 로컬 아티팩트만 쓸 거면 CHAT_SERVE_TIMEOUT 으로 줄여도 된다.
STARTUP_TIMEOUT = float(os.environ.get("CHAT_SERVE_TIMEOUT", "2400"))
# 마지막으로 고른 모델/병렬구성을 서버측에 기억 → 브라우저 새로고침 후에도 DEFAULT_MODEL 로 안 돌아감.
# user_set=False 면(아직 아무도 안 바꿈) '지금 NPU 에 떠 있는 모델'로 시작한다(아래 _initial_model).
# (단일 사용자 DEMO 전제. 새 세션/탭도 마지막 선택을 따른다.)
_LAST_MODEL = {"name": DEFAULT_MODEL, "dp": 1, "pp": 1, "user_set": False}


def _dd_choices():
    """드롭다운 라벨. 이름 자체가 이미 tp 를 달고 있으므로(카탈로그 참고) 뒤에 컨텍스트만 덧붙인다.
    kv_heads=4 계열처럼 프롬프트 상한이 총 컨텍스트보다 짧으면 그 값도 같이 보여 준다.
    값은 모델명(DISPLAY2KEY 의 키)."""
    out = []
    for m in CATALOG.values():
        ctx, pmax = m["ctx"], m.get("prompt_max")
        c = f"{ctx // 1024}K" + (f"/프롬프트 {pmax // 1024}K" if pmax and pmax < ctx else "")
        out.append((f"{m['name']}  ·  {c}", m["name"]))
    return out


def _artifact_ref(m):
    """serve 에 넘길 아티팩트 위치. 로컬은 절대경로, 프리빌트는 HF 저장소 ID 그대로 넘긴다
    (furiosa-llm 이 HF_HUB_CACHE 에서 해석하고, 없으면 내려받는다)."""
    return str(ARTIFACTS / m["sub"]) if m.get("src", "art") == "art" else m["sub"]


def _parser_flags(m):
    """--tool-call-parser / --reasoning-parser 플래그.
    tool 파서를 쓰려면 --enable-auto-tool-choice 가 같이 있어야 하고(없으면 tool 요청이 400),
    reasoning 파서는 추론 모델에만 준다(아닌 모델에 주면 400)."""
    flags = []
    if m.get("tool"):
        flags += ["--enable-auto-tool-choice", "--tool-call-parser", m["tool"]]
    if m.get("reasoning"):
        flags += ["--reasoning-parser", m["reasoning"]]
    return flags + list(m.get("extra", []))


def _pp_choices(m):
    """이 모델에서 고를 수 있는 pp 목록. FXB 아티팩트는 pp 자체가 거부되고(no_pp),
    pe<8(부분 카드) 모델도 쪼갤 대상이 아니라 1 뿐이다. 그 밖엔 pp_min 이상 4 까지.

    pp=3 도 넣는다. 한때 라우터의 (1,2,4) 를 그대로 가져와 3 을 뺐었는데 근거가 없었다 —
    이 UI 는 원래 [1,2,3,4] 를 주고 있었고, 런타임도 `-pp 3` 을 받는다(2026-08-04 실측:
    serve 로그에 `Parallelism Config: tp=8, pp=3, dp=1`). 다만 카드 4장에서 pp3 은 dp=1
    고정이고 한 장이 놀게 된다(3장 점유). 2 로 안 들어가는 모델을 4장까지 안 쓰고 올릴 때 쓴다.
    (pp3 로 끝까지 로드해 생성까지 확인한 실측은 아직 없다 — 카드가 비면 확인할 것.)"""
    if m.get("no_pp") or m.get("pe", 8) < 8:
        return [1]
    return [n for n in (1, 2, 3, 4) if n >= m.get("pp_min", 1)] or [1]


def _serve_env():
    """자식 serve 프로세스 환경. 로그인 셸을 안 거치고 뜬 경우에도(setsid·systemd) 프리빌트
    저장소를 같은 캐시에서 찾도록 HF_HUB_CACHE 를 못박는다."""
    env = dict(os.environ)
    env.setdefault("HF_HUB_CACHE", HF_HUB_CACHE)
    return env


def _port_up(port):
    try:
        return httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=1.5).status_code == 200
    except Exception:
        return False


def _par_flags(kind, dp, pp):
    """serve 명령에 넣을 병렬화 플래그(-pp/-dp). 실측으로 검증된 형태만 쓴다(2026-06-09):
    - tp32 는 아티팩트가 tp32·4장 고정이라 플래그 없음.
    - pp=1 이면 플래그 없음 — dp 는 --devices 카드 수로 자동 추론(furiosa 기본·현행 동작, 검증됨).
    - pp>1 이면 -pp 를 명시(카드 수만으론 pp/dp 구분 불가). dp>1 이면 -dp 도 함께 못박는다.
    예) (8,1,1)→[]  (8,2,1)→[]  (8,1,2)→[-pp 2]  (8,1,4)→[-pp 4]  (8,2,2)→[-pp 2 -dp 2]"""
    if kind == "tp32" or pp <= 1:
        return []
    flags = ["-pp", str(pp)]
    if dp > 1:
        flags += ["-dp", str(dp)]
    return flags


class ServeManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._proc = {}
        self._state = {k: "down" for k in CATALOG}
        self._err = {}
        self._dev = {}
        self._par = {}     # key -> (dp, pp). tp8 의 복제 수·레이어분할 수(serve 명령에 -dp/-pp 로 반영)
        self._pending = {} # key -> (dp, pp). 전환 중에 들어온 새 dp/pp 요청 — 전환 끝나면 즉시 적용
        self._stopping_all = False  # '전부 내리기' 진행 중 — in-flight 로딩을 조용히 중단시키는 플래그
        self._lru = []

    def _touch(self, key):
        if key in self._lru:
            self._lru.remove(key)
        self._lru.append(key)

    def _discover(self):
        """실행 중인 furiosa-llm serve 의 --port/--devices/-pp/-dp 를 읽어 카드 점유·병렬구성을
        실제와 맞춘다. pgrep 로 살아있는 것으로 확인된 키 집합을 돌려준다(HTTP 와 무관한 liveness)."""
        try:
            out = subprocess.run(["pgrep", "-af", "furiosa-llm serve"],
                                 capture_output=True, text=True, timeout=5).stdout
        except Exception:
            return set()
        port2info = {}
        for line in out.splitlines():
            mp, md = re.search(r"--port\s+(\d+)", line), re.search(r"--devices\s+(\S+)", line)
            if mp and md:
                mpp = re.search(r"(?:-pp|--pipeline-parallel-size)\s+(\d+)", line)
                mdp = re.search(r"(?:-dp|--data-parallel-size)\s+(\d+)", line)
                port2info[int(mp.group(1))] = (md.group(1),
                                               int(mpp.group(1)) if mpp else None,
                                               int(mdp.group(1)) if mdp else None)
        port2key = {m["port"]: k for k, m in CATALOG.items()}
        found = set()
        with self._lock:
            for port, (dev, pp, dp) in port2info.items():
                k = port2key.get(port)
                if k:
                    found.add(k)
                    if self._state.get(k) not in ("loading", "stopping"):
                        self._state[k] = "up"
                        self._dev[k] = dev
                        ncards = len([d for d in dev.split(",") if d.startswith("npu:")])
                        ppv = pp or 1
                        # -dp 미지정이면 카드 수/pp 로 역산(현행 dp 자동추론과 동일 규칙)
                        self._par[k] = (dp if dp else max(1, ncards // ppv), ppv)
        return found

    def _held_cards(self):
        held = set()
        for k, st in self._state.items():
            if st in ("up", "loading"):
                for d in self._dev.get(k, "").split(","):
                    if d.startswith("npu:"):
                        held.add(int(d.split(":")[1]))
        return held

    def _free_cards(self, n):
        held = self._held_cards()
        return [c for c in range(4) if c not in held][:n]

    def state(self, key):
        return self._state.get(key, "down")

    def error(self, key):
        return self._err.get(key, "")

    def device(self, key):
        return self._dev.get(key, "")

    def par(self, key):
        return self._par.get(key, (1, 1))

    def request(self, key, dp=1, pp=1):
        if not key or key not in CATALOG:
            return
        self._discover()
        m = CATALOG[key]
        if m["kind"] == "tp32":
            dp, pp, needed = 1, 1, 4          # tp32 는 4장 전부 — dp·pp 무의미
        elif m.get("pe", 8) < 8:
            dp, pp, needed = 1, 1, 1          # 부분 카드(tp<8) — 한 장의 앞 pe 개 PE 만
        else:
            # UI 를 안 거친 호출(복원된 _LAST_MODEL 등)도 있으므로 여기서 다시 조인다.
            # pp 는 이 모델이 실제로 허용하는 값 중 요청에 가장 가까운 것으로 스냅한다
            # (FXB → 1 강제, 1장에 안 들어가는 모델 → pp_min 이상).
            allowed = _pp_choices(m)
            pp = min(allowed, key=lambda n: (abs(n - max(1, int(pp or 1))), n))
            dp = max(1, min(4, int(dp or 1)))
            if dp * pp > 4:                    # 카드 4장 한도 — pp 우선, dp 축소
                dp = max(1, 4 // pp)
            needed = dp * pp                    # tp8 = 카드당 8PE → 카드 수 = dp×pp
        with self._lock:
            cur = self._state.get(key)
            cur_cards = (len(self._dev.get(key, "").split(","))
                         if cur in ("up", "loading") and self._dev.get(key) else 0)
            # 전환 중(loading/stopping): 같은 config 면 중복이라 무시. 다른 config 면 '대기 설정'에
            # 적어 두고 리턴 — 진행 중 전환이 정리되는 즉시 그 설정으로 다시 전환한다(변경 중 dp/pp
            # 를 바꿔도 바뀐 값이 반영되도록). 같은 요청 반복(터널 재진입)은 여전히 무해하게 흡수.
            if cur in ("loading", "stopping"):
                if (dp, pp) != self._par.get(key):
                    self._pending[key] = (dp, pp)
                return
            # 같은 모델이 같은 (dp,pp) 로 이미 떠 있으면 재기동 없이 재사용
            if cur == "up" and cur_cards == needed and self._par.get(key) == (dp, pp):
                self._touch(key)
                return
            others = [o for o in CATALOG if o != key and self._state.get(o) in ("up", "loading")]
            reclaimable = (4 - len(self._held_cards())) + cur_cards
            victims = []
            for o in self._lru + others:
                if reclaimable >= needed:
                    break
                if o in others and o not in victims:
                    victims.append(o)
                    reclaimable += len(self._dev.get(o, "").split(",")) if self._dev.get(o) else 1
            if reclaimable < needed:
                self._state[key] = "error"
                self._err[key] = f"{needed}장 확보 불가"
                return
            for v in victims:
                self._state[v] = "stopping"
            self._pending.pop(key, None)   # 새 전환이 권위 — 묵은 대기 설정 비움
            self._par[key] = (dp, pp)
            self._state[key] = "loading"
            self._err.pop(key, None)
            self._touch(key)
        threading.Thread(target=self._transition, args=(key, victims, needed), daemon=True).start()

    def _transition(self, key, victims, needed):
        for v in victims:
            self._stop_blocking(v)
        with self._lock:
            old = self._proc.get(key)
        if old is not None:
            self._kill(old)
            with self._lock:
                self._proc.pop(key, None)
                self._dev.pop(key, None)
        elif key in self._dev:
            self._stop_blocking(key)
            with self._lock:
                self._state[key] = "loading"
        with self._lock:
            cards = self._free_cards(needed)
            if len(cards) < needed:
                self._state[key] = "error"
                self._err[key] = f"{needed}장 확보 실패"
                return
            # tp<8 아티팩트는 카드 하나를 통째로 주면 안 되고 앞 pe 개 PE 만 준다(예: tp4 → npu:0:0-3).
            pe = CATALOG[key].get("pe", 8)
            dev = (",".join(f"npu:{c}" for c in cards) if pe >= 8
                   else f"npu:{cards[0]}:0-{pe - 1}")
            self._dev[key] = dev
        self._start_and_wait(key, dev)
        # 전환 중에 dp/pp 변경 요청이 들어와 쌓였으면(=_pending), 지금 serve 를 내리고 새 설정으로
        # 즉시 다시 전환한다. (_start_and_wait 도 로딩 중 _pending 을 감지하면 일찍 빠져나온다.)
        with self._lock:
            pending = self._pending.pop(key, None)
            cur_par = self._par.get(key)
        if pending is not None and pending != cur_par:
            self._stop_blocking(key)            # 현재(옛 설정) serve 내리고 카드 반납 → state=down
            self.request(key, pending[0], pending[1])   # 새 설정으로 재전환(cur=down 이라 진행됨)

    def _start_and_wait(self, key, dev):
        m = CATALOG[key]
        art = _artifact_ref(m)
        port = m["port"]
        # 로컬 아티팩트만 미리 존재를 확인한다. 프리빌트(src="hub")는 저장소 ID 라 파일이 아니고,
        # 캐시에 없으면 serve 가 알아서 내려받는다(첫 기동은 수십 GB 다운로드가 될 수 있음).
        if m.get("src", "art") == "art" and not Path(art, "artifact.json").exists():
            with self._lock:
                self._state[key] = "error"
                self._err[key] = f"artifact 없음: {art}"
                self._dev.pop(key, None)
            return
        dp, pp = self._par.get(key, (1, 1))
        cmd = [FURIOSA_LLM, "serve", art, "--devices", dev, "--host", "0.0.0.0",
               "--port", str(port), "--enable-prefix-caching",
               *_par_flags(m["kind"], dp, pp), *_parser_flags(m)]
        try:
            logf = open(LOG_DIR / f"{port}.log", "w")
            proc = subprocess.Popen(cmd, stdout=logf, stderr=logf, start_new_session=True,
                                    env=_serve_env())
        except Exception as e:
            with self._lock:
                self._state[key] = "error"
                self._err[key] = f"serve 실행 실패: {e}"
                self._dev.pop(key, None)
            return
        with self._lock:
            self._proc[key] = proc
        base = f"http://127.0.0.1:{port}/v1"
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            # '전부 내리기' 가 눌렸으면 이 로딩을 조용히 포기(error 표시 없이 — stop_all 이 정리).
            # 또는 로딩 중 dp/pp 변경 요청(_pending)이 들어왔으면 즉시 포기 → _transition 이 새 설정으로 재기동.
            with self._lock:
                if self._stopping_all:
                    return
                pend = self._pending.get(key)
            if pend is not None and pend != self._par.get(key):
                return
            if proc.poll() is not None:
                with self._lock:
                    self._state[key] = "error"
                    self._err[key] = f"serve 조기 종료(code {proc.returncode}) — serve_logs/{port}.log"
                    self._dev.pop(key, None)
                return
            try:
                if httpx.get(base + "/models", timeout=3.0).status_code == 200:
                    with self._lock:
                        self._state[key] = "up"
                    return
            except Exception:
                pass
            time.sleep(3.0)
        self._stop_blocking(key)
        with self._lock:
            self._state[key] = "error"
            self._err[key] = f"{int(STARTUP_TIMEOUT)}초 안에 준비 안 됨 — serve_logs/{port}.log"

    def _kill(self, proc):
        try:
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    proc.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=10)
        except Exception:
            pass

    def _stop_blocking(self, key):
        with self._lock:
            proc = self._proc.get(key)
            port = CATALOG[key]["port"]
            if self._state.get(key) != "down":
                self._state[key] = "stopping"
        if proc is not None:
            self._kill(proc)
        elif _port_up(port):
            subprocess.run(["pkill", "-f", f"furiosa-llm serve.*--port {port}"], check=False)
            time.sleep(2.0)
        with self._lock:
            self._proc.pop(key, None)
            self._dev.pop(key, None)
            self._state[key] = "down"
            self._err.pop(key, None)

    def stop_all(self):
        """떠 있는 furiosa-llm serve 를 전부 종료하고 카드를 비운다(UI '전부 내리기' 버튼).
        MGR 가 띄운 것 + 터미널 등에서 띄운 것까지 모두. 로딩 중이어도 깔끔히 취소된다."""
        with self._lock:
            self._stopping_all = True       # in-flight _start_and_wait 가 error 안 내고 빠지게
            for k in CATALOG:
                if self._state.get(k) in ("up", "loading"):
                    self._state[k] = "stopping"
            procs = list(self._proc.values())
        for p in procs:
            self._kill(p)
        # 트래킹 안 되는(터미널 등에서 띄운) serve 까지 전부 — serve_models.sh stop 과 동일
        try:
            subprocess.run(["pkill", "-f", "furiosa-llm serve"], check=False, timeout=10)
        except Exception:
            pass
        time.sleep(2.0)
        with self._lock:
            self._proc.clear()
            self._dev.clear()
            self._par.clear()
            self._pending.clear()
            self._err.clear()
            self._lru = []
            for k in CATALOG:
                self._state[k] = "down"
            self._stopping_all = False

    def states(self):
        found = self._discover()    # pgrep 로 실제 살아있는 키
        with self._lock:
            snap = dict(self._state)
            procs = dict(self._proc)
        out = {}
        for k, m in CATALOG.items():
            s = snap.get(k, "down")
            if s in ("loading", "stopping"):
                out[k] = s
                continue
            if k in found:
                # 프로세스가 살아있으면 HTTP 프로브가 느려도 up 유지(busy/slow 오판 방지)
                out[k] = "up"
                continue
            if s == "up":
                # pgrep 에도 없고 상태가 up 이었으면, HTTP 로 한 번 더 확인 후에만 내림
                if _port_up(m["port"]):
                    out[k] = "up"
                    continue
                p = procs.get(k)
                new = "error" if (p is not None and p.poll() is not None) else "down"
                with self._lock:
                    self._state[k] = new
                    self._dev.pop(k, None)
                    if new == "error":
                        self._err[k] = f"serve 중단됨 — serve_logs/{m['port']}.log"
                out[k] = new
            else:
                out[k] = s
        return out


MGR = ServeManager()

# ── furiosa RNGD 테마 (furiosa-apps chat-playground 디자인: 순수 검정 + 빨강·시안·보라) ──
BG = "#000000"       # 메인 배경(furiosa = 순수 검정)
SIDE = "#0a0a0a"     # 사이드바
ELEV = "#1c1c1c"     # 입력창·검색창
CARD = "#151515"     # 카드·아코디언·선택 항목
BORDER = "#3a3a3a"   # 경계선(furiosa #444 계열)
TXT = "#e0e0e0"
MUTE = "#888888"
RED = "#dc2626"      # furiosa 강조(전송/Enter 버튼)
CYAN = "#76d6ff"     # 메트릭 제목
PURPLE = "#cdbbff"   # 라인·DEMO 배지
CSS = f"""
@keyframes ledpulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.18; }} }}
.led-pulse {{ animation: ledpulse 1.1s ease-in-out infinite; }}
.gradio-container {{ max-width:100% !important; padding:0 !important; background:{BG} !important; color:{TXT} !important; }}
/* 최외곽 래퍼 main.fillable.app 의 max-width:1536·margin(auto→32px)·padding:32px 가 양옆을 비움 → 0/100% 로 덮어 빈 공간 제거 */
.gradio-container .app, main.fillable, main.app {{ max-width:100% !important; margin:0 !important; padding:0 !important; }}
footer, .show-api, .built-with {{ display:none !important; }}
* {{ --color-accent:{CARD} !important; --color-accent-soft:{CARD} !important; }}
.gradio-container .prose, .gradio-container label, .gradio-container span {{ color:{TXT}; }}
input[type=range] {{ accent-color:{RED} !important; }}
input:focus, textarea:focus, .gr-box:focus-within {{ outline:none !important; box-shadow:none !important; }}

/* furiosa 헤더 (로고 + Furiosa RNGD Chat + DEMO 배지 | 모델) */
#furheader {{ background:{BG} !important; border-bottom:1px solid {BORDER}; padding:0 18px !important; min-height:62px; align-items:center !important; gap:0 !important; }}
#brand {{ display:flex; align-items:center; gap:11px; height:62px; }}
#brand img {{ height:26px; width:auto; }}
#brand .ttl {{ color:#fff; font-weight:700; font-size:1.2rem; letter-spacing:.4px; }}
#brand .demo {{ background:{PURPLE}; color:#000; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; letter-spacing:.5px; }}
#model-dd {{ max-width:480px !important; min-width:340px !important; }}
#model-dd, #model-dd .wrap, #model-dd .secondary-wrap {{ background:transparent !important; border:none !important; box-shadow:none !important; min-height:0 !important; }}
/* 긴 모델명이 잘리지 않게: 폭 넉넉히 + 한 줄 + 넘치면 …(끝 칩은 input 밖 secondary-wrap 라 안 가림) */
/* 우측 정렬 글자가 세모(caret) 아이콘과 겹치지 않게 input 오른쪽에 caret 폭만큼 여백 확보.
   주의: .secondary-wrap 에는 손대지 않는다 — gradio 에선 그 래퍼가 input 을 품고 있어
   pointer-events 등을 건드리면 클릭(드롭다운 열기)이 막힌다. 패딩만으로 겹침을 해결한다. */
#model-dd input {{ font-weight:600 !important; font-size:13.5px !important; color:{TXT} !important; font-family:monospace !important; cursor:pointer; text-align:right; text-overflow:ellipsis; white-space:nowrap; overflow:hidden; padding-right:30px !important; }}
#model-dd .wrap:hover {{ background:{CARD} !important; border-radius:8px !important; }}

/* 사이드바 */
#sidebar {{ background:{SIDE} !important; border-right:1px solid {BORDER}; padding:10px 8px !important; min-height:96vh; }}
#sidebar .gap, #sidebar .form {{ background:transparent !important; border:none !important; }}
#newchat-btn {{ background:transparent !important; border:1px solid {BORDER} !important; color:{TXT} !important; border-radius:10px !important; font-weight:500; text-align:left; }}
#newchat-btn:hover {{ background:{CARD} !important; border-color:{RED} !important; }}
#search-box {{ background:transparent !important; }}
#search-box input, #search-box textarea {{ background:{ELEV} !important; border:none !important; color:{TXT} !important; border-radius:10px !important; padding:9px 12px !important; }}
#sidebar .label-wrap, #recent-label p {{ color:{MUTE} !important; font-size:12px !important; font-weight:600; padding:6px 6px 2px !important; margin:0 !important; }}
#convo-list {{ border:none !important; background:transparent !important; box-shadow:none !important; }}
#convo-list label {{ display:block !important; width:100%; padding:8px 10px !important; margin:1px 0 !important; border-radius:8px !important; cursor:pointer; color:#cfcfd6 !important; font-size:14px; border:none !important; background:transparent !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
#convo-list label:hover {{ background:{CARD} !important; }}
#convo-list input[type=radio] {{ display:none !important; }}
#convo-list label:has(input:checked) {{ background:{CARD} !important; color:#fff !important; box-shadow:inset 2px 0 0 {RED}; }}
#del-btn {{ background:transparent !important; border:none !important; color:{MUTE} !important; font-size:12.5px !important; text-align:left; }}
#del-btn:hover {{ color:{RED} !important; }}
#statusbox, #statusbox div {{ font-size:12.5px; line-height:1.7; color:{TXT} !important; }}
/* '전부 내리기' — 사이드바 톤(투명·테두리)에 맞추되 카드를 비우는 동작이라 빨강(furiosa 강조)으로 hover */
#stopall-btn {{ background:transparent !important; border:1px solid {BORDER} !important; color:{MUTE} !important; font-size:12.5px !important; border-radius:10px !important; }}
#stopall-btn:hover {{ border-color:{RED} !important; color:{RED} !important; background:#1a0d0d !important; }}
#sidebar .accordion, #sidebar .accordion * {{ border-color:{BORDER} !important; }}
#userchip {{ border-top:1px solid {BORDER}; margin-top:8px; padding:10px 6px 4px; color:{MUTE}; font-size:13px; }}
#settings-acc, #rag-acc {{ border:none !important; background:transparent !important; }}

/* 메인 */
#main {{ background:{BG} !important; }}

/* 우측 실시간 대시보드 */
#dashboard {{ background:{BG} !important; border-left:1px solid {BORDER}; padding:16px 12px !important; min-height:96vh; }}
#dashbox {{ background:transparent !important; }}

/* RAG 컨트롤 */
#rag-files {{ background:{ELEV} !important; border:1px dashed {BORDER} !important; border-radius:10px !important; }}
#rag-info {{ font-size:12px; color:{MUTE}; line-height:1.6; }}

/* 챗봇 — furiosa 풍 (질문=어두운 말풍선, 답변=투명 폭 꽉 채움) */
#chatbot {{ background:transparent !important; border:none !important; max-width:100% !important; margin:0 !important; padding:0 22px !important; }}
#inputwrap {{ max-width:100% !important; margin:0 !important; }}
#chatbot .message-wrap, #chatbot .message-row {{ box-shadow:none !important; }}
/* 중첩 둥근박스 원흉: gradio 가 .user-row(행)·.message-bubble-border(래퍼)·.user(버블) 각각에
   배경/테두리/radius 를 줘서 박스가 겹쳐 보였다. → 행과 래퍼는 완전히 투명·무radius 로 죽이고
   박스는 .user 버블 '한 겹만' 남긴다. */
#chatbot .message-bubble-border {{ border:none !important; border-radius:0 !important; background:transparent !important; box-shadow:none !important; }}
#chatbot .user-row, #chatbot .bot-row {{ background:transparent !important; }}
#chatbot .bot-row .message, #chatbot .bot-row .bubble, #chatbot .bot {{ background:transparent !important; border:none !important; color:{TXT} !important; }}
#chatbot .user {{ background:{CARD} !important; border:1px solid {BORDER} !important; color:#fff !important; border-radius:14px !important; }}
#chatbot .user .message-content, #chatbot .user .prose, #chatbot .user .md, #chatbot .user-row .bubble, #chatbot .user-row .message-content {{ background:transparent !important; border:none !important; border-radius:0 !important; box-shadow:none !important; padding:0 !important; }}
#chatbot .avatar-container, #chatbot .avatar-image {{ display:none !important; }}
#chatbot .message, #chatbot .message-content, #chatbot .bubble, #chatbot .message-row {{ opacity:1 !important; }}
#chatbot .user-row .message-content, #chatbot .user-row .message {{ color:#fff !important; }}
#chatbot .bot-row .message-content, #chatbot .bot-row .message {{ color:{TXT} !important; }}
/* 답변(봇)은 채팅 폭을 꽉 채우게 — Gradio 기본 width 제한 해제 (질문 말풍선은 우측 컴팩트 유지) */
#chatbot .bot-row, #chatbot .bot-row .message, #chatbot .bot-row .message-content, #chatbot .bot-row .prose {{ max-width:100% !important; width:100% !important; }}
/* 가로 스크롤 방지: 대화 내용을 칸 폭에 맞춘다. 긴 텍스트/URL 은 줄바꿈, 코드블록·표는 '자체' 스크롤로 가둠. */
#chatbot, #chatbot .message-wrap, #chatbot .bubble-wrap, #main, #main > div {{ overflow-x:hidden !important; }}
#chatbot .message-content, #chatbot .prose, #chatbot .md, #chatbot p, #chatbot li, #chatbot span {{ overflow-wrap:break-word !important; word-break:break-word !important; max-width:100% !important; }}
#chatbot pre {{ max-width:100% !important; overflow-x:auto !important; white-space:pre !important; }}
#chatbot table {{ display:block !important; max-width:100% !important; overflow-x:auto !important; }}
/* 사고 과정 — 접힘 = 연회색 한 줄, 펼침 = 은은한 박스 안 회색 추론 */
#chatbot details {{ background:transparent !important; border:none !important; padding:0 !important; margin:2px 0 10px !important; }}
#chatbot details summary {{ color:{MUTE} !important; font-size:13.5px !important; cursor:pointer; list-style:none; outline:none; user-select:none; }}
#chatbot details summary::-webkit-details-marker {{ display:none; }}
#chatbot details summary::marker {{ content:""; }}
#chatbot details summary::before {{ content:"▸"; margin-right:6px; color:{MUTE}; font-size:11px; }}
#chatbot details[open] summary::before {{ content:"▾"; }}
#chatbot details[open] {{ background:{CARD} !important; border-radius:10px !important; padding:10px 14px !important; }}
#chatbot details[open] > *:not(summary) {{ color:#9a9aa6 !important; font-size:13px !important; line-height:1.6; }}

/* 입력 알약 */
#inputwrap {{ padding:8px 22px 16px !important; }}
#inputbar {{ background:{ELEV} !important; border:1px solid {BORDER} !important; border-radius:26px !important; padding:6px 6px 6px 18px !important; align-items:center !important; }}
#inputbar:focus-within {{ border-color:{RED} !important; }}
/* 겉 알약 안의 텍스트박스 내부 박스(block/wrap)를 완전히 투명화 → 박스 안 박스 제거 */
#inputbar .block, #inputbar .wrap, #inputbar label, #inputbar .input-container {{ background:transparent !important; border:none !important; box-shadow:none !important; border-radius:0 !important; padding:0 !important; }}
#inputbar textarea {{ background:transparent !important; border:none !important; color:{TXT} !important; box-shadow:none !important; font-size:15px; padding:8px 0 !important; }}
#send-btn, #stop-btn {{ border-radius:50% !important; min-width:38px !important; max-width:38px; width:38px; height:38px; padding:0 !important; font-size:18px; line-height:1; box-shadow:none !important; }}
#send-btn {{ background:{RED} !important; color:#fff !important; border:none !important; }}
#send-btn:hover {{ background:#ef3b3b !important; }}
#stop-btn {{ background:#fff !important; color:#111 !important; border:none !important; }}
#hint {{ color:{MUTE}; font-size:11.5px; text-align:center; padding:6px 0 0; }}
"""
_COLOR = {"up": "#22c55e", "loading": "#eab308", "stopping": "#eab308", "down": "#6b7280", "error": "#ef4444"}

# Base 테마 기본값이 흰색이라 검색창·입력창·아코디언·버튼이 희게 뜨는 것을 막아 검정으로 고정.
_DARKVARS = dict(
    body_background_fill=BG, body_text_color=TXT, body_text_color_subdued=MUTE,
    background_fill_primary=BG, background_fill_secondary=SIDE,
    block_background_fill=BG, block_border_color=BORDER,
    block_label_background_fill=BG, block_label_text_color=MUTE, block_title_background_fill=BG,
    border_color_primary=BORDER, border_color_accent=BORDER,
    input_background_fill=ELEV, input_background_fill_focus=ELEV, input_background_fill_hover=ELEV,
    input_border_color=BORDER, input_placeholder_color=MUTE,
    button_secondary_background_fill=CARD, button_secondary_background_fill_hover="#262626",
    button_secondary_text_color=TXT, panel_background_fill=SIDE, panel_border_color=BORDER,
    color_accent_soft=CARD, code_background_fill="#0d0d0d",
)
THEME = gr.themes.Base(primary_hue="red", secondary_hue="gray", neutral_hue="gray").set(
    **_DARKVARS, **{f"{k}_dark": v for k, v in _DARKVARS.items()})


def status_html():
    """LED + 모델명 + (떠 있을 때만) 사용 카드·병렬구성(dp·pp). 실제 serve 프로세스의
    --devices/-pp/-dp 에서 읽으므로(_discover) UI 선택이 진짜 적용됐는지 여기서 확인된다."""
    st = MGR.states()
    rows = []
    for k, m in CATALOG.items():
        s = st[k]
        cls = ' class="led-pulse"' if s in ("loading", "stopping") else ''
        dot = (f'<span{cls} style="display:inline-block;width:9px;height:9px;border-radius:50%;'
               f'background:{_COLOR[s]};margin-right:8px;vertical-align:middle;"></span>')
        dev = MGR.device(k)
        if m["kind"] != "tp32" and s in ("up", "loading"):
            dp_v, pp_v = MGR.par(k)
            dev = f"{dev} · dp{dp_v}·pp{pp_v}" if dev else dev
        info = f' <span style="color:{MUTE};">{dev}</span>' if s in ("up", "loading") and dev else ""
        if s == "error" and MGR.error(k):
            info = ' <span style="color:#ef4444;">실패</span>'
        rows.append(f'<div style="padding:1px 0;">{dot}{m["name"]}{info}</div>')
    return (f'<div style="color:{MUTE};margin-bottom:5px;">🟢 켜짐 · 🟡 전환중 · 🔴 꺼짐</div>'
            + "".join(rows))


def status_struct():
    """모델 상태 패널의 '정적 구조'(값 자리만 id 로). LED 점/정보 텍스트는 클라이언트가 /status_data
    를 폴링해 제자리 갱신 → 패널 전체 재렌더(깜빡임) 없이 바뀐 LED 만 바뀐다(전환 LED 펄스는 CSS)."""
    rows = []
    for k, m in CATALOG.items():
        dot = (f'<span id="st-dot-{k}" style="display:inline-block;width:9px;height:9px;'
               f'border-radius:50%;background:{_COLOR["down"]};margin-right:8px;vertical-align:middle;"></span>')
        info = f'<span id="st-info-{k}" style="color:{MUTE};"></span>'
        rows.append(f'<div style="padding:1px 0;">{dot}{m["name"]} {info}</div>')
    return (f'<div style="color:{MUTE};margin-bottom:5px;">🟢 켜짐 · 🟡 전환중 · 🔴 꺼짐</div>'
            + "".join(rows))


def status_data():
    """모델 상태를 JSON 으로(클라이언트 폴링용). 각 모델: 색·펄스여부·정보텍스트·에러여부."""
    st = MGR.states()
    out = []
    for k, m in CATALOG.items():
        s = st[k]
        dev = MGR.device(k)
        if m["kind"] != "tp32" and s in ("up", "loading"):
            dp_v, pp_v = MGR.par(k)
            dev = f"{dev} · dp{dp_v}·pp{pp_v}" if dev else dev
        info = dev if (s in ("up", "loading") and dev) else ""
        if s == "error" and MGR.error(k):
            info = "실패"
        out.append({"key": k, "color": _COLOR[s], "pulse": s in ("loading", "stopping"),
                    "info": info, "err": s == "error"})
    return {"models": out}


# LED 자동 갱신은 '전환 중'에만 Timer 를 켜서 돌린다. 유휴 상태에선 Timer 를 꺼
# (active=False) 패널을 아예 다시 그리지 않으므로 '전체 깜빡임'이 없다.
# (gr.skip() 은 Timer.tick 에서 프런트 재렌더를 막지 못해, 켜져 있으면 매 틱 패널이
#  통째로 교체되며 깜빡이기 때문에 — 유휴 시엔 끄는 것이 정답.)
_LAST_STATUS = {"html": None}


def _transitioning():
    return any(MGR.state(k) in ("loading", "stopping") for k in CATALOG)


def status_tick():
    """Timer tick: 상태 HTML 갱신 + 전환이 끝났으면 Timer 를 스스로 끈다.
    출력 2개: (status, timer)."""
    h = status_html()
    changed = h != _LAST_STATUS["html"]
    _LAST_STATUS["html"] = h
    status_out = h if changed else gr.skip()
    timer_out = gr.skip() if _transitioning() else gr.Timer(active=False)
    return status_out, timer_out


def status_force():
    h = status_html()
    _LAST_STATUS["html"] = h
    return h


def stop_all_models():
    """UI '전부 내리기' 버튼: 떠 있는 모델을 전부 종료(카드 비움). 상태 LED 갱신은 클라이언트 폴링."""
    MGR.stop_all()


def load_status():
    """페이지 로드: 상태 1회 갱신 + 전환 중이면 Timer 켬. 출력 2개: (status, timer)."""
    return status_force(), gr.Timer(active=_transitioning())


# ── 대화 영구 저장 ────────────────────────────────────────────────
def _new_conv_id():
    return "c" + dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _title_of(messages):
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content", "").strip():
            t = msg["content"].strip().replace("\n", " ")
            return (t[:30] + "…") if len(t) > 30 else t
    return "(빈 대화)"


def _save_convo(cid, model_name, messages):
    if not cid or not any(msg.get("role") == "user" for msg in messages):
        return
    (CONV_DIR / f"{cid}.json").write_text(json.dumps(
        {"id": cid, "title": _title_of(messages), "model": model_name,
         "updated": dt.datetime.now().isoformat(timespec="seconds"), "messages": messages},
        ensure_ascii=False, indent=2))


def _load_convo(cid):
    try:
        return json.loads((CONV_DIR / f"{cid}.json").read_text()).get("messages", [])
    except Exception:
        return []


def _convo_choices(query=""):
    items = []
    for f in sorted(CONV_DIR.glob("c*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
            title = d.get("title") or d["id"]
            if not query or query.lower() in title.lower():
                items.append((title, d["id"]))
        except Exception:
            pass
    return items


# ── 생성 ──────────────────────────────────────────────────────────
def _client(base_url):
    return OpenAI(base_url=base_url, api_key="dummy", timeout=600)


def _resolve_model_id(base_url):
    return _client(base_url).models.list().data[0].id


def _think_block(think, label):
    """추론 텍스트를 ChatGPT식 접힘 헤더로. 라벨만 보이고, 누르면 전체 추론 펼침.
    Gradio 5.50 은 allow_tags=True + '블록' 포맷(태그가 줄 단독)일 때만 <details> 를 렌더한다."""
    return f"<details>\n<summary>{label}</summary>\n\n{think}\n\n</details>\n\n"


def _stream_reply(base_url, model_id, msgs, temperature, max_tokens, rec=None):
    """답변 스트리밍. 추론(reasoning)은 ChatGPT처럼 연한 회색 접힘 줄로:
    추론 중엔 '💭 생각하는 중…', 끝나면 '💭 N초 동안 생각함'(클릭하면 전체 추론).
    rec 가 주어지면 대시보드용 메트릭(첫 토큰 시각·토큰 수·정확 completion_tokens)을 기록한다.
    stream_options(include_usage)로 furiosa-llm serve 가 주는 정확한 토큰수를 받는다."""
    stream = _client(base_url).chat.completions.create(
        model=model_id, messages=msgs, temperature=temperature, max_tokens=int(max_tokens),
        stream=True, stream_options={"include_usage": True})
    think, body = "", ""
    t0 = time.time()
    think_secs = None
    for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if not chunk.choices:
            if usage is not None and rec is not None:       # 마지막 usage 청크 → 정확한 토큰수
                rec["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
            continue
        delta = chunk.choices[0].delta
        r = getattr(delta, "reasoning", None)
        if r:
            think += r
            if rec is not None:
                METRICS.first_token(rec)
                METRICS.add_chars(rec, len(r))   # 글자 누적 → 라이브 TPS 추정(최종은 usage 로 보정)
        if delta.content:
            if think and think_secs is None:           # 추론 끝, 답변 시작 → 걸린 시간 확정
                think_secs = max(1, round(time.time() - t0))
            body += delta.content
            if rec is not None:
                METRICS.first_token(rec)
                METRICS.add_chars(rec, len(delta.content))
        if think:
            label = (f"💭 {think_secs}초 동안 생각함" if think_secs is not None else "💭 생각하는 중…")
            yield _think_block(think, label) + body
        else:
            yield body or "…"


# 전송/중지 버튼 토글 상태
_GEN = (gr.update(visible=False), gr.update(visible=True))     # 생성중: 전송 숨김, 중지 표시
_IDLE = (gr.update(visible=True), gr.update(visible=False))    # 대기: 전송 표시, 중지 숨김


def _fit_context(msgs, ctx, reserve=768):
    """이력이 모델 컨텍스트(ctx)를 넘으면 오래된 대화 턴부터 버려 항상 들어가게 만든다.
    system 메시지(시스템 프롬프트·RAG)는 보존하고, 최근 턴을 우선 남긴다(최소 마지막 1턴은 유지).
    토큰은 글자수/3 으로 보수 추정. 모델을 작은 ctx 로 바꿔도 기존 대화를 이어갈 수 있게 한다."""
    sys_msgs = [mm for mm in msgs if mm.get("role") == "system"]
    convo = [mm for mm in msgs if mm.get("role") != "system"]

    def toklen(ms):
        return sum(len(x.get("content", "")) for x in ms) // 3 + 16

    budget = max(512, ctx - reserve)
    kept = []
    for mm in reversed(convo):                      # 최근 턴부터 채운다
        if kept and toklen(sys_msgs + [mm] + kept) > budget:
            break
        kept.insert(0, mm)
    return sys_msgs + kept


# 답변 끝에 화면용으로 붙인 모델 마커(<span class="ans-model-meta">)·RAG 각주(🔎)를 떼어낸다(프롬프트 오염 방지).
_META_RE = re.compile(
    r'(?:\s*\n\n<span class="ans-model-meta"[^>]*>[^<]*</span>'
    r'|\s*\n\n<div style="text-align:right;color:#6b6b73[^>]*>[^<]*</div>'
    r'|\s*\n\n<span style="color:#888;font-size:12px;">🔎 RAG 참조:[^<]*</span>)+\s*$')


def _strip_meta(content: str) -> str:
    return _META_RE.sub("", content or "")


def _generate(history, conv_id, model_name, dp, pp, rag_on, rag_k, system_prompt, temperature, max_tokens):
    """history(마지막 user) 뒤에 답변 스트리밍. 출력 7개:
    (chatbot, conv_id, txt, convo, status, send_btn, stop_btn).
    rag_on 이면 업로드 문서에서 관련 청크를 찾아 컨텍스트로 주입하고 출처를 각주로 단다."""
    if not conv_id:
        conv_id = _new_conv_id()
    history = list(history)
    history.append({"role": "assistant", "content": ""})
    yield history, conv_id, "", gr.update(), gr.skip(), *_GEN     # 생성 시작 → 중지 버튼

    key = DISPLAY2KEY.get(model_name)
    if key is None:
        history[-1]["content"] = f"⚠️ 알 수 없는 모델: {model_name}"
        _save_convo(conv_id, model_name, history)
        yield history, conv_id, "", gr.update(choices=_convo_choices(), value=conv_id), gr.skip(), *_IDLE
        return
    m = CATALOG[key]
    port = m["port"]
    base_url = f"http://127.0.0.1:{port}/v1"

    if MGR.state(key) != "up" and not _port_up(port):
        MGR.request(key, dp, pp)
        t0 = time.time()
        while True:
            if MGR.state(key) == "up" or _port_up(port):
                break
            if MGR.state(key) == "error":
                history[-1]["content"] = f"⚠️ '{model_name}' 띄우기 실패: {MGR.error(key)}"
                _save_convo(conv_id, model_name, history)
                yield history, conv_id, "", gr.update(choices=_convo_choices(), value=conv_id), gr.skip(), *_IDLE
                return
            if MGR.state(key) == "down":   # 이전 모델 정리로 down 까지 떨어졌으면 다시 요청(idempotent)
                MGR.request(key, dp, pp)
            history[-1]["content"] = f"⏳ '{model_name}' 준비 중… ({int(time.time() - t0)}초). 무거운 모델은 수 분 걸립니다."
            yield history, conv_id, "", gr.update(), gr.skip(), gr.skip(), gr.skip()
            time.sleep(2.0)
            if time.time() - t0 > STARTUP_TIMEOUT + 30:
                history[-1]["content"] = f"⚠️ '{model_name}' 준비 시간 초과 — serve_logs/{port}.log"
                _save_convo(conv_id, model_name, history)
                yield history, conv_id, "", gr.update(choices=_convo_choices(), value=conv_id), gr.skip(), *_IDLE
                return

    try:
        model_id = _resolve_model_id(base_url)
    except Exception as e:
        history[-1]["content"] = f"⚠️ 서버 연결 실패: {e}"
        _save_convo(conv_id, model_name, history)
        yield history, conv_id, "", gr.update(choices=_convo_choices(), value=conv_id), gr.skip(), *_IDLE
        return

    msgs = ([{"role": "system", "content": system_prompt}] if system_prompt and system_prompt.strip() else [])
    # 답변 끝의 모델표식/ RAG 각주는 화면 표시용이라 다음 프롬프트엔 빼고 보낸다.
    msgs += [({"role": mm["role"], "content": _strip_meta(mm.get("content", ""))}
              if mm.get("role") == "assistant" else mm) for mm in history[:-1]]

    # ── RAG: 켜져 있고 문서가 있으면 마지막 질문으로 검색해 컨텍스트를 질문 직전에 주입 ──
    rag_sources = []
    if rag_on and RAG.summary()[1] > 0:
        user_q = next((mm["content"] for mm in reversed(history[:-1]) if mm.get("role") == "user"), "")
        ctx, rag_sources = RAG.context(user_q, int(rag_k))
        if ctx:
            rag_sys = {"role": "system", "content": (
                "다음은 사용자가 올린 문서에서 질문과 관련해 찾은 발췌입니다. 답변에 활용하고, "
                "사용한 부분은 [번호]로 인용하세요. 문서에 답이 없으면 일반 지식으로 답하되 그 점을 밝히세요.\n\n"
                + ctx)}
            msgs.insert(len(msgs) - 1, rag_sys)   # 마지막 user 턴 바로 앞에 삽입

    # 컨텍스트 맞춤: 이력이 이 모델 ctx 를 넘으면 오래된 턴부터 버려 항상 들어가게 한다.
    # (모델을 더 작은 ctx 로 바꿔도 '기존 채팅'이 그대로 이어진다 — 새 채팅 안 만들어도 됨.)
    msgs = _fit_context(msgs, m["ctx"])
    # 초과 방지: prompt + max_tokens <= ctx. 프롬프트 토큰을 보수적으로 추정해 클램프.
    est_prompt = sum(len(mm.get("content", "")) for mm in msgs) // 3 + 16
    eff_max = max(16, min(int(max_tokens), m["ctx"] - est_prompt - 256))
    rec = METRICS.start()
    try:
        for partial in _stream_reply(base_url, model_id, msgs, temperature, eff_max, rec=rec):
            history[-1]["content"] = partial
            yield history, conv_id, "", gr.update(), gr.skip(), gr.skip(), gr.skip()
        if rag_sources:   # 답변 끝에 출처 각주(furiosa/kotaemon 식 근거 표시)
            history[-1]["content"] += (
                f"\n\n<span style=\"color:#888;font-size:12px;\">🔎 RAG 참조: "
                f"{', '.join(rag_sources)}</span>")
        # 이 답변을 낸 모델 — 숨김 마커로 심어두면 클라이언트 JS 가 읽어서 답변의 복사/재생성 버튼
        # (.message-buttons-left) 바로 옆에 작게(튀지 않는 회색) 붙인다. (오른쪽 끝이라 잘리던 것 해결)
        history[-1]["content"] += (
            f'\n\n<span class="ans-model-meta" style="display:none">{model_name}</span>')
        yield history, conv_id, "", gr.update(), gr.skip(), gr.skip(), gr.skip()
    except Exception as e:
        history[-1]["content"] = f"⚠️ 생성 중 에러: {e}"
        yield history, conv_id, "", gr.update(), gr.skip(), gr.skip(), gr.skip()
    finally:
        METRICS.finish(rec, rec.get("completion_tokens"))
    _save_convo(conv_id, model_name, history)
    yield history, conv_id, "", gr.update(choices=_convo_choices(), value=conv_id), gr.skip(), *_IDLE


def respond(user_msg, history, conv_id, model_name, dp, pp, rag_on, rag_k, system_prompt, temperature, max_tokens):
    user_msg = (user_msg or "").strip()
    history = list(history or [])
    if not user_msg:
        yield history, conv_id, "", gr.update(), gr.skip(), gr.skip(), gr.skip()
        return
    if not conv_id:
        conv_id = _new_conv_id()
    history.append({"role": "user", "content": user_msg})
    # 질문을 입력 즉시 대화창에 노출 + 전송→중지 토글
    yield history, conv_id, "", gr.update(), gr.skip(), *_GEN
    yield from _generate(history, conv_id, model_name, dp, pp, rag_on, rag_k, system_prompt, temperature, max_tokens)


def regenerate(history, conv_id, model_name, dp, pp, rag_on, rag_k, system_prompt, temperature, max_tokens):
    history = list(history or [])
    if history and history[-1].get("role") == "assistant":
        history.pop()
    if not history or history[-1].get("role") != "user":
        yield history, conv_id, "", gr.update(), gr.skip(), gr.skip(), gr.skip()
        return
    yield from _generate(history, conv_id, model_name, dp, pp, rag_on, rag_k, system_prompt, temperature, max_tokens)


def delete_convo(selected_cid, cur_conv_id):
    """대화 목록에서 선택한 대화를 삭제. 열려 있던 대화면 화면도 비움."""
    if selected_cid:
        try:
            (CONV_DIR / f"{selected_cid}.json").unlink()
        except Exception:
            pass
    if selected_cid and selected_cid == cur_conv_id:
        return [], "", gr.update(choices=_convo_choices(), value=None)
    return gr.update(), cur_conv_id, gr.update(choices=_convo_choices(), value=None)


def new_chat():
    return [], _new_conv_id(), gr.update(value=None), ""


def load_chat(cid):
    if not cid:
        return gr.update(), gr.update()
    return _load_convo(cid), cid


def filter_convos(query):
    return gr.update(choices=_convo_choices(query or ""))


def _par_updates(model_name, dp, pp):
    """모델 종류에 맞춰 dp·pp 드롭다운을 재구성하고, 적용할 (dp,pp) 를 함께 돌려준다.
    - tp32: dp·pp 비활성(4장 고정, 둘 다 1·선택 불가)
    - pe<8(부분 카드)·FXB(no_pp): pp 는 1 뿐 — 전자는 dp 도 1, 후자는 dp 만 고른다.
    - 그 밖의 tp8: pp 는 _pp_choices(pp_min 이상), dp 는 dp×pp ≤ 4 장.
    반환: (dp_update, pp_update, dp, pp)"""
    key = DISPLAY2KEY.get(model_name)
    m = CATALOG.get(key, {})
    if not m or m.get("kind") == "tp32":
        return (gr.update(value=1, choices=[1], interactive=False),
                gr.update(value=1, choices=[1], interactive=False), 1, 1)
    if m.get("pe", 8) < 8:   # 카드 하나의 일부 PE 만 쓰는 모델 — 쪼개거나 복제할 대상이 아니다
        return (gr.update(value=1, choices=[1], interactive=False),
                gr.update(value=1, choices=[1], interactive=False), 1, 1)
    pps = _pp_choices(m)
    # 요청값을 허용 목록으로 스냅(같은 거리면 작은 쪽) — 예: pp_min=2 인데 1 이 들어오면 2 로.
    pp = min(pps, key=lambda n: (abs(n - max(1, int(pp or 1))), n))
    max_dp = max(1, 4 // pp)                      # 카드 4장 한도: dp ≤ 4/pp
    dp = max(1, min(int(dp or 1), max_dp))
    return (gr.update(value=dp, choices=list(range(1, max_dp + 1)), interactive=True),
            gr.update(value=pp, choices=pps, interactive=len(pps) > 1), dp, pp)


def on_model_change(model_name, dp, pp):
    """모델 변경 → on-demand serve 즉시 시작 후 바로 반환(터널 연결 장시간 점유 X).
    dp·pp 컨트롤 재구성 + max_tokens 를 그 모델 최대치로 재설정. 모델 상태 LED·대시보드 갱신은
    클라이언트 폴링(/status_data·/dash_metrics)이 담당. 출력 3개: (maxtok, dp, pp)."""
    key = DISPLAY2KEY.get(model_name)
    ctx = CATALOG.get(key, {}).get("ctx", 8192)
    dp_u, pp_u, dp_v, pp_v = _par_updates(model_name, dp, pp)
    MGR.request(key, dp_v, pp_v)
    _LAST_MODEL.update(name=model_name, dp=dp_v, pp=pp_v, user_set=True)   # 새로고침 후 복원용 기억
    return gr.update(maximum=ctx, value=ctx), dp_u, pp_u


def on_par_change(model_name, dp, pp):
    """dp/pp 변경 → 새 병렬 구성으로 재-serve. dp×pp>4 면 제약에 맞춰 자동 보정.
    상태/대시보드는 클라이언트 폴링이 갱신. 출력 2개: (dp, pp)."""
    key = DISPLAY2KEY.get(model_name)
    dp_u, pp_u, dp_v, pp_v = _par_updates(model_name, dp, pp)
    MGR.request(key, dp_v, pp_v)
    _LAST_MODEL.update(name=model_name, dp=dp_v, pp=pp_v, user_set=True)
    return dp_u, pp_u


def _serving_model_key():
    """지금 NPU 에 떠 있는(serving) 모델 키 하나. up 우선, 없으면 loading, 없으면 None.
    (MGR._discover 가 pgrep 으로 실제 furiosa-llm serve 프로세스를 읽으므로 터미널로 띄운 것도 잡힌다.)"""
    try:
        st = MGR.states()
    except Exception:
        return None
    for want in ("up", "loading"):
        for k in CATALOG:
            if st.get(k) == want:
                return k
    return None


def _initial_model():
    """첫 시작 모델: 사용자가 아직 안 바꿨으면 '지금 떠 있는 모델', 없으면 DEFAULT_MODEL.
    떠 있는 모델이면 그 실제 dp·pp 구성까지 _LAST_MODEL 에 반영한다."""
    if not _LAST_MODEL.get("user_set"):
        k = _serving_model_key()
        if k:
            try:
                dp_v, pp_v = MGR.par(k)
            except Exception:
                dp_v, pp_v = 1, 1
            _LAST_MODEL.update(name=CATALOG[k]["name"], dp=dp_v or 1, pp=pp_v or 1)
    return _LAST_MODEL["name"]


def restore_model():
    """페이지(크롬) 새로고침/첫 접속 시 시작 모델을 드롭다운에 지정.
    아직 아무도 안 바꿨으면 '지금 NPU 에 떠 있는 모델'로(없으면 default), 바꿨으면 마지막 선택으로.
    그 모델에 맞는 max_tokens·dp·pp 도 함께 맞춘다. 출력 4개: (model_dd, maxtok, dp, pp)."""
    name = _initial_model()
    key = DISPLAY2KEY.get(name)
    ctx = CATALOG.get(key, {}).get("ctx", 8192)
    dp_u, pp_u, _, _ = _par_updates(name, _LAST_MODEL["dp"], _LAST_MODEL["pp"])
    return gr.update(value=name), gr.update(maximum=ctx, value=ctx), dp_u, pp_u


# ── 실시간 대시보드 ──────────────────────────────────────────────────
# LED status 와 같은 전략: 타이머는 '생성 중(+여유 5초)'에만 켜고 유휴엔 끈다.
# (이 파일이 실측한 'always-on Timer + gr.skip() 은 매 틱 재렌더되어 깜빡인다'는 발견 때문 —
#  status_tick 주석 참고. dash_timer 를 생성 시 켜고 활동이 멎으면 스스로 끈다.)
_LAST_DASH = {"html": None}
DASH_IDLE_OFF = 5.0   # 마지막 토큰 후 이 시간(초) 지나면 타이머 자동 off


def _active_cards(model_name):
    """선택 모델이 실제 점유한 NPU 카드 인덱스 집합(없으면 None=전체). 대시보드가 '그 모델의
    카드' 전력/온도/사용률만 보도록 — 다른 모델 부하가 새어들지 않게."""
    key = DISPLAY2KEY.get(model_name)
    dev = MGR.device(key) if key else ""
    cards = {int(d.split(":")[1]) for d in dev.split(",") if d.startswith("npu:")}
    return cards or None


def dash_metrics_data(model_name: str = ""):
    """대시보드 클라이언트(/dash_metrics)가 폴링하는 데이터: HW 표본 1회 + 현재 수치 JSON + active.
    active(생성중+5초 / 전환중) 면 클라가 빠르게(0.8s), 아니면 느리게(4s) 폴링한다."""
    try:
        METRICS.sample(_active_cards(model_name) if model_name else None)
    except Exception:
        pass
    data = METRICS.metrics_json()
    data["active"] = ((time.time() - METRICS.last_activity) <= DASH_IDLE_OFF) or _transitioning()
    return data


# 클라이언트 폴링 JS: /dash_metrics 를 받아 각 칸의 '값/막대/스파크라인'만 제자리 갱신한다.
# 패널 HTML 을 통째로 안 바꾸므로 깜빡임이 없고(=#4), 변한 칸(예: NPU memory)만 실제로 바뀐다(=#3).
POLL_JS = r"""
() => {
  if (window.__dashPolling) return; window.__dashPolling = true;
  const $ = (id) => document.getElementById(id);
  const setT = (id, t) => { const e=$(id); if(e && e.textContent!==t) e.textContent=t; };
  const fmt = (v) => { v=+v; if(!isFinite(v)||v===0) return '0'; const a=Math.abs(v);
    if(a>=100) return ''+Math.round(v); if(a>=10) return ''+(Math.round(v*10)/10);
    if(a>=1) return ''+(Math.round(v*100)/100); return ''+(+v.toPrecision(3)); };
  const spark = (key, vals, dashV) => {
    const el=$('mp-'+key); if(!el) return;
    if(!vals || vals.length<2){ el.setAttribute('points',''); return; }
    const w=210,h=46; const vmax=Math.max.apply(null, (dashV!=null)?vals.concat([dashV]):vals);
    const vmin=Math.min.apply(null, vals); const rng=(vmax-vmin)||1;
    const pts=vals.map((v,i)=>{ const x=i/(vals.length-1)*w; const y=h-3-(v-vmin)/rng*(h-6);
      return x.toFixed(1)+','+y.toFixed(1); }).join(' ');
    el.setAttribute('points', pts);
    const dl=$('md-'+key);
    if(dl && dashV){ const dy=h-3-(dashV-vmin)/rng*(h-6);
      dl.setAttribute('y1',dy.toFixed(1)); dl.setAttribute('y2',dy.toFixed(1)); dl.setAttribute('opacity','0.55'); }
  };
  const updStatus = (s) => {
    (s.models||[]).forEach(md=>{
      const dot=$('st-dot-'+md.key);
      if(dot){ dot.style.background=md.color; dot.className = md.pulse?'led-pulse':''; }
      const inf=$('st-info-'+md.key);
      if(inf){ if(inf.textContent!==md.info) inf.textContent=md.info; inf.style.color = md.err?'#ef4444':'#888'; }
    });
  };
  const tick = () => {
    const inp=document.querySelector('#model-dd input'); const model=inp?inp.value:'';
    fetch('/status_data').then(r=>r.json()).then(updStatus).catch(()=>{});   // 모델 상태 LED 제자리 갱신
    fetch('/dash_metrics?model='+encodeURIComponent(model)).then(r=>r.json()).then(d=>{
      setT('mv-tps', fmt(d.tps)); setT('mv-tpot', fmt(d.tpot));
      setT('mv-e2e', fmt(d.e2e/1000)); setT('mv-ttft', fmt(d.ttft));
      setT('mv-power', fmt(d.power)); setT('mv-temp', fmt(d.temp)); setT('mv-util', fmt(d.util));
      spark('tps', d.tps_hist, d.max_tps||null); spark('tpot', d.tpot_hist, null); spark('power', d.power_hist, null);
      for(let i=0;i<4;i++){ const row=$('mem-row-'+i); if(!row) continue;
        const m=(d.mem||[]).find(x=>x[0]===i);
        if(!m){ row.style.display='none'; continue; }
        row.style.display='flex'; const used=m[1], total=m[2], pct=m[3];
        const bar=$('mem-bar-'+i); if(bar){ bar.style.width=Math.max(0,Math.min(100,pct))+'%';
          bar.style.background = (pct>=90)?'#dc2626':'#76d6ff'; }
        setT('mem-used-'+i, used.toFixed(1)+'/'+total.toFixed(1)); setT('mem-pct-'+i, Math.round(pct)+'%');
      }
      setTimeout(tick, d.active?800:4000);
    }).catch(()=>setTimeout(tick, 4000));
  };
  window.__dashTick = tick;   // 새로고침 버튼이 즉시 1회 갱신할 수 있게 노출
  // 답변마다 모델명을 그 답변의 복사/재생성 버튼(.message-buttons-left) 아래에 작게 붙인다.
  // - 메시지 전체가 단일 .message-wrap 이라, '마커[i] ↔ message-buttons-left[i]' 순서(둘 다 봇답변에만
  //   생기고 DOM 순서 동일)로 매칭해 '모든' 답변에 붙인다(모델 바꿔 새 답변 와도 표기됨).
  // - 라벨은 버튼박스 '밖'(다음 형제)에 둬 박스를 아이콘 크기 그대로 유지(가로로 안 늘어남).
  const placeModels = () => {
    const metas = document.querySelectorAll('#chatbot .ans-model-meta');
    const boxes = document.querySelectorAll('#chatbot .message-buttons-left');
    const n = Math.min(metas.length, boxes.length);
    for (let i = 0; i < n; i++) {
      const box = boxes[i];
      const nx = box.nextElementSibling;
      if (nx && nx.classList && nx.classList.contains('ans-model-label')) continue;  // 이미 붙음
      const lab = document.createElement('span');
      lab.className = 'ans-model-label';
      lab.textContent = metas[i].textContent;
      lab.style.cssText = 'display:block;color:#6b6b73;font-size:11px;margin:2px 0 0 4px;white-space:nowrap;';
      box.insertAdjacentElement('afterend', lab);
    }
  };
  const cbEl = document.querySelector('#chatbot');
  if (cbEl) new MutationObserver(() => placeModels()).observe(cbEl, { childList: true, subtree: true });
  placeModels();
  tick();
}
"""


def dash_tick(model_name):
    """대시보드 타이머 tick: 선택 모델 카드의 HW 표본 갱신 + furiosa 스타일 HTML 렌더.
    생성 중(+여유 5초)이거나 모델 전환 중이면 계속 갱신(메모리 라이브), 둘 다 멎으면 스스로 끈다.
    출력 2개: (dash, dash_timer)."""
    METRICS.sample(_active_cards(model_name))
    h = METRICS.render_html()
    html_out = gr.skip() if h == _LAST_DASH["html"] else h
    _LAST_DASH["html"] = h
    busy = (time.time() - METRICS.last_activity) <= DASH_IDLE_OFF or _transitioning()
    timer_out = gr.skip() if busy else gr.Timer(active=False)
    return html_out, timer_out


def start_dash():
    """생성 시작 시 호출: 활동 표시 + 대시보드 타이머 켬(생성 중 라이브 갱신)."""
    METRICS.touch()
    return gr.Timer(active=True)


def dash_initial():
    """페이지 로드 시 한 번만 HW 표본을 떠서(카드별 메모리 등) 바로 보이게 한 뒤 렌더.
    이후 갱신은 생성 중 dash_timer 가 담당(유휴 spawn 없음)."""
    try:
        METRICS.sample(None)   # active_cards=None → 모든 NPU(메모리는 전체 카드 표시)
    except Exception:
        pass
    return METRICS.render_html()


# ── RAG 컨트롤 핸들러 ────────────────────────────────────────────────
def _rag_info_html(extra=""):
    nd, nc, names = RAG.summary()
    backend = "임베딩 서버" if RAG.backend == "embedding" else "TF-IDF(로컬)"
    head = (f'📚 <b>{nd}</b>개 문서 · <b>{nc}</b>개 청크 · 검색: {backend}'
            if nd else f'문서 없음 · 검색: {backend}')
    lst = "".join(f'<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">• {n}</div>'
                  for n in names[:8])
    more = f'<div>… 외 {nd - 8}개</div>' if nd > 8 else ""
    err = f'<div style="color:#dc2626;">{extra}</div>' if extra else ""
    return f'<div id="rag-info">{head}{err}<div style="margin-top:4px;">{lst}{more}</div></div>'


def rag_add_files(files):
    """업로드 파일들을 인덱싱. 출력 2개: (rag_info, file_clear)."""
    errs = []
    for f in files or []:
        path = f if isinstance(f, str) else getattr(f, "name", None)
        if not path:
            continue
        try:
            RAG.add_file(path)
        except Exception as e:
            errs.append(f"{Path(path).name}: {e}")
    return _rag_info_html("; ".join(errs)), None


def rag_add_url_fn(url):
    try:
        n = RAG.add_url(url)
        return _rag_info_html(f"" if n else "내용이 비어 추가 안 됨"), ""
    except Exception as e:
        return _rag_info_html(f"URL 실패: {e}"), url


def rag_add_text_fn(text):
    if text and text.strip():
        name = "붙여넣기 " + dt.datetime.now().strftime("%H:%M:%S")
        RAG.add(name, text)
        return _rag_info_html(), ""
    return _rag_info_html(), text


def rag_clear_fn():
    RAG.clear()
    return _rag_info_html()


def _header_html():
    img = f'<img src="{LOGO_URI}" alt="furiosa"/>' if LOGO_URI else "🔴 "
    return (f'<div id="brand">{img}'
            f'<span class="ttl">Furiosa RNGD Chat</span>'
            f'<span class="demo">DEMO</span></div>')


def build_ui():
    # 첫 시작 모델 = 지금 NPU 에 떠 있는 모델(없으면 DEFAULT_MODEL). 드롭다운·max_tokens 도 그 모델로.
    _init_model = _initial_model()
    _ctx0 = CATALOG[DISPLAY2KEY[_init_model]]["ctx"]
    with gr.Blocks(title="Furiosa RNGD Chat", fill_height=True, css=CSS, theme=THEME) as demo:
        conv_id = gr.State("")
        # ── furiosa 헤더: 로고 + Furiosa RNGD Chat + DEMO | 모델 드롭다운 ──
        with gr.Row(elem_id="furheader", equal_height=True):
            with gr.Column(scale=1, min_width=200):
                gr.HTML(_header_html())
            model_dd = gr.Dropdown(_dd_choices(), value=_init_model, show_label=False,
                                   container=False, elem_id="model-dd", scale=0, min_width=340)
        with gr.Row(equal_height=False):
            # ── 사이드바: 대화 이력 + 모델 상태(LED) + 설정(dp/pp) + RAG ──
            with gr.Column(scale=1, min_width=240, elem_id="sidebar"):
                new_btn = gr.Button("✏️  새 채팅", elem_id="newchat-btn")
                search = gr.Textbox(placeholder="🔍  검색", show_label=False, elem_id="search-box",
                                    lines=1, container=False)
                gr.Markdown("최근", elem_id="recent-label")
                convo_radio = gr.Radio(choices=_convo_choices(), show_label=False, value=None,
                                       elem_id="convo-list", container=False)
                del_btn = gr.Button("🗑  선택한 대화 삭제", size="sm", elem_id="del-btn")
                with gr.Accordion("모델 상태", open=True):
                    status = gr.HTML(value=status_struct(), elem_id="statusbox")
                    with gr.Row():
                        refresh_btn = gr.Button("🔄 새로고침", size="sm")
                        stopall_btn = gr.Button("🛑 전부 내리기", size="sm", elem_id="stopall-btn")
                with gr.Accordion("⚙  설정 (dp·pp·생성)", open=False, elem_id="settings-acc"):
                    with gr.Row():
                        dp = gr.Dropdown([1, 2, 3, 4], value=1, label="복제 dp", scale=1,
                                         info="카드마다 복제 — 동시 요청↑. tp8만")
                        pp = gr.Dropdown([1, 2, 3, 4], value=1, label="레이어 분할 pp", scale=1,
                                         info="여러 장에 레이어 분산. dp×pp≤4. tp8만")
                    temp = gr.Slider(0.0, 2.0, value=0.7, step=0.1, label="temperature")
                    maxtok = gr.Slider(64, _ctx0, value=_ctx0, step=256, label="max_tokens (답변 최대 길이)",
                                       info="모델 선택 시 그 모델 최대치로 자동 설정. 생성 시 컨텍스트에 맞게 자동 조정됨")
                    sys_box = gr.Textbox(label="시스템 프롬프트", lines=1,
                                         placeholder="예: 너는 한국어로 답하는 코딩 도우미야.")
                with gr.Accordion("📎 문서 검색 (RAG)", open=False, elem_id="rag-acc"):
                    rag_on = gr.Checkbox(value=False, label="RAG 사용 (올린 문서에서 근거 검색)")
                    rag_files = gr.File(label="문서 업로드 (.txt·.md·코드·.pdf)", file_count="multiple",
                                        elem_id="rag-files", height=90)
                    with gr.Row():
                        rag_url = gr.Textbox(placeholder="https:// URL", show_label=False, scale=3, lines=1)
                        rag_url_btn = gr.Button("URL", size="sm", scale=1)
                    with gr.Row():
                        rag_paste = gr.Textbox(placeholder="텍스트 붙여넣기", show_label=False, scale=3, lines=1)
                        rag_paste_btn = gr.Button("추가", size="sm", scale=1)
                    rag_k = gr.Slider(1, 8, value=4, step=1, label="참조 청크 수 (top-k)")
                    rag_info = gr.HTML(value=_rag_info_html())
                    rag_clear = gr.Button("🗑 문서 비우기", size="sm")
                gr.HTML('<div id="userchip">RNGD NPU · furiosa-llm</div>')
            # ── 채팅 ──
            with gr.Column(scale=3, elem_id="main"):
                chatbot = gr.Chatbot(type="messages", elem_id="chatbot", height="74vh",
                                     show_label=False, show_copy_button=True,
                                     allow_tags=True)  # True 라야 <details> 사고과정이 렌더됨
                with gr.Column(elem_id="inputwrap"):
                    with gr.Row(elem_id="inputbar"):
                        txt = gr.Textbox(placeholder="무엇이든 부탁하세요", show_label=False, scale=9,
                                         lines=1, container=False, autofocus=True)
                        send = gr.Button("↑", elem_id="send-btn", scale=0)
                        stop = gr.Button("■", elem_id="stop-btn", scale=0, visible=False)
                    gr.HTML('<div id="hint">RNGD NPU 위 furiosa-llm · 답변은 모델에 따라 부정확할 수 있어요.</div>')
            # ── 우측 실시간 성능 대시보드 (furiosa chat-playground 이식) ──
            # 정적 구조만 1회 렌더하고, 값은 클라이언트 JS(POLL_JS)가 /dash_metrics 폴링해 제자리 갱신.
            # → 패널을 통째로 안 바꾸므로 깜빡임 없이 매끄럽게 변하고, 변한 칸만 실제로 바뀐다.
            with gr.Column(scale=1, min_width=240, elem_id="dashboard"):
                dash = gr.HTML(value=METRICS.render_dashboard(), elem_id="dashbox")

        SP = "hidden"  # 도는 네모(progress 스피너) 끔 → LED 펄스만, 스트리밍/질문 즉시 노출
        # 모델 상태 LED 도 대시보드처럼 클라이언트 폴링(/status_data)으로 제자리 갱신 → 패널 전체
        # 깜빡임 없이 바뀐 LED 만 바뀐다(전환 펄스는 CSS). 별도 Timer/재렌더 불필요.
        IPOLL = "() => window.__dashTick && window.__dashTick()"   # 즉시 1회 폴링(버튼용)
        chat_inputs = [txt, chatbot, conv_id, model_dd, dp, pp, rag_on, rag_k, sys_box, temp, maxtok]
        chat_outputs = [chatbot, conv_id, txt, convo_radio, status, send, stop]
        regen_inputs = [chatbot, conv_id, model_dd, dp, pp, rag_on, rag_k, sys_box, temp, maxtok]
        ev1 = txt.submit(respond, chat_inputs, chat_outputs, show_progress=SP)
        ev2 = send.click(respond, chat_inputs, chat_outputs, show_progress=SP)
        ev3 = chatbot.retry(regenerate, regen_inputs, chat_outputs, show_progress=SP)
        stop.click(lambda: _IDLE, None, [send, stop], cancels=[ev1, ev2, ev3], show_progress=SP)
        new_btn.click(new_chat, None, [chatbot, conv_id, convo_radio, txt], show_progress=SP)
        del_btn.click(delete_convo, [convo_radio, conv_id], [chatbot, conv_id, convo_radio], show_progress=SP)
        refresh_btn.click(None, None, None, js=IPOLL, show_progress=SP)   # 즉시 폴링(LED 새로고침)
        # '전부 내리기': 떠 있는 serve 전부 종료(카드 비움). LED 갱신은 폴링이 반영.
        stopall_btn.click(stop_all_models, None, None, show_progress=SP)
        search.change(filter_convos, [search], [convo_radio], show_progress=SP)
        convo_radio.change(load_chat, [convo_radio], [chatbot, conv_id], show_progress=SP)
        model_dd.change(on_model_change, [model_dd, dp, pp], [maxtok, dp, pp], show_progress=SP)
        dp.change(on_par_change, [model_dd, dp, pp], [dp, pp], show_progress=SP)
        pp.change(on_par_change, [model_dd, dp, pp], [dp, pp], show_progress=SP)
        # RAG: 업로드/URL/붙여넣기/비우기 → 문서 인덱싱 + 정보 패널 갱신
        rag_files.upload(rag_add_files, [rag_files], [rag_info, rag_files], show_progress=SP)
        rag_url_btn.click(rag_add_url_fn, [rag_url], [rag_info, rag_url], show_progress=SP)
        rag_paste_btn.click(rag_add_text_fn, [rag_paste], [rag_info, rag_paste], show_progress=SP)
        rag_clear.click(rag_clear_fn, None, [rag_info], show_progress=SP)
        # 크롬 새로고침: 마지막에 고른 모델 복원(default 로 안 돌아가게). 상태·대시보드는 폴링이 채움.
        demo.load(restore_model, None, [model_dd, maxtok, dp, pp], show_progress=SP)
        # 대시보드: 값은 클라이언트 JS 가 /dash_metrics 폴링해 제자리 갱신(깜빡임 없음·변한 칸만).
        demo.load(None, None, None, js=POLL_JS)
    return demo


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI

    host = os.environ.get("CHAT_HOST", "0.0.0.0")
    port = int(os.environ.get("CHAT_PORT", "7870"))
    root_path = os.environ.get("CHAT_ROOT_PATH", "")
    _auth = os.environ.get("CHAT_AUTH", "")
    auth = tuple(_auth.split(":", 1)) if ":" in _auth else None

    # default_concurrency_limit>1: 스트리밍 생성과 다른 이벤트(상태 타이머 등)가 동시에 돌도록.
    demo = build_ui().queue(default_concurrency_limit=12)

    # FastAPI 에 대시보드 폴링 라우트를 붙이고 그 위에 gradio 를 마운트한다.
    # 클라이언트 JS(POLL_JS)가 이 JSON 을 받아 칸 값만 제자리 갱신 → 패널 무깜빡임.
    app = FastAPI()

    @app.get("/dash_metrics")
    def _dash_metrics(model: str = ""):
        return dash_metrics_data(model)

    @app.get("/status_data")
    def _status_data():
        return status_data()

    app = gr.mount_gradio_app(app, demo, path="/", root_path=root_path, auth=auth)
    uvicorn.run(app, host=host, port=port)
