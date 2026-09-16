"""Deterministic-first query understanding for warehouse requests."""

from __future__ import annotations

from datetime import datetime, timedelta
import re

from src.api.domain.agent_protocols import MissingInput
from src.api.domain.identity import IdentityContext

from .contracts import QueryEnvelope, QueryType, ResolvedEntity, TimeRange

_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:SKU|WO|WT|EQ|WH)-[A-Z0-9-]+\b",
    re.IGNORECASE,
)
_ENTITY_PREFIXES = {
    "SKU": "sku",
    "WO": "warehouse_order",
    "WT": "warehouse_task",
    "EQ": "equipment",
    "WH": "warehouse",
}
_DOCUMENT_TERMS = (
    "sop",
    "procedure",
    "manual",
    "policy",
    "guide",
    "流程",
    "制度",
    "手册",
    "文档",
    "处置规范",
)
_STRUCTURED_TERMS = (
    "query",
    "status",
    "inventory",
    "stock",
    "order",
    "task",
    "equipment",
    "查询",
    "状态",
    "库存",
    "订单",
    "任务",
    "设备",
    "故障",
)
_ACTION_TERMS = (
    "create",
    "assign",
    "confirm",
    "dispatch",
    "update",
    "rebalance",
    "创建",
    "分配",
    "确认",
    "调度",
    "更新",
    "重平衡",
)


class QueryUnderstandingService:
    """Build a governed QueryEnvelope without expanding authenticated scope."""

    def parse(
        self,
        text: str,
        identity: IdentityContext,
        now: datetime,
    ) -> QueryEnvelope:
        normalized = " ".join(text.split())
        if not normalized:
            raise ValueError("query cannot be blank")
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        protected_terms = tuple(
            dict.fromkeys(
                match.group(0).upper()
                for match in _IDENTIFIER_PATTERN.finditer(normalized)
            )
        )
        entities = tuple(self._resolve_entity(term) for term in protected_terms)
        warehouse_terms = tuple(
            entity.entity_id for entity in entities if entity.entity_type == "warehouse"
        )
        allowed_warehouses = tuple(identity.warehouse_scope)
        unauthorized_terms = tuple(
            warehouse
            for warehouse in warehouse_terms
            if allowed_warehouses and warehouse not in allowed_warehouses
        )
        query_type = self._classify(normalized)
        missing_inputs = self._missing_inputs(normalized, query_type, entities)
        time_range = self._resolve_time(normalized, now)

        return QueryEnvelope(
            original_query=text,
            normalized_query=normalized,
            query_type=query_type,
            entities=entities,
            time_range=time_range,
            keywords=self._keywords(normalized, protected_terms),
            semantic_queries=(normalized,),
            protected_terms=protected_terms,
            unauthorized_terms=unauthorized_terms,
            filters={
                "tenant_id": identity.tenant_id,
                "warehouse_ids": list(allowed_warehouses),
            },
            freshness_requirement=self._freshness(query_type, normalized),
            missing_inputs=missing_inputs,
        )

    @staticmethod
    def _resolve_entity(term: str) -> ResolvedEntity:
        prefix = term.split("-", 1)[0].upper()
        return ResolvedEntity(
            entity_type=_ENTITY_PREFIXES[prefix],
            entity_id=term.upper(),
            original_text=term,
        )

    @staticmethod
    def _classify(query: str) -> QueryType:
        lowered = query.lower()
        has_document = any(term in lowered for term in _DOCUMENT_TERMS)
        has_structured = any(term in lowered for term in _STRUCTURED_TERMS)
        has_action = any(term in lowered for term in _ACTION_TERMS)

        if has_action:
            return "action_request"
        if has_document and has_structured:
            return "hybrid"
        if has_document:
            return "document_knowledge"
        return "structured_fact"

    @staticmethod
    def _resolve_time(query: str, now: datetime) -> TimeRange | None:
        lowered = query.lower()
        if "今天" in query or "today" in lowered:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return TimeRange(
                start=start,
                end=start + timedelta(days=1),
                original_expression="今天" if "今天" in query else "today",
            )
        if "昨天" in query or "yesterday" in lowered:
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return TimeRange(
                start=end - timedelta(days=1),
                end=end,
                original_expression="昨天" if "昨天" in query else "yesterday",
            )
        return None

    @staticmethod
    def _missing_inputs(
        query: str,
        query_type: QueryType,
        entities: tuple[ResolvedEntity, ...],
    ) -> tuple[MissingInput, ...]:
        entity_types = {entity.entity_type for entity in entities}
        if (
            "设备" in query or "equipment" in query.lower()
        ) and "equipment" not in entity_types:
            return (
                MissingInput(
                    field_name="equipment_id_or_area",
                    reason="设备问题需要设备编号或区域范围",
                    required_for_execution=query_type == "action_request",
                ),
            )
        return ()

    @staticmethod
    def _keywords(query: str, protected_terms: tuple[str, ...]) -> tuple[str, ...]:
        matched = [
            term
            for term in (*_DOCUMENT_TERMS, *_STRUCTURED_TERMS)
            if term in query.lower()
        ]
        return tuple(dict.fromkeys((*protected_terms, *matched)))

    @staticmethod
    def _freshness(query_type: QueryType, query: str) -> str:
        if query_type in {"structured_fact", "action_request", "hybrid"}:
            if any(
                term in query.lower() for term in ("当前", "实时", "current", "live")
            ):
                return "live"
            return "minutes"
        return "versioned"
