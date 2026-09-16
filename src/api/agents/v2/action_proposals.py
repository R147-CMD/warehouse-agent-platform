"""Deterministic proposal builders; these functions never execute side effects."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

from src.api.domain.agent_protocols import AgentTask, ProposedAction, ResourceRef


def _find_value(value: Any, keys: tuple[str, ...]) -> Any | None:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, ""):
                return value[key]
        for nested in value.values():
            found = _find_value(nested, keys)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_value(nested, keys)
            if found is not None:
                return found
    return None


def _action_id(task: AgentTask, target: str) -> str:
    return (
        "action-"
        + sha256(
            f"{task.run_id}:{task.capability}:{target}".encode("utf-8")
        ).hexdigest()[:24]
    )


class SAPActionProposalFactory:
    @staticmethod
    async def assign_order(task: AgentTask) -> ProposedAction:
        order_match = re.search(
            r"(?:订单|order)\s*(?:WO-)?(\d{6,20})", task.objective, re.IGNORECASE
        )
        resource_match = re.search(
            r"(?:给|to)\s*(RES[-_A-Z0-9]+)", task.objective, re.IGNORECASE
        )
        if not order_match or not resource_match:
            raise ValueError("warehouse order and target resource are required")
        order_id = order_match.group(1)
        resource = resource_match.group(1).upper()
        expected_version = _find_value(
            task.inputs.get("current"), ("etag", "@odata.etag")
        )
        if not expected_version:
            raise ValueError("fresh warehouse order ETag is required")
        warehouse_id = (
            task.identity.warehouse_scope[0] if task.identity.warehouse_scope else None
        )
        return ProposedAction(
            action_id=_action_id(task, order_id),
            capability="sap.ewm.order.assign",
            target=ResourceRef(
                resource_type="warehouse_order",
                resource_id=order_id,
                warehouse_id=warehouse_id,
                expected_version=str(expected_version),
            ),
            arguments={"warehouse_order": order_id, "resource": resource},
            expected_effect=f"Assign SAP warehouse order {order_id} to {resource}",
            risk_level="high",
            required_scopes=("sap.order.assign",),
            idempotency_key=f"{task.identity.tenant_id}:{warehouse_id}:sap-order-assign:{order_id}:{resource}",
        )

    @staticmethod
    async def confirm_task(task: AgentTask) -> ProposedAction:
        task_match = re.search(
            r"(?:任务|task)\s*(?:WT-)?(\d{6,20})", task.objective, re.IGNORECASE
        )
        if not task_match:
            raise ValueError("warehouse task is required")
        warehouse_task = task_match.group(1)
        task_item = str(
            _find_value(task.inputs.get("current"), ("task_item", "WarehouseTaskItem"))
            or "0"
        )
        expected_version = _find_value(
            task.inputs.get("current"), ("etag", "@odata.etag")
        )
        if not expected_version:
            raise ValueError("fresh warehouse task ETag is required")
        warehouse_id = (
            task.identity.warehouse_scope[0] if task.identity.warehouse_scope else None
        )
        return ProposedAction(
            action_id=_action_id(task, warehouse_task),
            capability="sap.ewm.task.confirm",
            target=ResourceRef(
                resource_type="warehouse_task",
                resource_id=warehouse_task,
                warehouse_id=warehouse_id,
                expected_version=str(expected_version),
            ),
            arguments={
                "warehouse_task": warehouse_task,
                "warehouse_task_item": task_item,
            },
            expected_effect=f"Confirm SAP warehouse task {warehouse_task}/{task_item}",
            risk_level="high",
            required_scopes=("sap.task.confirm",),
            idempotency_key=f"{task.identity.tenant_id}:{warehouse_id}:sap-task-confirm:{warehouse_task}:{task_item}",
        )


def build_default_action_proposal_handlers():
    return {
        "sap.ewm.order.assign.propose": SAPActionProposalFactory.assign_order,
        "sap.ewm.task.confirm.propose": SAPActionProposalFactory.confirm_task,
    }
