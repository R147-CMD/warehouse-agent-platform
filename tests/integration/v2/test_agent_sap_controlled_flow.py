from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient
from src.api.agents.v2.specialist import SpecialistAgent
from src.api.domain.agent_protocols import AgentTask, ProposedAction, ResourceRef
from src.api.domain.identity import IdentityContext
from src.api.services.execution.approval_service import ApprovalService
from src.api.services.execution.command_service import CommandService
from src.api.services.execution.sap_handlers import SAPEWMCommandHandlers
from src.api.services.execution.store import InMemoryExecutionStore
from src.api.services.execution.worker import CommandWorker
from src.api.services.evidence_v2.store import InMemoryEvidenceStore
from src.api.services.wms.integration_service import WMSIntegrationService
from src.mock_servers.sap_ewm.app import create_app


def identity(user: str) -> IdentityContext:
    return IdentityContext(
        tenant_id="tenant-1",
        user_id=user,
        roles=("warehouse_manager",),
        scopes=("sap.order.assign",),
        warehouse_scope=("EW01",),
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_agent_to_approval_outbox_worker_sap_and_readback() -> None:
    async def propose(task: AgentTask) -> ProposedAction:
        return ProposedAction(
            action_id="assign-2000005003",
            capability="sap.ewm.order.assign",
            target=ResourceRef(
                resource_type="warehouse_order",
                resource_id="2000005003",
                warehouse_id="EW01",
                expected_version='W/"MOCK-2000005003-1"',
            ),
            arguments={"warehouse_order": "2000005003", "resource": "RES2"},
            expected_effect="Assign warehouse order to RES2",
            risk_level="high",
            required_scopes=("sap.order.assign",),
            idempotency_key="tenant-1:EW01:assign:2000005003:RES2",
        )

    agent = SpecialistAgent(
        "operations-agent-v2",
        ("sap.ewm.order.assign.propose",),
        {"sap.ewm.order.assign.propose": propose},
    )
    task = AgentTask(
        task_id="task-1",
        run_id="run-1",
        node_id="proposal",
        capability="sap.ewm.order.assign.propose",
        objective="Assign SAP order 2000005003 to RES2",
        identity=identity("requester"),
    )
    agent_result = await agent.execute(task)
    action = agent_result.proposed_actions[0]

    store = InMemoryExecutionStore()
    evidence_store = InMemoryEvidenceStore()
    approval_service = ApprovalService(store)
    pending = await approval_service.request(action, identity("requester"))
    approved = await approval_service.decide(
        pending.approval_id, action, identity("approver"), approve=True
    )
    command = await CommandService(store).enqueue(
        approved, action, identity("requester")
    )

    app = create_app(control_enabled=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://sap.example.test"
    ) as http_client:
        config = SAPEWMConfig(
            enabled=True,
            mock_mode=True,
            base_url="http://sap.example.test",
            warehouse="EW01",
            auth_mode="basic",
            username="mock-user",
            password="mock-password",
            verify_tls=False,
        )
        sap_client = SAPEWMODataClient(config, http_client=http_client)
        adapter = SAPEWMAdapter(config, client=sap_client)
        service = WMSIntegrationService()
        service.adapters[config.connection_id] = adapter
        handlers = SAPEWMCommandHandlers(service, connection_id=config.connection_id)
        executed = await CommandWorker(
            store, handlers.bindings(), evidence_store=evidence_store
        ).process_next()

    assert executed.command_id == command.command_id
    assert executed.status == "succeeded"
    assert executed.readback["executing_resource"] == "RES2"
    evidence = await evidence_store.query(identity("requester"))
    assert evidence[0].ref.evidence_type == "execution_readback"
    assert evidence[0].content["executing_resource"] == "RES2"
