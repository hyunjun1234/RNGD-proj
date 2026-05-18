"""Qwen3-Embedding-8B / Qwen3-Reranker-8B 측정.

Embedding: /v1/embeddings (OpenAI 호환). 단일 요청 + 배치 요청 처리량.
Reranker: 실제 엔드포인트는 furiosa-llm 버전에 따라 다를 수 있어 두 후보 시도.
  1) /v1/rerank (cohere/jina 스타일)
  2) /v1/score (chat-style score endpoint)
  실패 시 /v1/embeddings로 query/doc 임베딩 후 코사인 유사도 fallback.

코드 생성 평가의 SWE-bench 보조 (BM25 대신 semantic retrieval)에도 그대로 활용.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx


# 적당히 다양한 길이의 입력 문서 (실측은 더 큰 데이터셋으로 교체 가능)
SAMPLE_DOCS = [
    "def fibonacci(n): return n if n < 2 else fibonacci(n-1) + fibonacci(n-2)",
    "class BTreeNode: def __init__(self, leaf=False): self.keys = []",
    "import torch.nn as nn\nclass Transformer(nn.Module):\n    def __init__(self, d_model): ...",
    "// implements a thread-safe LRU cache in Go\nfunc (c *LRU) Get(k string) (any, bool) {",
    "SELECT user_id, COUNT(*) FROM events WHERE ts > NOW() - INTERVAL 7 DAY GROUP BY 1",
] * 20  # 100 docs

SAMPLE_QUERIES = [
    "binary search implementation",
    "LRU cache thread safety",
    "transformer self attention",
    "SQL window function",
    "tree traversal in order",
] * 4


@dataclass
class EmbedResult:
    model: str
    n_inputs: int
    batch_size: int
    wall_clock_s: float
    latencies_s: list[float] = field(default_factory=list)

    def summary(self) -> dict:
        if not self.latencies_s:
            return {"model": self.model, "error": "no successful requests"}
        return {
            "model": self.model,
            "n_inputs": self.n_inputs,
            "batch_size": self.batch_size,
            "wall_clock_s": round(self.wall_clock_s, 3),
            "throughput_inputs_per_s": round(self.n_inputs / self.wall_clock_s, 2)
            if self.wall_clock_s > 0 else 0.0,
            "p50_latency_s": round(statistics.median(self.latencies_s), 4),
            "p95_latency_s": round(_p95(self.latencies_s), 4),
        }


def _p95(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[max(0, int(round(0.95 * (len(s) - 1))))]


async def bench_embeddings(
    base_url: str,
    model: str,
    docs: Optional[list[str]] = None,
    batch_sizes: tuple[int, ...] = (1, 4, 16, 64),
    timeout_s: float = 120.0,
) -> list[EmbedResult]:
    docs = docs or SAMPLE_DOCS
    out: list[EmbedResult] = []
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        for bs in batch_sizes:
            chunks = [docs[i:i + bs] for i in range(0, len(docs), bs)]
            lats: list[float] = []
            wall_start = time.perf_counter()
            for ch in chunks:
                t0 = time.perf_counter()
                r = await client.post(
                    f"{base_url}/embeddings",
                    json={"model": model, "input": ch},
                )
                r.raise_for_status()
                _ = r.json()
                lats.append(time.perf_counter() - t0)
            wall = time.perf_counter() - wall_start
            out.append(EmbedResult(
                model=model, n_inputs=len(docs), batch_size=bs,
                wall_clock_s=wall, latencies_s=lats,
            ))
    return out


@dataclass
class RerankResult:
    model: str
    pairs: int
    wall_clock_s: float
    method: str
    latencies_s: list[float] = field(default_factory=list)

    def summary(self) -> dict:
        if not self.latencies_s:
            return {"model": self.model, "error": "no successful requests"}
        return {
            "model": self.model,
            "method": self.method,
            "pairs": self.pairs,
            "wall_clock_s": round(self.wall_clock_s, 3),
            "throughput_pairs_per_s": round(self.pairs / self.wall_clock_s, 2)
            if self.wall_clock_s > 0 else 0.0,
            "p50_latency_s": round(statistics.median(self.latencies_s), 4),
            "p95_latency_s": round(_p95(self.latencies_s), 4),
        }


async def _try_endpoint(client: httpx.AsyncClient, url: str, payload: dict) -> Optional[httpx.Response]:
    try:
        r = await client.post(url, json=payload)
        if r.status_code < 500:
            return r
    except Exception:
        return None
    return None


async def bench_reranker(
    base_url: str,
    model: str,
    queries: Optional[list[str]] = None,
    docs: Optional[list[str]] = None,
    timeout_s: float = 120.0,
) -> RerankResult:
    queries = queries or SAMPLE_QUERIES
    docs = docs or SAMPLE_DOCS

    method = "rerank"
    pairs = 0
    lats: list[float] = []
    wall_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        # 첫 호출로 엔드포인트 탐색
        probe = {"model": model, "query": queries[0], "documents": docs[:5]}
        r = await _try_endpoint(client, f"{base_url}/rerank", probe)
        if r is not None and r.status_code == 200:
            method = "rerank"
            for q in queries:
                t0 = time.perf_counter()
                r2 = await client.post(f"{base_url}/rerank",
                                       json={"model": model, "query": q, "documents": docs})
                r2.raise_for_status()
                lats.append(time.perf_counter() - t0)
                pairs += len(docs)
        else:
            # fallback: 임베딩 기반 코사인 유사도
            method = "embedding-cosine"
            import math
            for q in queries:
                t0 = time.perf_counter()
                r_q = await client.post(f"{base_url}/embeddings",
                                        json={"model": model, "input": [q]})
                r_q.raise_for_status()
                r_d = await client.post(f"{base_url}/embeddings",
                                        json={"model": model, "input": docs})
                r_d.raise_for_status()
                qv = r_q.json()["data"][0]["embedding"]
                dvs = [d["embedding"] for d in r_d.json()["data"]]

                def dot(a, b): return sum(x * y for x, y in zip(a, b))
                def norm(a): return math.sqrt(dot(a, a)) or 1e-9
                _ = sorted(((dot(qv, dv) / (norm(qv) * norm(dv)), i) for i, dv in enumerate(dvs)),
                           reverse=True)
                lats.append(time.perf_counter() - t0)
                pairs += len(docs)
    wall = time.perf_counter() - wall_start
    return RerankResult(model=model, pairs=pairs, wall_clock_s=wall, method=method, latencies_s=lats)


def to_jsonable_embed(r: EmbedResult) -> dict:
    d = asdict(r)
    d["summary"] = r.summary()
    return d


def to_jsonable_rerank(r: RerankResult) -> dict:
    d = asdict(r)
    d["summary"] = r.summary()
    return d
