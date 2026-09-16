"""Low-cardinality Prometheus metrics for the V2 control plane."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram


class RuntimeMetricsV2:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        registry = registry or CollectorRegistry()
        self.runs = Counter(
            "warehouse_agent_v2_runs_total",
            "V2 Agent runs",
            ("status", "planning_mode"),
            registry=registry,
        )
        self.plan_compile_seconds = Histogram(
            "warehouse_agent_v2_plan_compile_seconds",
            "Plan compilation duration",
            registry=registry,
        )
        self.agent_tasks = Counter(
            "warehouse_agent_v2_tasks_total",
            "Specialist Agent tasks",
            ("agent", "capability", "status"),
            registry=registry,
        )
        self.retrieval = Counter(
            "warehouse_agent_v2_retrieval_total",
            "Retrieval channel outcomes",
            ("channel", "status"),
            registry=registry,
        )
        self.commands = Counter(
            "warehouse_agent_v2_commands_total",
            "Governed commands",
            ("capability", "status"),
            registry=registry,
        )
