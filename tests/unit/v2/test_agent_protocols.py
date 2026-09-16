from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def _types():
    from src.api.domain.agent_protocols import (
        AgentError,
        AgentResult,
        AgentTask,
        ProposedAction,
        ResourceRef,
    )
    from src.api.domain.errors import ErrorCategory
    from src.api.domain.identity import IdentityContext

    return {
        "AgentError": AgentError,
        "AgentResult": AgentResult,
        "AgentTask": AgentTask,
        "ProposedAction": ProposedAction,
        "ResourceRef": ResourceRef,
        "ErrorCategory": ErrorCategory,
        "IdentityContext": IdentityContext,
    }


def _identity(identity_type):
    return identity_type(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("supervisor",),
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def test_agent_task_rejects_blank_objective():
    types = _types()

    with pytest.raises(ValidationError):
        types["AgentTask"](
            task_id="task-1",
            run_id="run-1",
            node_id="node-1",
            capability="warehouse.inventory.query",
            objective="  ",
            identity=_identity(types["IdentityContext"]),
        )


def test_proposed_action_requires_idempotency_key():
    types = _types()

    with pytest.raises(ValidationError):
        types["ProposedAction"](
            action_id="action-1",
            capability="sap_ewm.assign_warehouse_order",
            target=types["ResourceRef"](
                resource_type="warehouse_order", resource_id="WO-1"
            ),
            arguments={"assignee_id": "EMP-1"},
            expected_effect="warehouse order assigned",
            risk_level="high",
            required_scopes=("ewm.order.assign",),
            idempotency_key="",
        )


def test_failed_agent_result_requires_structured_error():
    types = _types()

    with pytest.raises(ValidationError):
        types["AgentResult"](
            task_id="task-1",
            status="failed",
            summary="request failed",
            confidence=0.0,
        )

    result = types["AgentResult"](
        task_id="task-1",
        status="failed",
        summary="upstream timed out",
        confidence=0.0,
        error=types["AgentError"](
            code="upstream_timeout",
            category=types["ErrorCategory"].TIMEOUT,
            message="SAP query timed out",
            retryable=True,
        ),
    )

    assert result.error is not None
    assert result.error.retryable is True


def test_agent_result_confidence_is_bounded():
    types = _types()

    with pytest.raises(ValidationError):
        types["AgentResult"](
            task_id="task-1",
            status="succeeded",
            summary="ok",
            confidence=1.1,
        )
