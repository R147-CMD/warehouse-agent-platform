"""Deterministic rank fusion independent of backend score scales."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from .contracts import FusedCandidate, RetrievalCandidate, RetrievalChannel


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[RetrievalCandidate]], *, k: int = 60
) -> list[FusedCandidate]:
    if k < 1:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = defaultdict(float)
    candidates: dict[str, RetrievalCandidate] = {}
    channels: dict[str, set[RetrievalChannel]] = defaultdict(set)
    for ranking in rankings:
        for position, candidate in enumerate(ranking, start=1):
            rank = candidate.rank if candidate.rank >= 1 else position
            scores[candidate.candidate_id] += 1.0 / (k + rank)
            candidates.setdefault(candidate.candidate_id, candidate)
            channels[candidate.candidate_id].add(candidate.channel)
    ordered_ids = sorted(scores, key=lambda key: (-scores[key], key))
    return [
        FusedCandidate(
            candidate=candidates[candidate_id],
            fused_score=scores[candidate_id],
            channels=tuple(sorted(channels[candidate_id])),
        )
        for candidate_id in ordered_ids
    ]
