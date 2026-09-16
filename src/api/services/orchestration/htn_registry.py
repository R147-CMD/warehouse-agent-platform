"""Versioned, deterministic HTN templates for standard warehouse workflows."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

from .models import PlanGraph, PlanNode, ValueBinding

HTNBuilder = Callable[[str], PlanGraph]


class HTNRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, HTNBuilder] = {}

    def register(self, template_id: str, builder: HTNBuilder) -> None:
        if template_id in self._builders:
            raise ValueError(f"duplicate HTN template: {template_id}")
        self._builders[template_id] = builder

    def expand(self, template_id: str, *, objective: str) -> PlanGraph:
        try:
            builder = self._builders[template_id]
        except KeyError as error:
            raise KeyError(f"unknown HTN template: {template_id}") from error
        return builder(objective.strip())


def _plan_id(template_id: str, objective: str) -> str:
    digest = sha256(f"{template_id}:{objective}".encode("utf-8")).hexdigest()[:20]
    return f"htn-{digest}"


def _rebalance_picking_tasks(objective: str) -> PlanGraph:
    template_id = "rebalance_picking_tasks.v1"
    return PlanGraph(
        plan_id=_plan_id(template_id, objective),
        version=1,
        objective=objective,
        nodes=(
            PlanNode(
                node_id="query_tasks",
                node_type="task",
                capability="warehouse.tasks.query",
            ),
            PlanNode(
                node_id="query_workforce",
                node_type="task",
                capability="workforce.availability.query",
            ),
            PlanNode(
                node_id="build_proposal",
                node_type="task",
                capability="warehouse.tasks.rebalance.propose",
                depends_on=("query_tasks", "query_workforce"),
            ),
            PlanNode(
                node_id="approval",
                node_type="approval",
                depends_on=("build_proposal",),
            ),
            PlanNode(
                node_id="command",
                node_type="command",
                depends_on=("approval",),
            ),
            PlanNode(
                node_id="verify",
                node_type="verify",
                depends_on=("command",),
            ),
            PlanNode(
                node_id="answer",
                node_type="answer",
                depends_on=("verify",),
            ),
        ),
    )


def _controlled_action(objective: str) -> PlanGraph:
    template_id = "controlled_action.v1"
    return PlanGraph(
        plan_id=_plan_id(template_id, objective),
        version=1,
        objective=objective,
        nodes=(
            PlanNode(
                node_id="proposal",
                node_type="task",
                capability="warehouse.action.propose",
            ),
            PlanNode(
                node_id="approval", node_type="approval", depends_on=("proposal",)
            ),
            PlanNode(node_id="command", node_type="command", depends_on=("approval",)),
            PlanNode(node_id="verify", node_type="verify", depends_on=("command",)),
            PlanNode(node_id="answer", node_type="answer", depends_on=("verify",)),
        ),
    )


def _governed_action_plan(
    objective: str, *, template_id: str, read_capability: str, proposal_capability: str
) -> PlanGraph:
    return PlanGraph(
        plan_id=_plan_id(template_id, objective),
        version=1,
        objective=objective,
        nodes=(
            PlanNode(
                node_id="read_current", node_type="task", capability=read_capability
            ),
            PlanNode(
                node_id="proposal",
                node_type="task",
                capability=proposal_capability,
                depends_on=("read_current",),
                inputs={
                    "current": ValueBinding(
                        source="node_output", path="read_current.result"
                    )
                },
            ),
            PlanNode(
                node_id="approval", node_type="approval", depends_on=("proposal",)
            ),
            PlanNode(node_id="command", node_type="command", depends_on=("approval",)),
            PlanNode(node_id="verify", node_type="verify", depends_on=("command",)),
            PlanNode(node_id="answer", node_type="answer", depends_on=("verify",)),
        ),
    )


def _sap_assign_order(objective: str) -> PlanGraph:
    return _governed_action_plan(
        objective,
        template_id="sap_assign_order.v1",
        read_capability="sap.ewm.orders.query",
        proposal_capability="sap.ewm.order.assign.propose",
    )


def _sap_confirm_task(objective: str) -> PlanGraph:
    return _governed_action_plan(
        objective,
        template_id="sap_confirm_task.v1",
        read_capability="sap.ewm.orders.query",
        proposal_capability="sap.ewm.task.confirm.propose",
    )


def _equipment_dispatch(objective: str) -> PlanGraph:
    return _governed_action_plan(
        objective,
        template_id="equipment_dispatch.v1",
        read_capability="equipment.status.query",
        proposal_capability="equipment.dispatch.propose",
    )


def build_default_htn_registry() -> HTNRegistry:
    registry = HTNRegistry()
    registry.register("rebalance_picking_tasks.v1", _rebalance_picking_tasks)
    registry.register("controlled_action.v1", _controlled_action)
    registry.register("sap_assign_order.v1", _sap_assign_order)
    registry.register("sap_confirm_task.v1", _sap_confirm_task)
    registry.register("equipment_dispatch.v1", _equipment_dispatch)
    return registry
