from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient
from src.api.agents.v2.action_proposals import SAPActionProposalFactory
from src.api.domain.agent_protocols import AgentTask
from src.api.domain.identity import IdentityContext
from src.api.services.execution.control_plane import ControlledExecutionService
from src.api.services.execution.outbox_relay import OutboxRelay
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
async def test_agent_proposal_requires_approval_then_executes_once_through_outbox() -> (
    None
):
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
        adapter = SAPEWMAdapter(
            config, client=SAPEWMODataClient(config, http_client=http_client)
        )
        service = WMSIntegrationService()
        service.adapters[config.connection_id] = adapter
        task = AgentTask(
            task_id="task-1",
            run_id="run-1",
            node_id="propose",
            capability="sap.ewm.order.assign.propose",
            objective="Assign order 2000005003 to RES2",
            inputs={"current": {"etag": 'W/"MOCK-2000005003-1"'}},
            identity=identity("requester"),
        )
        action = await SAPActionProposalFactory.assign_order(task)

        counts = (await http_client.get("/_mock/requests")).json()
        assert counts.get("assign_order", 0) == 0

        store = InMemoryExecutionStore()
        evidence_store = InMemoryEvidenceStore()
        control_plane = ControlledExecutionService(store)
        await control_plane.register("run-1", identity("requester"), (action,))
        pending = await control_plane.request_approval(
            action.action_id, identity("requester")
        )
        counts = (await http_client.get("/_mock/requests")).json()
        assert counts.get("assign_order", 0) == 0
        _approval, command = await control_plane.decide(
            pending.approval_id, identity("approver"), approve=True
        )
        assert command is not None

        handlers = SAPEWMCommandHandlers(service, connection_id=config.connection_id)
        worker = CommandWorker(
            store, handlers.bindings(), evidence_store=evidence_store
        )

        async def deliver(_event_id: str, command_id: str) -> None:
            await worker.process(command_id)
            await worker.process(command_id)  # at-least-once duplicate delivery

        report = await OutboxRelay(store, deliver).publish_batch(limit=10)
        executed = await store.get_command(command.command_id)

        counts = (await http_client.get("/_mock/requests")).json()
        evidence = await evidence_store.query(identity("requester"))

    assert report.delivered == 1
    assert executed is not None and executed.status == "succeeded"
    assert executed.readback["executing_resource"] == "RES2"
    assert counts["assign_order"] == 1
    assert len(evidence) == 1
    assert evidence[0].ref.evidence_type == "execution_readback"
    assert evidence[0].ref.source_version == 'W/"MOCK-2000005003-2"'
    assert executed.evidence_refs == (evidence[0].ref,)
