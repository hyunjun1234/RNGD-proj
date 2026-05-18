"""토큰 생성 속도 측정.

각 요청마다 TTFT(time to first token), ITL(inter-token latency), 총 처리 시간을 stream으로 측정.
batch_size별로 동시 요청을 보내서 throughput도 계산.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx


@dataclass
class RequestMetric:
    ttft_s: float
    total_s: float
    output_tokens: int
    itl_s_list: list[float] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def itl_p50(self) -> float:
        return statistics.median(self.itl_s_list) if self.itl_s_list else float("nan")

    @property
    def output_tps(self) -> float:
        body = max(self.total_s - self.ttft_s, 1e-9)
        return self.output_tokens / body if self.output_tokens > 0 else 0.0


@dataclass
class BatchResult:
    model: str
    concurrency: int
    prompt_tokens_target: int
    max_tokens: int
    wall_clock_s: float
    successes: int
    failures: int
    metrics: list[RequestMetric]

    def summary(self) -> dict:
        ok = [m for m in self.metrics if m.error is None and m.output_tokens > 0]
        if not ok:
            return {
                "model": self.model,
                "concurrency": self.concurrency,
                "prompt_tokens_target": self.prompt_tokens_target,
                "max_tokens": self.max_tokens,
                "successes": self.successes,
                "failures": self.failures,
                "wall_clock_s": self.wall_clock_s,
                "error": "no successful requests",
            }
        ttfts = [m.ttft_s for m in ok]
        itls = [m.itl_p50 for m in ok]
        otps = [m.output_tps for m in ok]
        total_out_tokens = sum(m.output_tokens for m in ok)
        agg_throughput = total_out_tokens / self.wall_clock_s if self.wall_clock_s > 0 else 0.0
        return {
            "model": self.model,
            "concurrency": self.concurrency,
            "prompt_tokens_target": self.prompt_tokens_target,
            "max_tokens": self.max_tokens,
            "successes": self.successes,
            "failures": self.failures,
            "wall_clock_s": round(self.wall_clock_s, 3),
            "ttft_s_p50": round(statistics.median(ttfts), 4),
            "ttft_s_p95": round(_p95(ttfts), 4),
            "itl_s_p50": round(statistics.median(itls), 5),
            "itl_s_p95": round(_p95(itls), 5),
            "output_tps_per_request_p50": round(statistics.median(otps), 2),
            "aggregate_output_tps": round(agg_throughput, 2),
            "total_output_tokens": total_out_tokens,
        }


def _p95(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = max(0, int(round(0.95 * (len(s) - 1))))
    return s[k]


_PROMPT_FILLER = (
    "Refactor the following code to be more efficient and readable. "
    "Explain your reasoning step by step. "
)


def _make_prompt(target_tokens: int) -> str:
    # 1 word ≈ 1.3 tokens 가정으로 대략 채움. 정확한 토큰 수는 서버가 토크나이즈하면서 결정.
    body = (_PROMPT_FILLER * (target_tokens // 8 + 1))[: target_tokens * 5]
    return f"You are a senior engineer.\n\n{body}\n\nWrite a Python function that solves this problem."


async def _one_request(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> RequestMetric:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
    }
    start = time.perf_counter()
    ttft: Optional[float] = None
    last_token_t = start
    itls: list[float] = []
    n_out = 0
    try:
        async with client.stream("POST", f"{base_url}/chat/completions", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    now = time.perf_counter()
                    if ttft is None:
                        ttft = now - start
                    else:
                        itls.append(now - last_token_t)
                    last_token_t = now
                    n_out += 1
        total = time.perf_counter() - start
        return RequestMetric(
            ttft_s=ttft if ttft is not None else float("nan"),
            total_s=total,
            output_tokens=n_out,
            itl_s_list=itls,
        )
    except Exception as e:
        total = time.perf_counter() - start
        return RequestMetric(
            ttft_s=float("nan"),
            total_s=total,
            output_tokens=0,
            error=f"{type(e).__name__}: {e}",
        )


async def run_concurrency(
    base_url: str,
    model: str,
    concurrency: int,
    prompt_tokens_target: int,
    max_tokens: int,
    n_requests: int,
    warmup: int = 3,
    timeout_s: float = 600.0,
) -> BatchResult:
    prompt = _make_prompt(prompt_tokens_target)
    limits = httpx.Limits(max_connections=max(concurrency * 2, 16), max_keepalive_connections=concurrency * 2)
    async with httpx.AsyncClient(timeout=timeout_s, limits=limits) as client:
        # warmup
        for _ in range(warmup):
            await _one_request(client, base_url, model, prompt, max_tokens=32)

        sem = asyncio.Semaphore(concurrency)

        async def bounded():
            async with sem:
                return await _one_request(client, base_url, model, prompt, max_tokens)

        wall_start = time.perf_counter()
        results = await asyncio.gather(*[bounded() for _ in range(n_requests)])
        wall = time.perf_counter() - wall_start

    successes = sum(1 for m in results if m.error is None and m.output_tokens > 0)
    failures = len(results) - successes
    return BatchResult(
        model=model,
        concurrency=concurrency,
        prompt_tokens_target=prompt_tokens_target,
        max_tokens=max_tokens,
        wall_clock_s=wall,
        successes=successes,
        failures=failures,
        metrics=results,
    )


def to_jsonable(result: BatchResult) -> dict:
    d = asdict(result)
    d["summary"] = result.summary()
    return d
