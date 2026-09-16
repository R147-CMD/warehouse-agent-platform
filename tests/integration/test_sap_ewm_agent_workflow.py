"""End-to-end Agent -> MCP -> WMS -> SAP EWM acceptance tests."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import re
from threading import Thread
from time import monotonic, sleep
from types import SimpleNamespace
from typing import Any, TypedDict
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
import pytest
import uvicorn

from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.adapters.wms.sap_ewm_models import SAPPage, SAPStockItem, SAPWriteResult
from src.api.agents.operations.mcp_operations_agent import (
    MCPOperationsCoordinationAgent,
)
from src.api.services.approval import (
    ApprovalConflictError,
    ApprovalDecision,
    ApprovalExecutionContext,
    ApprovalGateway,
    ApprovalInterruptPayload,
    ApprovalRecord,
    ApprovalRejectedError,
    ApprovalResumePayload,
    ApprovalStatus,
    bind_approval_context,
)
from src.api.services.mcp.adapters.sap_ewm_adapter import (
    SAPEWMMCPAdapter,
    SAPEWMMCPAdapterConfig,
)
from src.api.services.mcp.tool_discovery import ToolDiscoveryService
from src.api.services.agent_config import load_agent_config
from src.api.services.wms.integration_service import WMSIntegrationService
from src.mock_servers.sap_ewm.app import create_app
from src.mock_servers.sap_ewm.repository import MockRepository


class InMemoryApprovalRepository:
    """Small replay-safe repository double for the approval integration boundary."""

    def __init__(self) -> None:
        self.records: dict[str, ApprovalRecord] = {}

    async def ensure_pending(
        self, context, tool_key, tool_name, arguments, action_index, risk
    ) -> ApprovalRecord:
        action_key = f"{context.request_id}:{action_index}:{tool_key}"
        if action_key in self.records:
            return self.records[action_key]
        now = datetime.now(timezone.utc)
        record = ApprovalRecord(
            approval_id=uuid4(),
            thread_id=context.thread_id,
            checkpoint_ns=context.checkpoint_ns,
            request_id=context.request_id,
            action_key=action_key,
            idempotency_key=action_key,
            tool_key=tool_key,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk.risk_level,
            risk_reasons=list(risk.reasons),
            requester_id=context.requester_id,
            requester_username=context.requester_username,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            updated_at=now,
        )
        self.records[action_key] = record
        return record

    async def record_rejection(
        self, approval_id, resume_payload, *, expired=False
    ) -> ApprovalRecord:
        record = self._find(approval_id)
        updated = record.model_copy(
            update={
                "status": (
                    ApprovalStatus.EXPIRED if expired else ApprovalStatus.REJECTED
                ),
                "approver_id": resume_payload.approver_id,
                "approver_username": resume_payload.approver_username,
            }
        )
        self.records[record.action_key] = updated
        return updated

    async def claim_approved_execution(
        self, approval_id, resume_payload
    ) -> ApprovalRecord:
        record = self._find(approval_id)
        if record.status is ApprovalStatus.EXECUTED:
            return record
        if record.status not in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
            raise ApprovalConflictError(
                f"Approval in {record.status.value} state cannot execute"
            )
        updated = record.model_copy(
            update={
                "status": ApprovalStatus.EXECUTING,
                "approver_id": resume_payload.approver_id,
                "approver_username": resume_payload.approver_username,
            }
        )
        self.records[record.action_key] = updated
        return updated

    async def get(self, approval_id: UUID) -> ApprovalRecord | None:
        try:
            return self._find(approval_id)
        except StopIteration:
            return None

    async def mark_executed(self, approval_id, result) -> ApprovalRecord:
        record = self._find(approval_id)
        updated = record.model_copy(
            update={"status": ApprovalStatus.EXECUTED, "result": result}
        )
        self.records[record.action_key] = updated
        return updated

    async def mark_failed(self, approval_id, error_summary) -> ApprovalRecord:
        record = self._find(approval_id)
        updated = record.model_copy(
            update={"status": ApprovalStatus.FAILED, "error": error_summary}
        )
        self.records[record.action_key] = updated
        return updated

    def _find(self, approval_id) -> ApprovalRecord:
        return next(
            record
            for record in self.records.values()
            if record.approval_id == approval_id
        )


def _sap_config() -> SAPEWMConfig:
    return SAPEWMConfig(
        enabled=True,
        mock_mode=True,
        base_url="http://sap.example.test",
        warehouse="EW01",
        client="100",
        auth_mode="basic",
        username="svc-user",
        password="svc-password",
        verify_tls=False,
    )


def _context(request_id: str) -> ApprovalExecutionContext:
    return ApprovalExecutionContext(
        thread_id="thread-sap",
        checkpoint_ns="operations",
        request_id=request_id,
        requester_id=7,
        requester_username="warehouse-user",
    )


@pytest.mark.asyncio
async def test_sap_read_write_approval_and_replay_boundary(monkeypatch) -> None:
    monkeypatch.setenv("SAP_EWM_EXPOSE_LEGACY_WRITE_TOOLS", "true")
    import src.api.services.approval.gateway as gateway_module
    import src.api.services.mcp.tool_discovery as discovery_module

    service = AsyncMock(spec=WMSIntegrationService)
    service.adapters = {}
    service.add_wms_connection.return_value = True
    service.get_physical_stock.return_value = SAPPage(
        items=[
            SAPStockItem(
                warehouse="EW01",
                sku="TG11",
                storage_bin="T010-02-05-A",
                quantity=Decimal("956"),
                unit="EA",
                stock_item_uuid="stock-uuid-1",
            )
        ]
    )
    service.assign_warehouse_order.return_value = SAPWriteResult(
        operation="assign_warehouse_order",
        entity_id="2000005003",
        status="ASSIGNED",
    )
    adapter = SAPEWMMCPAdapter(
        SAPEWMMCPAdapterConfig(),
        _sap_config(),
        service,
        request_id_factory=lambda: "sap-request-id",
    )
    await adapter.initialize()

    discovery = ToolDiscoveryService()
    assert await discovery.register_discovery_source(
        "sap_ewm_tools", adapter, "mcp_adapter"
    )
    tools = {
        tool.name: tool.tool_id
        for tool in await discovery.get_tools_by_source("sap_ewm_tools")
    }

    repository = InMemoryApprovalRepository()
    gateway = ApprovalGateway(repository_provider=lambda: repository)
    monkeypatch.setattr(discovery_module, "get_approval_gateway", lambda: gateway)
    decision = {"value": ApprovalDecision.APPROVE}

    def resume_approval(payload: dict[str, object]) -> dict[str, object]:
        return ApprovalResumePayload(
            approval_id=payload["approval_id"],
            decision=decision["value"],
            approver_id=11,
            approver_username="shift-manager",
            reason="verified",
        ).model_dump(mode="json")

    monkeypatch.setattr(gateway_module, "interrupt", resume_approval)

    stock = await discovery.execute_tool(
        tools["sap_ewm_get_physical_stock"],
        {"product": "TG11"},
    )
    assert stock["data"]["items"][0]["sku"] == "TG11"
    service.get_physical_stock.assert_awaited_once()
    assert repository.records == {}

    write_arguments = {
        "warehouse_order": "2000005003",
        "resource": "RES2",
        "reason": "balance workload",
    }
    decision["value"] = ApprovalDecision.REJECT
    with bind_approval_context(_context("request-reject")):
        with pytest.raises(ApprovalRejectedError):
            await discovery.execute_tool(
                tools["sap_ewm_assign_warehouse_order"],
                write_arguments,
                action_index=0,
            )
    service.assign_warehouse_order.assert_not_awaited()

    decision["value"] = ApprovalDecision.APPROVE
    approval_context = _context("request-approve")
    with bind_approval_context(approval_context):
        first = await discovery.execute_tool(
            tools["sap_ewm_assign_warehouse_order"],
            write_arguments,
            action_index=0,
        )
    with bind_approval_context(approval_context):
        replay = await discovery.execute_tool(
            tools["sap_ewm_assign_warehouse_order"],
            write_arguments,
            action_index=0,
        )

    assert first["data"]["status"] == "ASSIGNED"
    assert replay == first
    service.assign_warehouse_order.assert_awaited_once()


@dataclass
class RunningSAPMock:
    base_url: str
    repository: MockRepository


@pytest.fixture
def running_mock(unused_tcp_port: int):
    repository = MockRepository()
    app = create_app(repository, control_enabled=True)
    base_url = f"http://127.0.0.1:{unused_tcp_port}"
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=unused_tcp_port,
            log_level="error",
        )
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()

    deadline = monotonic() + 5
    while monotonic() < deadline:
        try:
            if httpx.get(base_url + "/health", timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            sleep(0.02)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("SAP EWM acceptance mock did not become ready")

    yield RunningSAPMock(base_url=base_url, repository=repository)

    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive()


def _live_config(running_mock: RunningSAPMock, **overrides: Any) -> SAPEWMConfig:
    values: dict[str, Any] = {
        "enabled": True,
        "connection_id": f"sap-acceptance-{uuid4()}",
        "mock_mode": True,
        "base_url": running_mock.base_url,
        "warehouse": "EW01",
        "client": "100",
        "auth_mode": "basic",
        "username": "mock-user",
        "password": "mock-password",
        "verify_tls": False,
        "connect_timeout_seconds": 1,
        "read_timeout_seconds": 1,
        "max_read_attempts": 3,
    }
    values.update(overrides)
    return SAPEWMConfig(**values)


class _ScriptedNimClient:
    async def generate_response(self, messages, **_kwargs):
        system_message = messages[0]["content"]
        if "Parse warehouse operations queries" in system_message:
            return SimpleNamespace(
                content=json.dumps(self._parse(messages[-1]["content"]))
            )
        return SimpleNamespace(
            content=json.dumps(
                {
                    "response_type": "operations_info",
                    "data": {},
                    "natural_language": (
                        "SAP EWM 已完成请求处理，并返回了可追踪的结构化工具结果。"
                        "请根据结果状态继续仓库作业。"
                    ),
                    "recommendations": [],
                    "confidence": 0.9,
                    "actions_taken": [],
                },
                ensure_ascii=False,
            )
        )

    @staticmethod
    def _parse(prompt: str) -> dict[str, Any]:
        order = re.search(r"\b(2\d{9})\b", prompt)
        task = re.search(r"\b(1\d{9})\b", prompt)
        resource = re.search(r"\b(RES\d+)\b", prompt, re.IGNORECASE)
        product = re.search(r"\b(TG\d+)\b", prompt, re.IGNORECASE)
        lowered = prompt.lower()

        if "分配" in prompt or "assign" in lowered:
            return {
                "intent": "sap_order_assignment",
                "entities": {
                    "warehouse_order": order.group(1) if order else "",
                    "resource": resource.group(1).upper() if resource else "",
                },
                "context": {},
            }
        if "确认" in prompt or "confirm" in lowered:
            return {
                "intent": "sap_task_confirmation",
                "entities": {
                    "warehouse_task": task.group(1) if task else "",
                    "warehouse_task_item": "0",
                },
                "context": {},
            }
        if "订单" in prompt or "order" in lowered:
            return {
                "intent": "sap_order_task_query",
                "entities": {"warehouse_order": order.group(1) if order else ""},
                "context": {},
            }
        return {
            "intent": "sap_stock_query",
            "entities": {"product": product.group(1).upper() if product else ""},
            "context": {},
        }


class _AgentWorkflowState(TypedDict, total=False):
    message: str
    session_id: str
    response: dict[str, Any]


@dataclass
class _WorkflowRun:
    context: ApprovalExecutionContext
    config: dict[str, Any]


class SAPAgentWorkflowHarness:
    """Compiled LangGraph harness around the real operations Agent boundary."""

    CHECKPOINT_NS = "sap-ewm-acceptance"

    def __init__(
        self,
        *,
        running_mock: RunningSAPMock,
        config: SAPEWMConfig,
        service: WMSIntegrationService,
        discovery: ToolDiscoveryService,
        agent: MCPOperationsCoordinationAgent,
        repository: InMemoryApprovalRepository,
    ) -> None:
        self.running_mock = running_mock
        self.config = config
        self.service = service
        self.discovery = discovery
        self.agent = agent
        self.repository = repository
        self._runs: dict[UUID, _WorkflowRun] = {}

        workflow = StateGraph(_AgentWorkflowState)
        workflow.add_node("operations_agent", self._run_agent)
        workflow.add_edge(START, "operations_agent")
        workflow.add_edge("operations_agent", END)
        self.graph = workflow.compile(checkpointer=InMemorySaver())

    @classmethod
    async def create(
        cls, running_mock: RunningSAPMock, monkeypatch
    ) -> "SAPAgentWorkflowHarness":
        monkeypatch.setenv("SAP_EWM_EXPOSE_LEGACY_WRITE_TOOLS", "true")
        import src.api.services.mcp.tool_discovery as discovery_module

        config = _live_config(running_mock)
        service = WMSIntegrationService()
        assert await service.add_wms_connection("sap_ewm", config, config.connection_id)
        adapter = SAPEWMMCPAdapter(SAPEWMMCPAdapterConfig(), config, service)
        assert await adapter.initialize()
        discovery = ToolDiscoveryService()
        assert await discovery.register_discovery_source(
            "sap_ewm_tools", adapter, "mcp_adapter"
        )

        repository = InMemoryApprovalRepository()
        gateway = ApprovalGateway(repository_provider=lambda: repository)
        monkeypatch.setattr(discovery_module, "get_approval_gateway", lambda: gateway)

        agent = MCPOperationsCoordinationAgent()
        agent.nim_client = _ScriptedNimClient()
        agent.hybrid_retriever = object()
        agent.operations_tools = object()
        agent.tool_discovery = discovery
        agent.config = load_agent_config("operations")
        return cls(
            running_mock=running_mock,
            config=config,
            service=service,
            discovery=discovery,
            agent=agent,
            repository=repository,
        )

    async def close(self) -> None:
        await self.service.remove_wms_connection(self.config.connection_id)

    async def _run_agent(self, state: _AgentWorkflowState) -> _AgentWorkflowState:
        response = await self.agent.process_query(
            state["message"], session_id=state["session_id"]
        )
        return {"response": asdict(response)}

    async def query(self, message: str) -> dict[str, Any]:
        context, graph_config = self._new_invocation()
        with bind_approval_context(context):
            result = await self.graph.ainvoke(
                {
                    "message": message,
                    "session_id": context.thread_id,
                },
                config=graph_config,
            )
        assert "__interrupt__" not in result
        return result["response"]

    async def start(self, message: str) -> ApprovalInterruptPayload:
        context, graph_config = self._new_invocation()
        with bind_approval_context(context):
            result = await self.graph.ainvoke(
                {
                    "message": message,
                    "session_id": context.thread_id,
                },
                config=graph_config,
            )
        raw_interrupt = result["__interrupt__"][0]
        payload = ApprovalInterruptPayload.model_validate(raw_interrupt.value)
        self._runs[payload.approval_id] = _WorkflowRun(context, graph_config)
        return payload

    async def approve(self, approval_id: UUID) -> dict[str, Any]:
        return await self._resume(approval_id, ApprovalDecision.APPROVE)

    async def reject(
        self, approval_id: UUID, reason: str = "rejected"
    ) -> dict[str, Any]:
        return await self._resume(approval_id, ApprovalDecision.REJECT, reason=reason)

    async def expire(self, approval_id: UUID) -> dict[str, Any]:
        return await self._resume(
            approval_id,
            ApprovalDecision.REJECT,
            reason="approval expired",
            approver_username="system-expiry",
        )

    async def replay(self, approval_id: UUID) -> dict[str, Any]:
        run = self._runs[approval_id]
        snapshot = await self.graph.aget_state(run.config)
        return snapshot.values["response"]

    async def inject_fault(self, **fault: Any) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.running_mock.base_url + "/_mock/faults/next", json=fault
            )
        assert response.status_code == 204

    async def mock_request_count(self, operation: str) -> int:
        async with httpx.AsyncClient() as client:
            response = await client.get(self.running_mock.base_url + "/_mock/requests")
        response.raise_for_status()
        return response.json().get(operation, 0)

    async def _resume(
        self,
        approval_id: UUID,
        decision: ApprovalDecision,
        *,
        reason: str = "verified",
        approver_username: str = "shift-manager",
    ) -> dict[str, Any]:
        run = self._runs[approval_id]
        payload = ApprovalResumePayload(
            approval_id=approval_id,
            decision=decision,
            approver_id=None if approver_username == "system-expiry" else 11,
            approver_username=approver_username,
            reason=reason,
        )
        with bind_approval_context(run.context):
            result = await self.graph.ainvoke(
                Command(resume=payload.model_dump(mode="json")),
                config=run.config,
            )
        return result["response"]

    def _new_invocation(
        self,
    ) -> tuple[ApprovalExecutionContext, dict[str, Any]]:
        request_id = str(uuid4())
        thread_id = f"sap-thread-{uuid4()}"
        context = ApprovalExecutionContext(
            thread_id=thread_id,
            checkpoint_ns=self.CHECKPOINT_NS,
            request_id=request_id,
            requester_id=7,
            requester_username="warehouse-user",
        )
        graph_config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }
        return context, graph_config


@pytest.fixture
async def configured_agent(running_mock, monkeypatch):
    harness = await SAPAgentWorkflowHarness.create(running_mock, monkeypatch)
    try:
        yield harness
    finally:
        await harness.close()


def find_tool_result(response: dict[str, Any], tool_name: str) -> dict[str, Any]:
    for item in (response.get("tool_execution_results") or {}).values():
        if item.get("tool_name") == tool_name:
            return item
    raise AssertionError(f"Tool result not found: {tool_name}")


@pytest.mark.asyncio
async def test_stock_query_full_chain(configured_agent) -> None:
    response = await configured_agent.query("查询 EW01 仓库商品 TG11 的库存")

    call = find_tool_result(response, "sap_ewm_get_physical_stock")
    assert call["result"]["data"]["items"][0]["sku"] == "TG11"
    assert call["result"]["source_system"] == "sap_ewm"
    assert await configured_agent.mock_request_count("get_stock") == 1


@pytest.mark.asyncio
async def test_order_task_query_full_chain(configured_agent) -> None:
    response = await configured_agent.query("查询仓库订单 2000005003 及其任务")

    call = find_tool_result(response, "sap_ewm_list_orders_and_tasks")
    assert call["result"]["data"]["orders"][0]["order_id"] == "2000005003"
    assert call["result"]["data"]["orders"][0]["tasks"][0]["task_id"] == ("1000004703")


@pytest.mark.asyncio
async def test_assignment_requires_approval_and_executes_once(
    configured_agent,
) -> None:
    interrupted = await configured_agent.start("把仓库订单 2000005003 分配给 RES2")
    assert interrupted.tool_name == "sap_ewm_assign_warehouse_order"
    assert await configured_agent.mock_request_count("assign_order") == 0

    completed = await configured_agent.approve(interrupted.approval_id)
    replayed = await configured_agent.replay(interrupted.approval_id)

    call = find_tool_result(completed, "sap_ewm_assign_warehouse_order")
    assert call["result"]["data"]["status"] == "ASSIGNED"
    assert replayed == completed
    assert await configured_agent.mock_request_count("assign_order") == 1


@pytest.mark.asyncio
async def test_task_confirmation_rejection_performs_no_write(
    configured_agent,
) -> None:
    interrupted = await configured_agent.start("确认仓库任务 1000004703")
    assert interrupted.tool_name == "sap_ewm_confirm_warehouse_task"

    rejected = await configured_agent.reject(
        interrupted.approval_id, reason="verification failed"
    )

    call = find_tool_result(rejected, "sap_ewm_confirm_warehouse_task")
    assert call["approval_status"] == "rejected"
    assert await configured_agent.mock_request_count("confirm_task") == 0


@pytest.mark.asyncio
async def test_etag_conflict_requires_new_approval(configured_agent) -> None:
    first = await configured_agent.start("把仓库订单 2000005003 分配给 RES2")
    await configured_agent.inject_fault(operation="assign_order", status_code=412)

    failed = await configured_agent.approve(first.approval_id)
    call = find_tool_result(failed, "sap_ewm_assign_warehouse_order")
    assert call["success"] is False
    assert call["error_code"] == "SAP_ETAG_CONFLICT"

    second = await configured_agent.start("把仓库订单 2000005003 分配给 RES2")
    assert second.approval_id != first.approval_id
    assert await configured_agent.mock_request_count("assign_order") == 1


@pytest.mark.asyncio
async def test_expired_approval_performs_no_write(configured_agent) -> None:
    interrupted = await configured_agent.start("把仓库订单 2000005003 分配给 RES2")

    expired = await configured_agent.expire(interrupted.approval_id)

    call = find_tool_result(expired, "sap_ewm_assign_warehouse_order")
    assert call["approval_status"] == "rejected"
    assert await configured_agent.mock_request_count("assign_order") == 0


@pytest.mark.asyncio
async def test_read_429_retries_then_succeeds(configured_agent) -> None:
    await configured_agent.inject_fault(operation="get_stock", status_code=429)

    response = await configured_agent.query("查询 EW01 仓库商品 TG11 的库存")

    call = find_tool_result(response, "sap_ewm_get_physical_stock")
    assert call["success"] is True
    assert await configured_agent.mock_request_count("get_stock") == 2


@pytest.mark.asyncio
async def test_read_timeout_returns_sap_timeout(running_mock) -> None:
    await _set_fault(running_mock, operation="get_stock", delay_ms=200)
    adapter = SAPEWMAdapter(
        _live_config(
            running_mock,
            read_timeout_seconds=0.05,
            max_read_attempts=1,
        )
    )
    await adapter.connect()
    try:
        with pytest.raises(SAPEWMError) as raised:
            await adapter.get_physical_stock(product="TG11")
    finally:
        await adapter.disconnect()

    assert raised.value.code is SAPEWMErrorCode.SAP_TIMEOUT
    assert await _mock_count(running_mock, "get_stock") == 1


@pytest.mark.asyncio
async def test_apply_then_timeout_is_confirmed_by_readback(running_mock) -> None:
    await _set_fault(
        running_mock,
        operation="assign_order",
        delay_ms=200,
        apply_then_timeout=True,
    )
    adapter = SAPEWMAdapter(_live_config(running_mock, read_timeout_seconds=0.05))
    await adapter.connect()
    try:
        result = await adapter.assign_warehouse_order("2000005003", "RES2")
    finally:
        await adapter.disconnect()

    assert result.status == "ASSIGNED"
    assert result.outcome_confirmed_by_readback is True
    assert await _mock_count(running_mock, "assign_order") == 1
    assert await _mock_count(running_mock, "get_order") == 2


@pytest.mark.asyncio
async def test_unverifiable_write_returns_unknown_outcome(running_mock) -> None:
    await _set_fault(
        running_mock,
        operation="assign_order",
        delay_ms=250,
    )
    adapter = SAPEWMAdapter(_live_config(running_mock, read_timeout_seconds=0.05))
    await adapter.connect()
    try:
        with pytest.raises(SAPEWMError) as raised:
            await adapter.assign_warehouse_order("2000005003", "RES2")
    finally:
        await adapter.disconnect()

    assert raised.value.code is SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN
    assert raised.value.outcome_unknown is True
    assert await _mock_count(running_mock, "assign_order") == 1
    assert await _mock_count(running_mock, "get_order") == 2


async def _set_fault(running_mock: RunningSAPMock, **fault: Any) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            running_mock.base_url + "/_mock/faults/next", json=fault
        )
    assert response.status_code == 204


async def _mock_count(running_mock: RunningSAPMock, operation: str) -> int:
    async with httpx.AsyncClient() as client:
        response = await client.get(running_mock.base_url + "/_mock/requests")
    response.raise_for_status()
    return response.json().get(operation, 0)
