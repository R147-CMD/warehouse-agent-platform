"""Token-budgeted context selection and deterministic deduplication."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from .contracts import ContextBundle, RetrievalCandidate


class ContextBuilder:
    def __init__(self, *, max_tokens: int = 4_000, per_source_limit: int = 5) -> None:
        if max_tokens < 1 or per_source_limit < 1:
            raise ValueError("context budgets must be positive")
        self.max_tokens = max_tokens
        self.per_source_limit = per_source_limit

    def build(self, candidates: Iterable[RetrievalCandidate]) -> ContextBundle:
        selected: list[RetrievalCandidate] = []
        content_hashes: set[str] = set()
        source_counts: dict[str, int] = {}
        used_tokens = 0
        truncated = False
        for candidate in candidates:
            content_hash = sha256(candidate.content.strip().encode("utf-8")).hexdigest()
            if content_hash in content_hashes:
                continue
            source_key = str(
                candidate.source_locator.get("document_id")
                or candidate.source_locator.get("table")
                or candidate.source_type
            )
            if source_counts.get(source_key, 0) >= self.per_source_limit:
                truncated = True
                continue
            if used_tokens + candidate.token_count > self.max_tokens:
                truncated = True
                continue
            selected.append(candidate)
            content_hashes.add(content_hash)
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
            used_tokens += candidate.token_count
        return ContextBundle(
            items=tuple(selected),
            used_tokens=used_tokens,
            max_tokens=self.max_tokens,
            truncated=truncated,
        )
