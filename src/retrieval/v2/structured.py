"""Template-only structured fact retrieval with mandatory tenant/warehouse filters."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from src.api.domain.identity import IdentityContext

from .contracts import QueryEnvelope, RetrievalCandidate


class StructuredFactRetriever:
    def __init__(
        self, templates: dict[str, Callable[..., Any]], *, max_rows: int = 100
    ) -> None:
        self.templates = templates
        self.max_rows = max_rows

    async def retrieve(
        self,
        template_id: str,
        query: QueryEnvelope,
        identity: IdentityContext,
        *,
        limit: int = 50,
    ) -> list[RetrievalCandidate]:
        template = self.templates.get(template_id)
        if template is None:
            raise LookupError(
                f"structured query template is not registered: {template_id}"
            )
        safe_limit = min(max(1, limit), self.max_rows)
        parameters = {
            "tenant_id": identity.tenant_id,
            "warehouse_ids": identity.warehouse_scope,
            "entities": tuple(item.model_dump(mode="json") for item in query.entities),
            "time_range": (
                query.time_range.model_dump(mode="json") if query.time_range else None
            ),
            "limit": safe_limit,
        }
        rows = template(parameters)
        if inspect.isawaitable(rows):
            rows = await rows
        observed_at = datetime.now(UTC)
        results = []
        for rank, row in enumerate(list(rows)[:safe_limit], start=1):
            canonical = repr(sorted(row.items()))
            candidate_id = (
                "row-"
                + sha256(f"{template_id}:{canonical}".encode("utf-8")).hexdigest()[:24]
            )
            results.append(
                RetrievalCandidate(
                    candidate_id=candidate_id,
                    content=str(row),
                    source_type="structured_record",
                    source_locator={
                        "query_template_id": template_id,
                        "row": rank,
                        "observed_at": observed_at.isoformat(),
                    },
                    channel="structured",
                    rank=rank,
                    raw_score=1.0,
                    tenant_id=identity.tenant_id,
                    warehouse_ids=identity.warehouse_scope,
                    token_count=max(1, len(str(row)) // 3),
                    metadata={
                        "record": row,
                        "source_version": row.get("source_version"),
                    },
                )
            )
        return results
