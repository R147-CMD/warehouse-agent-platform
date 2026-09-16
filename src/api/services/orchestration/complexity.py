"""Rule-first selection of the planning path."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.retrieval.v2.contracts import QueryEnvelope


class PlanningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["fast_path", "htn", "llm", "clarify"]
    reason_codes: tuple[str, ...]


class ComplexityClassifier:
    @staticmethod
    def classify(query: QueryEnvelope) -> PlanningDecision:
        if any(item.required_for_execution for item in query.missing_inputs):
            return PlanningDecision(
                mode="clarify",
                reason_codes=("required_input_missing",),
            )
        if query.query_type == "action_request":
            return PlanningDecision(
                mode="htn",
                reason_codes=("controlled_business_action",),
            )
        if query.query_type in {"hybrid", "multi_hop"}:
            return PlanningDecision(
                mode="llm",
                reason_codes=("cross_source_or_multi_hop",),
            )
        return PlanningDecision(
            mode="fast_path",
            reason_codes=("single_read_capability",),
        )
