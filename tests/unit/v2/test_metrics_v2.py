from __future__ import annotations

from prometheus_client import CollectorRegistry, generate_latest

from src.api.services.monitoring.metrics_v2 import AgentMetricsV2


def test_agent_metrics_use_low_cardinality_dimensions() -> None:
    registry = CollectorRegistry()
    metrics = AgentMetricsV2(registry)
    metrics.record_run("succeeded", "fast_path")
    metrics.record_agent_task("operations", "inventory.read", "succeeded")
    metrics.record_retrieval("bm25", "hit")
    metrics.record_command("sap.task.confirm", "approved")

    output = generate_latest(registry).decode("utf-8")
    assert (
        'warehouse_agent_v2_runs_total{planning_mode="fast_path",status="succeeded"}'
        in output
    )
    assert (
        'warehouse_agent_v2_tasks_total{agent="operations",capability="inventory.read",status="succeeded"}'
        in output
    )
    assert (
        'warehouse_agent_v2_commands_total{capability="sap.task.confirm",status="approved"}'
        in output
    )
