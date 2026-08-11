# SPDX-License-Identifier: Apache-2.0
# Qwen3-Coder tool-call parser for furiosa-llm.
#
# furiosa-llm 2026.2.0 기본 tool 파서{hermes, llama3_json/4, openai}는 Qwen3-Coder 의
# tool call 을 못 읽는다. Qwen3-Coder 의 chat template 은 모델에게 다음 XML 형식을 지시한다:
#   <tool_call>
#   <function=FUNC>
#   <parameter=KEY>
#   VALUE
#   </parameter>
#   </function>
#   </tool_call>
# 그러나 실측상 a3b(FP8) 모델은 이 지시를 항상 따르지 않고, <tool_call> 안에 OpenAI 식
# JSON 배열([{"function":{"name":..,"arguments":".."}}])을 내거나 닫는 태그를 </tool_call>
# 대신 <tool_call> 로 잘못 내기도 한다. 그래서 이 파서는 **두 형식 모두** 관대하게 파싱한다.
#   1) XML  : <function=NAME> + <parameter=KEY>VALUE</parameter>
#   2) JSON : <tool_call> 뒤의 [ { ... } ] / { ... } (OpenAI tool_calls 형태)
# 출력은 OpenAI 표준 tool_calls(name + arguments(JSON 문자열)). 인자 타입은 tool 스키마로 보정.
#
# 등록명: "qwen3_coder"  →  furiosa-llm serve --tool-call-parser qwen3_coder
# (스트리밍은 XML 의 emit-on-complete 만 best-effort. JSON 형식까지 안전히 다루려면
#  router 가 qwen3_coder 모델을 비스트리밍으로 호출해 SSE 로 변환한다 — furiosa_router.py)
import json
import logging
import re
from typing import Sequence, Union

from furiosa_llm.server.protocol import (
    ChatCompletionRequest,
    DeltaFunctionCall,
    DeltaMessage,
    DeltaToolCall,
    ExtractedToolCallInformation,
    FunctionCall,
    ToolCall,
)
from furiosa_llm.server.tool_parsers.abstract_tool_parser import ToolParser, ToolParserManager
from furiosa_llm.server.utils import random_tool_call_id
from furiosa_llm.vllm_compat import AnyTokenizer

logger = logging.getLogger(__name__)


