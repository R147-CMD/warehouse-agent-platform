"""Low-cardinality metrics facade for Planner, Agent, Retrieval and Commands."""

from __future__ import annotations

from prometheus_client import CollectorRegistry

from .runtime_v2 import RuntimeMetricsV2


class AgentMetricsV2:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self._metrics = RuntimeMetricsV2(registry)

    def record_run(self, status: str, planning_mode: str) -> None:
        self._metrics.runs.labels(status=status, planning_mode=planning_mode).inc()

    def record_agent_task(self, agent: str, capability: str, status: str) -> None:
        self._metrics.agent_tasks.labels(
            agent=agent, capability=capability, status=status
        ).inc()

    def record_retrieval(self, channel: str, status: str) -> None:
        self._metrics.retrieval.labels(channel=channel, status=status).inc()

    def record_command(self, capability: str, status: str) -> None:
        self._metrics.commands.labels(capability=capability, status=status).inc()

    def observe_plan_compile(self, seconds: float) -> None:
        self._metrics.plan_compile_seconds.observe(seconds)
