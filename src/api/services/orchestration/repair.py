"""Immutable loop budgets used by reflection, retrieval, and replanning."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RepairKind = Literal["reflection", "retrieval_rewrite", "replan"]


class RepairBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reflection_remaining: int = Field(default=1, ge=0, le=2)
    retrieval_rewrite_remaining: int = Field(default=2, ge=0, le=2)
    replan_remaining: int = Field(default=2, ge=0, le=2)

    def consume(self, kind: RepairKind) -> "RepairBudget":
        field_name = f"{kind}_remaining"
        remaining = getattr(self, field_name)
        if remaining <= 0:
            raise ValueError(f"{kind} budget exhausted")
        return self.model_copy(update={field_name: remaining - 1})
