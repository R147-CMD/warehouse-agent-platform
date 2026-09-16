"""Fail-closed risk classification for tools that may need human approval."""

import os
from typing import Any, Protocol, Sequence

from .models import RiskAssessment


class ToolDescriptor(Protocol):
    """The tool attributes required for risk assessment without a circular import."""

    name: str
    category: Any
    capabilities: Sequence[str]
    metadata: dict[str, Any]


_MUTATING_TOKENS = frozenset(
    {
        "create",
        "update",
        "delete",
        "adjust",
        "assign",
        "dispatch",
        "start",
        "stop",
        "cancel",
        "close",
        "approve",
        "allocate",
        "release",
        "record",
    }
)
_READ_TOKENS = frozenset(
    {
        "get",
        "list",
        "read",
        "query",
        "search",
        "status",
        "report",
        "forecast",
        "describe",
    }
)
_FORCE_HIGH_RISK_NAMES = frozenset(
    {
        "acknowledge_safety_alert",
        "assign_equipment",
        "broadcast_alert",
        "control_equipment",
        "reconcile_inventory",
        "reserve_inventory",
        "set_environmental_controls",
    }
)
_FORCE_HIGH_RISK_PREFIXES = (
    "configure_",
    "control_",
    "write_",
)


def _configured_tool_names(variable_name: str) -> frozenset[str]:
    """Read comma-separated tool-name additions without granting policy overrides."""

    return frozenset(
        item.strip().lower()
        for item in os.getenv(variable_name, "").split(",")
        if item.strip()
    )


def _tokens(values: Sequence[str]) -> set[str]:
    """Normalize tool names and capabilities into underscore-delimited tokens."""

    tokens: set[str] = set()
    for value in values:
        tokens.update(part for part in value.lower().replace("-", "_").split("_") if part)
    return tokens


def _category_value(category: Any) -> str:
    """Support enum and string categories without importing the discovery module."""

    value = getattr(category, "value", category)
    return str(value).lower()


class ApprovalPolicy:
    """Classify discovered tools conservatively before they can execute."""

    def assess(self, tool: ToolDescriptor) -> RiskAssessment:
        """Return a fail-closed assessment in documented precedence order."""

        name = tool.name.strip().lower()
        metadata = tool.metadata or {}
        capabilities = tuple(str(capability) for capability in (tool.capabilities or ()))
        tokens = _tokens((name, *capabilities))

        if name in _FORCE_HIGH_RISK_NAMES or name.startswith(_FORCE_HIGH_RISK_PREFIXES):
            return RiskAssessment(True, "high", ("code-owned high-risk tool",))

        if name in _configured_tool_names("LANGGRAPH_APPROVAL_HIGH_RISK_TOOLS"):
            return RiskAssessment(True, "high", ("configured high-risk tool",))

        if metadata.get("requires_approval") is True:
            return RiskAssessment(True, "high", ("tool metadata requires approval",))
        if metadata.get("read_only") is False:
            return RiskAssessment(True, "high", ("tool metadata marks it non-read-only",))
        if metadata.get("mutating") is True:
            return RiskAssessment(True, "high", ("tool metadata marks it mutating",))

        if _category_value(tool.category) == "data_modification":
            return RiskAssessment(True, "high", ("data modification category",))
        if mutating_tokens := tuple(sorted(tokens & _MUTATING_TOKENS)):
            return RiskAssessment(True, "high", (f"mutating tokens: {', '.join(mutating_tokens)}",))

        read_tokens = tokens & _READ_TOKENS
        if (
            metadata.get("read_only") is True
            and read_tokens
            and not (tokens & _MUTATING_TOKENS)
        ):
            return RiskAssessment(False, "read", ("metadata and tokens confirm read-only",))

        if name in _configured_tool_names("LANGGRAPH_APPROVAL_READ_ONLY_TOOLS"):
            return RiskAssessment(False, "read", ("configured read-only tool",))

        return RiskAssessment(True, "unknown", ("tool risk could not be confirmed as read-only",))

    def requires_approval(self, tool: ToolDescriptor) -> bool:
        """Return whether the tool must be interrupted for human approval."""

        return self.assess(tool).requires_approval
