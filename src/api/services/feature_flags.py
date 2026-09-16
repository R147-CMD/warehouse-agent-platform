"""Feature flags for the incremental V2 agent platform rollout.

All new runtime paths are fail-closed and disabled unless an operator sets an
explicit truthy value.  Reading the environment on demand keeps tests and
process startup behavior predictable without a mutable module-level cache.
"""

from __future__ import annotations

from dataclasses import dataclass
import os


_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})


def _is_enabled(variable_name: str) -> bool:
    return os.getenv(variable_name, "false").strip().lower() in _TRUTHY_VALUES


@dataclass(frozen=True, slots=True)
class FeatureFlags:
    """Server-controlled rollout switches for independently shippable V2 paths."""

    agent_runtime_v2_enabled: bool = False
    retrieval_v2_enabled: bool = False
    execution_v2_enabled: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        return cls(
            agent_runtime_v2_enabled=_is_enabled(
                "WAREHOUSE_AGENT_RUNTIME_V2_ENABLED"
            ),
            retrieval_v2_enabled=_is_enabled("WAREHOUSE_RETRIEVAL_V2_ENABLED"),
            execution_v2_enabled=_is_enabled("WAREHOUSE_EXECUTION_V2_ENABLED"),
        )