@ToolParserManager.register_module("qwen3_coder")
class Qwen3CoderToolParser(ToolParser):
    def __init__(self, tokenizer: AnyTokenizer):
        super().__init__(tokenizer)
        self.tool_call_start = "<tool_call>"
        self.tool_call_end = "</tool_call>"
        # 함수명: 닫는 기호를 관대하게(>, }, 공백, 줄바꿈 어느 것이든 종료). 모델이
        # <function=write_file> / <function=write_file} 등 깨진 형태로도 내기 때문.
        self._func_re = re.compile(r"<function=([^>}\n\s]+)")
        self._param_re = re.compile(r"<parameter=([^>\n]+)>\n?(.*?)\n?</parameter>", re.DOTALL)
        # streaming state
        self._names_sent: set = set()
        self._args_sent: set = set()
        self._content_done = False

    # ── 스키마 기반 값 타입 보정 ──────────────────────────────────────────
    def _properties(self, request, name):
        for t in (getattr(request, "tools", None) or []):
            fn = getattr(t, "function", None)
            if fn is not None and getattr(fn, "name", None) == name:
                params = getattr(fn, "parameters", None) or {}
                if isinstance(params, dict):
                    return params.get("properties") or {}
        return {}

    def _coerce(self, raw, schema):
        t = (schema or {}).get("type")
        try:
            if t == "integer":
                return int(str(raw).strip())
            if t == "number":
                return float(str(raw).strip())
            if t == "boolean":
                return str(raw).strip().lower() in ("true", "1", "yes")
            if t in ("object", "array"):
                return json.loads(raw)
        except Exception:
            return raw
        return raw

    def _mk(self, name, args):
        arguments = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
        return ToolCall(type="function", function=FunctionCall(name=name, arguments=arguments))

    # ── 첫 JSON 값(배열/객체) raw_decode ─────────────────────────────────
    def _first_json(self, s):
        for i, ch in enumerate(s):
            if ch in "[{":
                try:
                    obj, _ = json.JSONDecoder().raw_decode(s[i:])
                    return obj
                except Exception:
                    continue
        return None

    # ── name/function 키를 가진 JSON → ToolCall 들 ────────────────────────
    # 모델이 함수/이름/인자 키를 제멋대로 쓴다(실측): function|tool_call 래퍼,
    # name|tool_name, arguments|parameters|args. 모두 관대하게 처리.
    def _obj_to_calls(self, obj):
        out = []
        for it in (obj if isinstance(obj, list) else [obj]):
            if not isinstance(it, dict):
                continue
            node = it
            for wrap in ("function", "tool_call", "tool"):
                if isinstance(it.get(wrap), dict):
                    node = it[wrap]
                    break
            name = (node.get("name") or node.get("tool_name")
                    or it.get("name") or it.get("tool_name"))
            if not name:
                continue
            args = node.get("arguments", node.get("parameters", node.get("args", {})))
            out.append(self._mk(name, args))
        return out

    # ── 견고 추출: 모델이 호출마다 형식이 달라도(XML / 깨진 태그+JSON / JSON배열) 모두 처리 ──
    def _extract_calls(self, text, request):
        # 보통은 <tool_call> 뒤에 호출이 오지만, 긴 컨텍스트에서는 **JSON 을 먼저 내고 <tool_call>
        # 을 꼬리로 붙이는** 출력이 나온다(2026-08-07 실측, tp32 공식 코더 17.8k 프롬프트):
        #   I'll read that for you.\n\n[{"function":{"name":"read_file",...}}]\n<tool_call>
        # 이때 마커 뒤만 보면 빈 문자열이라 멀쩡한 호출을 통째로 버리게 된다.
        # 그래서 마커 뒤를 먼저 보고, 못 찾으면 전체 텍스트로 한 번 더 시도한다.
        if self.tool_call_start in text:
            calls = self._extract_from(text[text.find(self.tool_call_start):], request)
            if calls:
                return calls
        return self._extract_from(text, request)

    def _extract_from(self, region, request):
        fmarks = list(self._func_re.finditer(region))
        if fmarks:
            # 형식 A: <function=NAME> 마커 (뒤에 <parameter> 또는 bare JSON 인자)
            calls = []
            for j, fm in enumerate(fmarks):
                name = fm.group(1).strip()
                end = fmarks[j + 1].start() if j + 1 < len(fmarks) else len(region)
                seg = region[fm.end():end]
                props = self._properties(request, name)
                args = {}
                for pm in self._param_re.finditer(seg):
                    k = pm.group(1).strip()
                    args[k] = self._coerce(pm.group(2), props.get(k))
                if not args:
                    jd = self._first_json(seg)
                    if isinstance(jd, dict):
                        args = jd["arguments"] if (
                            "arguments" in jd and isinstance(jd["arguments"], (dict, str))
                        ) else jd
                calls.append(self._mk(name, args))
            return calls
        # 형식 B: 함수태그 없이 JSON (배열/객체에 name 포함)
        jd = self._first_json(region)
        return self._obj_to_calls(jd) if jd is not None else []

    def _call_start(self, text):
        """도구 호출이 시작되는 위치. 사람용 content 를 여기서 잘라 낸다."""
        idxs = [i for i in (text.find(self.tool_call_start),
                            text.find("<function="),
                            text.find("[{"),
                            text.find('{"')) if i >= 0]
        return min(idxs) if idxs else len(text)

    # ── 비스트리밍 ────────────────────────────────────────────────────────
    def extract_tool_calls(self, model_output, request):
        # <tool_call> 마커가 아예 없이 OpenAI 식 JSON 만 내는 출력도 있으므로, 호출처럼 보이면
        # 마커가 없어도 시도한다. 평범한 산문을 오탐하지 않도록 name+arguments 형태일 때만.
        looks_like_json_call = ('"name"' in model_output
                                and ('"arguments"' in model_output or '"parameters"' in model_output))
        if self.tool_call_start not in model_output and not looks_like_json_call:
            return ExtractedToolCallInformation(tools_called=False, tool_calls=[], content=model_output)
        try:
            calls = self._extract_calls(model_output, request)
            if not calls:
                return ExtractedToolCallInformation(tools_called=False, tool_calls=[], content=model_output)
            content = model_output[:self._call_start(model_output)]
            return ExtractedToolCallInformation(
                tools_called=True, tool_calls=calls, content=content if content else None
            )
        except Exception:
            logger.exception("qwen3_coder extract_tool_calls failed")
            return ExtractedToolCallInformation(tools_called=False, tool_calls=[], content=model_output)

    # ── 스트리밍 (XML emit-on-complete best-effort) ───────────────────────
    def extract_tool_calls_streaming(
        self, previous_text, current_text, delta_text,
        previous_token_ids, current_token_ids, delta_token_ids, request,
    ):
        if self.tool_call_start not in current_text:
            return DeltaMessage(content=delta_text) if delta_text else None
        if not self._content_done:
            self._content_done = True
            head = current_text.split(self.tool_call_start)[0]
            if len(head) > len(previous_text):
                lead = head[len(previous_text):]
                if lead:
                    return DeltaMessage(content=lead)
        try:
            segs = current_text.split(self.tool_call_start)[1:]
            for idx, seg in enumerate(segs):
                closed = self.tool_call_end in seg
                body = seg.split(self.tool_call_end)[0] if closed else seg
                while len(self.prev_tool_call_arr) <= idx:
                    self.prev_tool_call_arr.append({})
                while len(self.streamed_args_for_tool) <= idx:
                    self.streamed_args_for_tool.append("")
                if idx not in self._names_sent:
                    fm = re.search(r"<function=([^>\n]+)>", body)
                    if not fm:
                        return None
                    name = fm.group(1).strip()
                    self._names_sent.add(idx)
                    self.current_tool_id = idx
                    self.prev_tool_call_arr[idx] = {"name": name, "arguments": {}}
                    return DeltaMessage(tool_calls=[DeltaToolCall(
                        index=idx, type="function", id=random_tool_call_id(),
                        function=DeltaFunctionCall(name=name))])
                if closed and idx not in self._args_sent:
                    calls = self._extract_calls(self.tool_call_start + body, request)
                    args_str = calls[0].function.arguments if calls else "{}"
                    self.prev_tool_call_arr[idx] = {
                        "name": self.prev_tool_call_arr[idx].get("name"),
                        "arguments": json.loads(args_str) if args_str else {},
                    }
                    self.streamed_args_for_tool[idx] = args_str
                    self._args_sent.add(idx)
                    self.current_tool_id = idx
                    return DeltaMessage(tool_calls=[DeltaToolCall(
                        index=idx, function=DeltaFunctionCall(arguments=args_str))])
            return None
        except Exception:
            logger.exception("qwen3_coder streaming failed")
            return None
