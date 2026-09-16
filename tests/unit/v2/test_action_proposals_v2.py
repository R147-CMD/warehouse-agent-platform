from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.agents.v2.action_proposals import SAPActionProposalFactory
from src.api.domain.agent_protocols import AgentTask
from src.api.domain.identity import IdentityContext


@pytest.mark.asyncio
async def test_sap_assignment_proposal_binds_target_arguments_and_etag() -> None:
    task = AgentTask(
        task_id="t1",
        run_id="r1",
        node_id="proposal",
        capability="sap.ewm.order.assign.propose",
        objective="将 SAP 仓库订单 2000005003 分配给 RES2",
        inputs={
            "current": {
                "data": {"orders": [{"order_id": "2000005003", "etag": 'W/"ORDER-7"'}]}
            }
        },
        identity=IdentityContext(
            tenant_id="t1",
            user_id="u1",
            scopes=("sap.order.assign",),
            warehouse_scope=("EW01",),
            authenticated_at=datetime.now(UTC),
        ),
    )

    proposal = await SAPActionProposalFactory.assign_order(task)

    assert proposal.capability == "sap.ewm.order.assign"
    assert proposal.arguments == {
        "warehouse_order": "2000005003",
        "resource": "RES2",
    }
    assert proposal.target.expected_version == 'W/"ORDER-7"'
