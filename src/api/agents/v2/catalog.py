"""Five domain Agents and their explicit capability boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from src.api.services.orchestration.agent_executor import AgentExecutorRegistry

from .specialist import SpecialistAgent


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    display_name: str
    capabilities: tuple[str, ...]


AGENT_DEFINITIONS = (
    AgentDefinition(
        "operations-agent-v2",
        "仓库运营 Agent",
        (
            "warehouse.fact.query",
            "warehouse.tasks.query",
            "workforce.availability.query",
            "warehouse.tasks.rebalance.propose",
            "warehouse.action.propose",
            "warehouse.wave.propose",
            "warehouse.route.optimize",
            "warehouse.dock.schedule.propose",
            "warehouse.shift.plan.propose",
            "warehouse.kpi.publish.propose",
            "sap.ewm.stock.query",
            "sap.ewm.orders.query",
            "sap.ewm.order.assign.propose",
            "sap.ewm.task.confirm.propose",
        ),
    ),
    AgentDefinition(
        "equipment-agent-v2",
        "设备管理 Agent",
        (
            "equipment.status.query",
            "equipment.telemetry.query",
            "equipment.maintenance.analyze",
            "equipment.dispatch.propose",
        ),
    ),
    AgentDefinition(
        "safety-agent-v2",
        "安全管理 Agent",
        (
            "safety.incident.query",
            "safety.risk.analyze",
            "safety.sop.query",
            "safety.emergency.plan",
        ),
    ),
    AgentDefinition(
        "forecasting-agent-v2",
        "需求预测 Agent",
        (
            "forecast.demand.run",
            "forecast.capacity.run",
            "forecast.workforce.run",
        ),
    ),
    AgentDefinition(
        "document-agent-v2",
        "文档处理 Agent",
        (
            "knowledge.search",
            "document.extract",
            "document.index.status",
        ),
    ),
)


def build_specialist_executors(
    handlers: dict[str, Callable[[Any], Any]],
) -> AgentExecutorRegistry:
    registry = AgentExecutorRegistry()
    for definition in AGENT_DEFINITIONS:
        registry.register(
            definition.agent_id,
            SpecialistAgent(
                definition.agent_id,
                definition.capabilities,
                {
                    capability: handlers[capability]
                    for capability in definition.capabilities
                    if capability in handlers
                },
            ),
        )
    return registry
