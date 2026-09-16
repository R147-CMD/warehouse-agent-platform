from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.agents.v2.catalog import AGENT_DEFINITIONS, build_specialist_executors
from src.api.domain.agent_protocols import AgentTask
from src.api.domain.identity import IdentityContext


@pytest.mark.asyncio
@pytest.mark.parametrize("definition", AGENT_DEFINITIONS)
async def test_all_five_specialist_agents_use_uniform_protocol(definition) -> None:
    capability = definition.capabilities[0]

    async def handler(task):
        return {"agent": definition.agent_id, "capability": task.capability}

    executors = build_specialist_executors({capability: handler})
    task = AgentTask(
        task_id=f"t-{definition.agent_id}",
        run_id="run-1",
        node_id="node-1",
        capability=capability,
        objective="test",
        identity=IdentityContext(
            tenant_id="tenant-1",
            user_id="user-1",
            authenticated_at=datetime.now(UTC),
        ),
    )

    result = await executors.get(definition.agent_id).execute(task)

    assert result.status == "succeeded"
    assert result.task_id == task.task_id
    assert result.data["agent"] == definition.agent_id
