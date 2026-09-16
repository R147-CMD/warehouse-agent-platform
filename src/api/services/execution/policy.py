"""Deterministic RBAC/ABAC and server-side risk decisions."""

from __future__ import annotations

from src.api.domain.agent_protocols import ProposedAction
from src.api.domain.identity import IdentityContext

from .models import PolicyDecision


class PolicyEngine:
    def evaluate(
        self, action: ProposedAction, identity: IdentityContext
    ) -> PolicyDecision:
        if not set(action.required_scopes).issubset(identity.scopes):
            return PolicyDecision(
                decision="deny",
                risk_level=action.risk_level,
                reasons=("required_scope_missing",),
            )
        warehouse_id = action.target.warehouse_id
        if warehouse_id and warehouse_id not in identity.warehouse_scope:
            return PolicyDecision(
                decision="deny",
                risk_level=action.risk_level,
                reasons=("warehouse_out_of_scope",),
            )
        # The server never accepts an Agent-provided downgrade for known writes.
        known_write = any(
            token in action.capability
            for token in (
                "assign",
                "confirm",
                "create",
                "update",
                "dispatch",
                "publish",
            )
        )
        effective_risk = (
            "high"
            if known_write and action.risk_level in {"low", "medium"}
            else action.risk_level
        )
        if (
            action.capability.startswith("sap.ewm")
            and not action.target.expected_version
        ):
            return PolicyDecision(
                decision="fresh_evidence_required",
                risk_level=effective_risk,
                reasons=("expected_version_required",),
            )
        if effective_risk == "critical":
            return PolicyDecision(
                decision="dual_approval",
                risk_level=effective_risk,
                reasons=("critical_write",),
            )
        if effective_risk in {"medium", "high"} or known_write:
            return PolicyDecision(
                decision="approval_required",
                risk_level=effective_risk,
                reasons=("state_changing_operation",),
            )
        return PolicyDecision(
            decision="allow", risk_level=effective_risk, reasons=("low_risk_read",)
        )
