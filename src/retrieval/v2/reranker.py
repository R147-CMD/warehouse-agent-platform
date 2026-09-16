"""Optional Cross-Encoder reranking with a deterministic fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from .contracts import FusedCandidate, RetrievalCandidate

ScoreProvider = Callable[[str, Sequence[str]], Awaitable[Sequence[float]]]


class CrossEncoderReranker:
    def __init__(
        self,
        score_provider: ScoreProvider | None = None,
        *,
        timeout_seconds: float = 2.0,
        top_n: int = 30,
    ) -> None:
        self.score_provider = score_provider
        self.timeout_seconds = timeout_seconds
        self.top_n = top_n

    async def rerank(
        self, query: str, fused: Sequence[FusedCandidate]
    ) -> tuple[list[RetrievalCandidate], bool]:
        limited = list(fused[: self.top_n])
        fallback = [item.candidate for item in limited]
        if not self.score_provider or not limited:
            return fallback, False
        try:
            scores = await asyncio.wait_for(
                self.score_provider(
                    query, [item.candidate.content for item in limited]
                ),
                timeout=self.timeout_seconds,
            )
            if len(scores) != len(limited):
                raise ValueError("reranker returned a different number of scores")
            ranked = sorted(
                zip(limited, scores, strict=True),
                key=lambda item: (-float(item[1]), item[0].candidate.candidate_id),
            )
            return [item.candidate for item, _ in ranked], False
        except (TimeoutError, ValueError, TypeError):
            return fallback, True
