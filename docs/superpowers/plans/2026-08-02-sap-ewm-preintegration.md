# SAP EWM Replaceable Pre-integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建基于 SAP 官方 OData V4 契约的 SAP EWM 协议兼容 Mock，并打通 Operations Agent、MCP、WMSIntegrationService、SAPEWMAdapter 到 Mock 的四项业务闭环。

**Architecture:** 独立 FastAPI Mock Server 模拟 SAP Warehouse Physical Stock by Product 与 Warehouse Order and Task A2X API。Agent 只调用四个稳定 MCP Tool；MCP 委托 WMSIntegrationService，SAPEWMAdapter 负责真实 HTTP、认证、CSRF、ETag、分页、重试和结果回查。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、httpx、pytest、pytest-asyncio、LangGraph、项目现有 MCP/ApprovalGateway、Prometheus、Docker Compose。

## Global Constraints

- 只公开 `sap_ewm_get_physical_stock`、`sap_ewm_list_orders_and_tasks`、`sap_ewm_assign_warehouse_order`、`sap_ewm_confirm_warehouse_task` 四个 SAP Tool。
- 只读 Tool 不审批；分配订单和确认任务必须经过现有 ApprovalGateway 与 LangGraph Interrupt。
- Mock 使用内存 Repository、单 Worker 和确定性种子数据；容器重启恢复种子状态是预期行为。
- 目标协议为 SAP OData V4；不得继续使用 `EWM_INVENTORY_SRV`、`InventorySet` 等占位服务。
- 支持 Basic 与 OAuth2 Client Credentials；生产配置默认 `verify_tls=true`，只有 Mock 模式允许 HTTP。
- Agent 不得传入 Base URL、凭证、SAP Client 或任意越权仓库号。
- 写请求禁止通用自动重试；超时后必须回查状态，无法判断时返回 `SAP_OUTCOME_UNKNOWN`。
- ETag 冲突不得覆盖；返回 `SAP_ETAG_CONFLICT` 并要求重新审批。
- 新模块行覆盖率目标不低于 80%。
- 在真实 SAP 非生产环境完成联调前，只能表述为“SAP EWM 可替换型预集成与协议兼容 Mock”。
- 当前项目目录不是独立 Git 仓库；执行任何源码提交前必须建立项目级独立 Git 边界，禁止把源码提交到 `E:\` 的 `student-message` 父仓库。

---

## File Structure

### New production files

- `src/adapters/wms/sap_ewm_config.py`：环境配置、认证模式、TLS 与 URL 校验。
- `src/adapters/wms/sap_ewm_models.py`：库存、订单、任务、分页和写结果领域模型。
- `src/adapters/wms/sap_ewm_errors.py`：标准 SAP 错误码和异常。
- `src/adapters/wms/sap_ewm_http.py`：OData HTTP、认证、CSRF、ETag、分页、重试和同源 Cursor。
- `src/api/services/mcp/adapters/sap_ewm_adapter.py`：四个 SAP MCP Tool 与统一输出。
- `src/api/services/monitoring/sap_ewm_metrics.py`：SAP 请求、重试、冲突和结果未知指标。

### New Mock Server files

- `src/mock_servers/__init__.py`：Mock Server 包。
- `src/mock_servers/sap_ewm/__init__.py`：SAP EWM Mock 包。
- `src/mock_servers/sap_ewm/app.py`：FastAPI 应用工厂、健康检查和 Router 注册。
- `src/mock_servers/sap_ewm/models.py`：Mock 外部协议模型与测试控制模型。
- `src/mock_servers/sap_ewm/repository.py`：种子状态、查询、原子状态变更和 ETag。
- `src/mock_servers/sap_ewm/odata.py`：过滤解析、分页、nextLink、metadata 与错误响应。
- `src/mock_servers/sap_ewm/security.py`：Basic、OAuth2、会话 Cookie 和 CSRF Token。
- `src/mock_servers/sap_ewm/faults.py`：下一请求故障注入。

### Modified production files

- `src/api/services/mcp/server.py`：MCPTool 增加内部风险元数据。
- `src/api/services/mcp/base.py`：ToolConfig 元数据传递到 MCPTool。
- `src/api/services/mcp/tool_discovery.py`：发现时保留 `read_only`、`mutating`、`requires_approval`。
- `src/adapters/wms/sap_ewm.py`：改造成领域映射 Adapter，委托 `SAPEWMODataClient`。
- `src/adapters/wms/factory.py`：允许 SAP 工厂接收校验后的 `SAPEWMConfig`，其他 WMS 仍接收字典。
- `src/adapters/wms/config_examples.py`：替换旧 host/port 配置示例。
- `src/api/services/wms/integration_service.py`：新增四项 SAP 业务方法。
- `src/api/routers/mcp.py`：全局发现服务注册 `sap_ewm_tools`。
- `src/api/agents/operations/mcp_operations_agent.py`：注册、解析并精确选择 SAP Tool。
- `.env.example`：增加安全的 SAP Mock 配置项。
- `deploy/compose/docker-compose.dev.yaml`：增加 `sap-ewm-mock` 并配置 backend。
- `docs/wms-integration.md`：记录启动、演示、错误场景和真实 SAP 切换边界。
- `pyproject.toml`：把项目已使用的 `httpx>=0.27.0` 加入主依赖。

### New tests

- `tests/unit/test_mcp_tool_metadata.py`
- `tests/unit/test_sap_ewm_config.py`
- `tests/unit/test_sap_ewm_http.py`
- `tests/unit/test_sap_ewm_adapter.py`
- `tests/unit/test_sap_ewm_mcp_adapter.py`
- `tests/unit/test_sap_ewm_agent_routing.py`
- `tests/unit/test_sap_ewm_metrics.py`
- `tests/contract/test_sap_ewm_mock_read.py`
- `tests/contract/test_sap_ewm_mock_write.py`
- `tests/integration/test_sap_ewm_http_integration.py`
- `tests/integration/test_sap_ewm_agent_workflow.py`

---

### Task 1: Preserve MCP Tool Risk Metadata

**Files:**
- Modify: `src/api/services/mcp/server.py:51-64`
- Modify: `src/api/services/mcp/base.py:84-95,239-259`
- Modify: `src/api/services/mcp/tool_discovery.py:328-343`
- Create: `tests/unit/test_mcp_tool_metadata.py`

**Interfaces:**
- Consumes: existing `MCPTool`, `ToolConfig`, `DiscoveredTool`, `ApprovalPolicy`.
- Produces: `MCPTool.metadata: dict[str, Any]`; discovery copies metadata into `DiscoveredTool.metadata`.

- [ ] **Step 1: Write failing metadata propagation tests**

```python
@pytest.mark.asyncio
async def test_discovery_preserves_read_only_metadata():
    adapter = FakeAdapter()
    adapter.tools["sap_ewm_get_physical_stock"] = MCPTool(
        name="sap_ewm_get_physical_stock",
        description="Read SAP EWM stock",
        tool_type=MCPToolType.FUNCTION,
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
        metadata={"read_only": True, "requires_approval": False},
    )
    discovery = ToolDiscoveryService()
    await discovery.register_discovery_source("sap_ewm_tools", adapter, "mcp_adapter")
    await discovery.discover_tools_from_source("sap_ewm_tools")
    tool = next(t for t in discovery.discovered_tools.values() if t.name.endswith("physical_stock"))
    assert tool.metadata["read_only"] is True
    assert ApprovalPolicy().requires_approval(tool) is False


@pytest.mark.asyncio
async def test_discovery_preserves_mutating_metadata():
    tool = await discover_fake_tool(
        "sap_ewm_confirm_warehouse_task",
        {"mutating": True, "requires_approval": True},
    )
    assert ApprovalPolicy().requires_approval(tool) is True
```

- [ ] **Step 2: Run the tests and verify the missing field failure**

Run: `python -m pytest tests/unit/test_mcp_tool_metadata.py -q`

Expected: FAIL because `MCPTool.__init__()` does not accept `metadata`.

- [ ] **Step 3: Add metadata to MCPTool and propagate it**

```python
from dataclasses import dataclass, field

@dataclass
class MCPTool:
    name: str
    description: str
    tool_type: MCPToolType
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

In `MCPAdapter.add_tool()` pass `metadata=tool_config.metadata or {}`. In `_discover_from_mcp_adapter()` merge metadata without allowing generated source fields to be overwritten:

```python
metadata={
    **(tool.metadata or {}),
    "tool_type": tool.tool_type.value,
    "adapter_type": adapter.config.adapter_type.value,
    "handler_available": tool.handler is not None,
}
```

- [ ] **Step 4: Run focused and approval-policy tests**

Run: `python -m pytest tests/unit/test_mcp_tool_metadata.py -q`

Expected: PASS; read Tool is not interrupted and mutating Tool is high risk.

- [ ] **Step 5: Commit the metadata boundary**

```bash
git add src/api/services/mcp/server.py src/api/services/mcp/base.py src/api/services/mcp/tool_discovery.py tests/unit/test_mcp_tool_metadata.py
git commit -m "feat: preserve MCP tool risk metadata"
```

---

### Task 2: Define SAP EWM Configuration, Models, and Errors

**Files:**
- Create: `src/adapters/wms/sap_ewm_config.py`
- Create: `src/adapters/wms/sap_ewm_models.py`
- Create: `src/adapters/wms/sap_ewm_errors.py`
- Modify: `src/adapters/wms/config_examples.py:23-33,64-73`
- Modify: `pyproject.toml:22-42`
- Create: `tests/unit/test_sap_ewm_config.py`

**Interfaces:**
- Produces: `SAPEWMConfig.from_env()`, `SAPEWMErrorCode`, `SAPEWMError`, `SAPPage[T]`, `SAPStockItem`, `SAPWarehouseOrder`, `SAPWarehouseTask`, `SAPOrderTaskResult`, `SAPWriteResult`.

- [ ] **Step 1: Write failing configuration and model tests**

```python
def test_real_connection_rejects_http():
    with pytest.raises(ValidationError):
        SAPEWMConfig(
            enabled=True,
            mock_mode=False,
            base_url="http://sap.example.test",
            warehouse="EW01",
            client="100",
            auth_mode="basic",
            username="svc",
            password="secret",
        )


def test_mock_connection_allows_http_and_redacts_secret():
    config = SAPEWMConfig(
        enabled=True,
        mock_mode=True,
        base_url="http://sap-ewm-mock:8010",
        warehouse="EW01",
        client="100",
        auth_mode="basic",
        username="mock-user",
        password="mock-password",
    )
    assert config.password.get_secret_value() == "mock-password"
    assert "mock-password" not in repr(config)


def test_basic_auth_requires_username_and_password():
    with pytest.raises(ValidationError):
        SAPEWMConfig(
            enabled=True,
            mock_mode=True,
            base_url="http://127.0.0.1:8010",
            warehouse="EW01",
            client="100",
            auth_mode="basic",
        )
```

- [ ] **Step 2: Run tests and verify imports fail**

Run: `python -m pytest tests/unit/test_sap_ewm_config.py -q`

Expected: FAIL with `ModuleNotFoundError` for the new SAP modules.

- [ ] **Step 3: Implement typed configuration and errors**

```python
class SAPAuthMode(str, Enum):
    BASIC = "basic"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"


class SAPEWMConfig(BaseModel):
    enabled: bool = False
    connection_id: str = "sap-ewm-default"
    mock_mode: bool = False
    base_url: AnyHttpUrl
    warehouse: str
    client: str = "100"
    auth_mode: SAPAuthMode = SAPAuthMode.BASIC
    username: str | None = None
    password: SecretStr | None = None
    token_url: AnyHttpUrl | None = None
    client_id: str | None = None
    client_secret: SecretStr | None = None
    scope: str | None = None
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    read_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    verify_tls: bool = True
    max_read_attempts: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def validate_security(self) -> "SAPEWMConfig":
        scheme = urlsplit(str(self.base_url)).scheme
        if not self.mock_mode and scheme != "https":
            raise ValueError("Real SAP EWM connections require HTTPS")
        if not self.mock_mode and not self.verify_tls:
            raise ValueError("TLS verification can only be disabled in mock mode")
        if self.auth_mode is SAPAuthMode.BASIC and not (self.username and self.password):
            raise ValueError("Basic auth requires username and password")
        if self.auth_mode is SAPAuthMode.OAUTH2_CLIENT_CREDENTIALS and not (
            self.token_url and self.client_id and self.client_secret
        ):
            raise ValueError("OAuth2 requires token_url, client_id, and client_secret")
        return self

    @classmethod
    def from_env(cls) -> "SAPEWMConfig":
        return cls(
            enabled=os.getenv("SAP_EWM_ENABLED", "false").lower() == "true",
            connection_id=os.getenv("SAP_EWM_CONNECTION_ID", "sap-ewm-default"),
            mock_mode=os.getenv("SAP_EWM_MOCK_MODE", "false").lower() == "true",
            base_url=os.environ["SAP_EWM_BASE_URL"],
            warehouse=os.environ["SAP_EWM_WAREHOUSE"],
            client=os.getenv("SAP_EWM_CLIENT", "100"),
            auth_mode=os.getenv("SAP_EWM_AUTH_MODE", "basic"),
            username=os.getenv("SAP_EWM_USERNAME"),
            password=os.getenv("SAP_EWM_PASSWORD"),
            token_url=os.getenv("SAP_EWM_TOKEN_URL"),
            client_id=os.getenv("SAP_EWM_CLIENT_ID"),
            client_secret=os.getenv("SAP_EWM_CLIENT_SECRET"),
            scope=os.getenv("SAP_EWM_SCOPE"),
            connect_timeout_seconds=float(os.getenv("SAP_EWM_CONNECT_TIMEOUT_SECONDS", "5")),
            read_timeout_seconds=float(os.getenv("SAP_EWM_READ_TIMEOUT_SECONDS", "15")),
            verify_tls=os.getenv("SAP_EWM_VERIFY_TLS", "true").lower() == "true",
        )
```

Define error codes exactly as `SAP_AUTH_FAILED`, `SAP_FORBIDDEN`, `SAP_ENTITY_NOT_FOUND`, `SAP_BUSINESS_CONFLICT`, `SAP_ETAG_CONFLICT`, `SAP_RATE_LIMITED`, `SAP_UNAVAILABLE`, `SAP_TIMEOUT`, `SAP_OUTCOME_UNKNOWN`, and `SAP_RESPONSE_INVALID`.

```python
class SAPEWMError(Exception):
    def __init__(self, code: SAPEWMErrorCode, message: str, *, status_code: int | None = None,
                 retriable: bool = False, outcome_unknown: bool = False):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retriable = retriable
        self.outcome_unknown = outcome_unknown

    @classmethod
    def unknown_outcome(cls, message: str) -> "SAPEWMError":
        return cls(SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN, message, retriable=False, outcome_unknown=True)
```

- [ ] **Step 4: Implement stable domain models**

```python
T = TypeVar("T")

class SAPPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None

class SAPStockItem(BaseModel):
    warehouse: str
    sku: str
    storage_bin: str
    storage_section: str | None = None
    batch: str | None = None
    quantity: Decimal
    unit: str
    stock_item_uuid: str

class SAPWarehouseTask(BaseModel):
    warehouse: str
    task_id: str
    task_item: str
    order_id: str
    status: str
    product: str | None = None
    source_bin: str | None = None
    destination_bin: str | None = None
    executing_resource: str | None = None
    etag: str

class SAPWarehouseOrder(BaseModel):
    warehouse: str
    order_id: str
    status: str
    executing_resource: str | None = None
    etag: str
    tasks: list[SAPWarehouseTask] = Field(default_factory=list)

class SAPOrderTaskResult(BaseModel):
    orders: list[SAPWarehouseOrder]
    next_cursor: str | None = None

class SAPWriteResult(BaseModel):
    operation: str
    entity_id: str
    status: str
    outcome_confirmed_by_readback: bool = False
```

Update the SAP example to use `base_url`, `auth_mode`, `mock_mode`, `client`, `warehouse`, and TLS fields. Add `httpx>=0.27.0` to `pyproject.toml` because production code imports it.

- [ ] **Step 5: Run tests and commit contracts**

Run: `python -m pytest tests/unit/test_sap_ewm_config.py -q`

Expected: PASS.

```bash
git add pyproject.toml src/adapters/wms/sap_ewm_config.py src/adapters/wms/sap_ewm_models.py src/adapters/wms/sap_ewm_errors.py src/adapters/wms/config_examples.py tests/unit/test_sap_ewm_config.py
git commit -m "feat: define SAP EWM contracts and configuration"
```

---

### Task 3: Build the Read-only SAP EWM Mock Contract

**Files:**
- Create: `src/mock_servers/__init__.py`
- Create: `src/mock_servers/sap_ewm/__init__.py`
- Create: `src/mock_servers/sap_ewm/app.py`
- Create: `src/mock_servers/sap_ewm/models.py`
- Create: `src/mock_servers/sap_ewm/repository.py`
- Create: `src/mock_servers/sap_ewm/odata.py`
- Create: `tests/contract/test_sap_ewm_mock_read.py`

**Interfaces:**
- Produces: `create_app(repository: MockRepository | None = None) -> FastAPI`, `MockRepository.reset()`, read endpoints for stock/orders/tasks, minimal OData V4 metadata.

- [ ] **Step 1: Write failing stock and order contract tests**

```python
@pytest.fixture
def mock_client() -> TestClient:
    return TestClient(create_app())


def test_get_stock_uses_odata_v4_shape(mock_client):
    response = mock_client.get(
        STOCK_PATH,
        params={"$filter": "EWMWarehouse eq 'EW01' and Product eq 'TG11'", "$top": "1"},
        auth=("mock-user", "mock-password"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["@odata.context"].endswith("$metadata#WarehousePhysicalStockProducts")
    assert body["value"][0]["Product"] == "TG11"
    assert body["value"][0]["EWMWarehouse"] == "EW01"


def test_get_order_tasks_navigation(mock_client):
    response = mock_client.get(
        ORDER_ROOT + "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')/_WarehouseTask",
        auth=("mock-user", "mock-password"),
    )
    assert response.status_code == 200
    assert response.json()["value"][0]["WarehouseOrder"] == "2000005003"
```

- [ ] **Step 2: Run contract tests and verify the package is missing**

Run: `python -m pytest tests/contract/test_sap_ewm_mock_read.py -q`

Expected: FAIL with import error for `src.mock_servers.sap_ewm.app`.

- [ ] **Step 3: Implement deterministic repository and exact filter parser**

```python
FILTER_TERM = re.compile(r"(?P<field>[A-Za-z][A-Za-z0-9_]*)\s+eq\s+'(?P<value>(?:''|[^'])*)'")

def parse_eq_filter(raw: str | None, allowed: set[str]) -> dict[str, str]:
    if not raw:
        return {}
    filters: dict[str, str] = {}
    for term in re.split(r"\s+and\s+", raw, flags=re.IGNORECASE):
        match = FILTER_TERM.fullmatch(term.strip())
        if not match or match.group("field") not in allowed:
            raise ODataRequestError("INVALID_FILTER", "Unsupported $filter expression", 400)
        filters[match.group("field")] = match.group("value").replace("''", "'")
    return filters
```

Seed `EW01`, products `TG11` and `TG12`, resources `RES1` and `RES2`, orders `2000005003`/`2000005004`, and tasks `1000004703`/`1000004704`. Repository query methods return copies so route serialization cannot mutate stored state.

- [ ] **Step 4: Implement OData read routes, pagination, and metadata**

```python
STOCK_ROOT = "/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/sap/whsephysicalstockproducts/0001"
ORDER_ROOT = "/sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001"

@router.get(STOCK_ROOT + "/WarehousePhysicalStockProducts")
async def list_stock(request: Request, repository: MockRepository = Depends(get_repository)):
    filters = parse_eq_filter(request.query_params.get("$filter"), {"EWMWarehouse", "Product", "EWMStorageBin"})
    page = repository.list_stock(filters, top=parse_top(request), offset=parse_skiptoken(request))
    return odata_collection(request, "WarehousePhysicalStockProducts", page)
```

Expose `$metadata` for both service roots with `application/xml`; include only the entities and properties used by this plan. `odata_collection()` adds `@odata.nextLink` when more rows exist.

- [ ] **Step 5: Run read contract tests and commit**

Run: `python -m pytest tests/contract/test_sap_ewm_mock_read.py -q`

Expected: PASS for stock filtering, order/task navigation, single-task lookup, pagination, malformed filter, and metadata.

```bash
git add src/mock_servers tests/contract/test_sap_ewm_mock_read.py
git commit -m "feat: add SAP EWM read contract mock"
```

---

### Task 4: Add Mock Authentication, CSRF, ETag, Writes, and Faults

**Files:**
- Create: `src/mock_servers/sap_ewm/security.py`
- Create: `src/mock_servers/sap_ewm/faults.py`
- Modify: `src/mock_servers/sap_ewm/app.py`
- Modify: `src/mock_servers/sap_ewm/models.py`
- Modify: `src/mock_servers/sap_ewm/repository.py`
- Create: `tests/contract/test_sap_ewm_mock_write.py`

**Interfaces:**
- Produces: Basic/OAuth validation, `/oauth/token`, CSRF fetch, `If-Match`, AssignWarehouseOrder, ConfirmWarehouseTaskExact, `/_mock/reset`, `/_mock/faults/next`.

- [ ] **Step 1: Write failing write-protocol tests**

```python
def test_assign_requires_csrf_and_etag(mock_client):
    path = ORDER_ROOT + "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')/SAP__self.AssignWarehouseOrder"
    response = mock_client.post(path, json={"EWMResource": "RES2"}, auth=BASIC_AUTH)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_assign_changes_resource_and_etag(mock_client):
    token, cookie = fetch_csrf(mock_client, ORDER_ROOT)
    order = get_order(mock_client, "2000005003")
    response = mock_client.post(
        assign_path("2000005003"),
        json={"EWMResource": "RES2"},
        headers={"X-CSRF-Token": token, "If-Match": order["@odata.etag"]},
        cookies=cookie,
        auth=BASIC_AUTH,
    )
    assert response.status_code == 204
    updated = get_order(mock_client, "2000005003")
    assert updated["ExecutingResource"] == "RES2"
    assert updated["@odata.etag"] != order["@odata.etag"]


def test_confirm_exact_is_idempotently_observable(mock_client):
    response = confirmed_task_request(mock_client, "1000004703", "0")
    assert response.status_code == 204
    assert get_task(mock_client, "1000004703")["WarehouseTaskStatus"] == "C"
```

- [ ] **Step 2: Run write tests and verify 404 failures**

Run: `python -m pytest tests/contract/test_sap_ewm_mock_write.py -q`

Expected: FAIL because write and control routes are not registered.

- [ ] **Step 3: Implement session-bound CSRF and ETag checks**

```python
class MockSecurity:
    def issue_csrf(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(24)
        token = secrets.token_urlsafe(32)
        self._csrf_by_session[session_id] = token
        return session_id, token

    def verify_csrf(self, session_id: str | None, token: str | None) -> None:
        if not session_id or not token or not secrets.compare_digest(self._csrf_by_session.get(session_id, ""), token):
            raise ODataRequestError("CSRF_TOKEN_INVALID", "CSRF token validation failed", 403)
```

Repository mutation methods execute under `asyncio.Lock`, compare `If-Match`, validate state/resource, update entity, increment version, and return the new snapshot. ETag format is `W/\"MOCK-{entity_id}-{version}\"`.

- [ ] **Step 4: Implement OAuth and one-shot fault injection**

```python
class FaultSpec(BaseModel):
    operation: str
    status_code: int | None = None
    delay_ms: int = Field(default=0, ge=0, le=30000)
    apply_then_timeout: bool = False

@control_router.post("/_mock/faults/next", status_code=204)
async def set_next_fault(spec: FaultSpec, faults: FaultController = Depends(get_faults)) -> Response:
    faults.set_next(spec)
    return Response(status_code=204)
```

`POST /oauth/token` accepts form fields `grant_type=client_credentials`, validates configured client ID/secret, and returns a short-lived bearer token. Control routes return `404` unless `SAP_EWM_MOCK_CONTROL_ENABLED=true`.

- [ ] **Step 5: Run all Mock contract tests and commit**

Run: `python -m pytest tests/contract/test_sap_ewm_mock_read.py tests/contract/test_sap_ewm_mock_write.py -q`

Expected: PASS, including `401/403/404/409/412/429/500`, delay, reset, and apply-then-timeout scenarios.

```bash
git add src/mock_servers/sap_ewm tests/contract/test_sap_ewm_mock_write.py
git commit -m "feat: add SAP EWM mock write protocol"
```

---

### Task 5: Implement the Secure OData HTTP Client

**Files:**
- Create: `src/adapters/wms/sap_ewm_http.py`
- Create: `tests/unit/test_sap_ewm_http.py`

**Interfaces:**
- Consumes: `SAPEWMConfig`, `SAPEWMError`.
- Produces: `SAPEWMODataClient.connect()`, `close()`, `get_collection()`, `get_entity()`, `post_action()`, `encode_cursor()`, `decode_cursor()`, `encode_next_link()`, `get_cursor_page()`.

- [ ] **Step 1: Write failing HTTP behavior tests using httpx.MockTransport**

```python
@pytest.mark.asyncio
async def test_get_retries_503_then_succeeds(client_factory):
    responses = iter([httpx.Response(503), httpx.Response(200, json={"value": []})])
    client = client_factory(lambda request: next(responses))
    result = await client.get_collection("stock", "/WarehousePhysicalStockProducts", params={})
    assert result["value"] == []
    assert client.read_attempts == 2


def test_cursor_rejects_other_origin(client):
    cursor = client.encode_cursor("https://evil.example/steal")
    with pytest.raises(SAPEWMError) as error:
        client.decode_cursor(cursor, expected_service="stock")
    assert error.value.code is SAPEWMErrorCode.SAP_RESPONSE_INVALID


@pytest.mark.asyncio
async def test_post_sends_csrf_cookie_and_if_match(client_factory):
    requests = []
    client = client_factory(recording_handler(requests))
    await client.post_action(
        "orders",
        "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')/SAP__self.AssignWarehouseOrder",
        {"EWMResource": "RES2"},
        etag='W/"1"',
    )
    assert requests[-1].headers["X-CSRF-Token"] == "csrf-token"
    assert requests[-1].headers["If-Match"] == 'W/"1"'
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run: `python -m pytest tests/unit/test_sap_ewm_http.py -q`

Expected: FAIL with import error.

- [ ] **Step 3: Implement authentication, bounded reads, and error mapping**

```python
class SAPEWMODataClient:
    SERVICE_ROOTS = {
        "stock": "/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/sap/whsephysicalstockproducts/0001",
        "orders": "/sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001",
    }

    async def get_collection(self, service: str, entity: str, params: dict[str, str],
                             correlation_id: str | None = None) -> dict[str, Any]:
        return await self._request_json(
            "GET", service, entity, params=params, retry_read=True, correlation_id=correlation_id
        )

    async def post_action(self, service: str, path: str, body: dict[str, Any] | None, etag: str,
                          correlation_id: str | None = None) -> None:
        token = await self._csrf_token(service)
        await self._request_json(
            "POST",
            service,
            path,
            json=body,
            headers={"X-CSRF-Token": token, "If-Match": etag},
            expected_status={204},
            retry_read=False,
            correlation_id=correlation_id,
        )
```

Use `httpx.Timeout(connect=config.connect_timeout_seconds, read=config.read_timeout_seconds, write=config.read_timeout_seconds, pool=config.connect_timeout_seconds)`. Basic uses `httpx.BasicAuth`; OAuth caches `access_token` until `expires_at - 30s` and refreshes once after an authentication-expiry response. `_request_json()` generates a UUID when `correlation_id` is absent, sends it as `X-Correlation-ID`, and includes only that ID plus redacted operation/status fields in logs.

- [ ] **Step 4: Implement safe cursor and write-outcome exception**

Encode the absolute `@odata.nextLink` with URL-safe Base64. Decode only after validating scheme, hostname, effective port, and service-root prefix against `SAPEWMConfig.base_url`. Implement `encode_next_link(next_link, expected_service) -> str | None` as the nullable wrapper and `get_cursor_page(cursor, expected_service, correlation_id=None)` as decode-plus-GET. A POST transport timeout raises `SAPEWMError.unknown_outcome("SAP write response was not received")` and is never retried inside the HTTP client.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/unit/test_sap_ewm_http.py -q`

Expected: PASS for Basic, OAuth refresh, CSRF refresh, read retry, Retry-After, error mapping, timeout, and cursor validation.

```bash
git add src/adapters/wms/sap_ewm_http.py tests/unit/test_sap_ewm_http.py
git commit -m "feat: add secure SAP EWM OData client"
```

---

### Task 6: Rewrite SAPEWMAdapter and Verify Real HTTP Integration

**Files:**
- Modify: `src/adapters/wms/sap_ewm.py:35-511`
- Modify: `src/adapters/wms/tests/test_wms_adapters.py:70-133,212-305`
- Create: `tests/unit/test_sap_ewm_adapter.py`
- Create: `tests/integration/test_sap_ewm_http_integration.py`

**Interfaces:**
- Consumes: `SAPEWMODataClient` and Task 2 domain models.
- Produces: `get_physical_stock()`, `list_orders_and_tasks()`, `assign_warehouse_order()`, `confirm_warehouse_task_exact()` plus BaseWMSAdapter compatibility methods.

- [ ] **Step 1: Write failing mapping and write-readback tests**

```python
@pytest.mark.asyncio
async def test_maps_official_stock_fields(client):
    client.get_collection.return_value = {
        "value": [{
            "EWMWarehouse": "EW01", "Product": "TG11", "EWMStorageBin": "T010-02-05-A",
            "EWMStorageSection": "S001", "Batch": "", "EWMStockQuantityInBaseUnit": 956,
            "EWMStockQuantityBaseUnit": "EA", "StockItemUUID": "stock-uuid-1"
        }]
    }
    page = await SAPEWMAdapter(config, client=client).get_physical_stock(product="TG11")
    assert page.items[0].sku == "TG11"
    assert page.items[0].quantity == Decimal("956")


@pytest.mark.asyncio
async def test_assign_timeout_is_confirmed_by_readback(adapter, client):
    client.post_action.side_effect = SAPEWMError.unknown_outcome("timeout")
    client.get_entity.side_effect = [open_order(), assigned_order("RES2")]
    result = await adapter.assign_warehouse_order("2000005003", "RES2")
    assert result.outcome_confirmed_by_readback is True
```

- [ ] **Step 2: Run tests and verify old field assumptions fail**

Run: `python -m pytest tests/unit/test_sap_ewm_adapter.py -q`

Expected: FAIL because the existing adapter uses OData V2 `d.results` and old endpoints.

- [ ] **Step 3: Implement official read mapping**

```python
async def get_physical_stock(self, product=None, storage_bin=None, limit=100, cursor=None,
                             correlation_id=None) -> SAPPage[SAPStockItem]:
    params = {"$filter": build_stock_filter(self.config.warehouse, product, storage_bin), "$top": str(limit)}
    payload = await self.client.get_cursor_page(cursor, "stock", correlation_id) if cursor else await self.client.get_collection(
        "stock", "/WarehousePhysicalStockProducts", params, correlation_id
    )
    return SAPPage(
        items=[SAPStockItem(
            warehouse=row["EWMWarehouse"], sku=row["Product"], storage_bin=row["EWMStorageBin"],
            storage_section=row.get("EWMStorageSection") or None, batch=row.get("Batch") or None,
            quantity=Decimal(str(row["EWMStockQuantityInBaseUnit"])),
            unit=row["EWMStockQuantityBaseUnit"], stock_item_uuid=row["StockItemUUID"],
        ) for row in payload.get("value", [])],
        next_cursor=self.client.encode_next_link(payload.get("@odata.nextLink"), "stock"),
    )
```

Build WarehouseOrder and WarehouseTask models from official properties and include `@odata.etag`. For a specific order, retrieve tasks through `/_WarehouseTask`; for collections, retrieve tasks only for returned orders to keep page bounds deterministic.

- [ ] **Step 4: Implement writes and BaseWMSAdapter compatibility**

`assign_warehouse_order()` and `confirm_warehouse_task_exact()` first GET the entity, call the exact SAP action, then return `SAPWriteResult`. On `SAP_OUTCOME_UNKNOWN`, re-read and compare desired state. Existing abstract methods delegate where semantics match; unsupported create/update operations raise `WMSDataError("Operation is not supported by the SAP EWM pre-integration")` instead of returning success.

- [ ] **Step 5: Add a real TCP integration fixture**

```python
@pytest.fixture
def sap_mock_url(unused_tcp_port):
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=unused_tcp_port, log_level="error")
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    wait_until_ready(f"http://127.0.0.1:{unused_tcp_port}/health")
    yield f"http://127.0.0.1:{unused_tcp_port}"
    server.should_exit = True
    thread.join(timeout=5)
```

Test connect, stock query, pagination, order/task query, assignment, confirmation, ETag conflict, read retry, and apply-then-timeout readback through actual localhost HTTP.

- [ ] **Step 6: Run adapter and HTTP integration tests**

Run: `python -m pytest tests/unit/test_sap_ewm_adapter.py tests/integration/test_sap_ewm_http_integration.py src/adapters/wms/tests/test_wms_adapters.py -q`

Expected: PASS; existing Manhattan and Oracle tests remain unchanged.

- [ ] **Step 7: Commit the adapter rewrite**

```bash
git add src/adapters/wms/sap_ewm.py src/adapters/wms/tests/test_wms_adapters.py tests/unit/test_sap_ewm_adapter.py tests/integration/test_sap_ewm_http_integration.py
git commit -m "feat: implement SAP EWM OData adapter"
```

---

### Task 7: Connect WMSIntegrationService to Four MCP Tools

**Files:**
- Modify: `src/adapters/wms/factory.py:58-97`
- Modify: `src/api/services/wms/integration_service.py:38-683`
- Create: `src/api/services/mcp/adapters/sap_ewm_adapter.py`
- Create: `tests/unit/test_sap_ewm_mcp_adapter.py`

**Interfaces:**
- Consumes: Task 6 SAPEWMAdapter methods.
- Produces: four WMS service methods and `get_sap_ewm_mcp_adapter()` singleton.

- [ ] **Step 1: Write failing service and Tool tests**

```python
@pytest.mark.asyncio
async def test_stock_tool_delegates_to_service(service):
    adapter = SAPEWMMCPAdapter(
        config=mcp_config(),
        sap_config=sap_config(),
        wms_service=service,
        request_id_factory=lambda: "request-1",
    )
    await adapter.initialize()
    result = await adapter.execute_tool("sap_ewm_get_physical_stock", {"product": "TG11", "limit": 10})
    service.get_physical_stock.assert_awaited_once_with(
        "sap-ewm-default", product="TG11", storage_bin=None, limit=10, cursor=None,
        correlation_id="request-1"
    )
    assert result["source_system"] == "sap_ewm"


def test_only_four_tools_are_exposed(adapter):
    assert set(adapter.tools) == {
        "sap_ewm_get_physical_stock", "sap_ewm_list_orders_and_tasks",
        "sap_ewm_assign_warehouse_order", "sap_ewm_confirm_warehouse_task",
    }
```

- [ ] **Step 2: Run tests and verify imports fail**

Run: `python -m pytest tests/unit/test_sap_ewm_mcp_adapter.py -q`

Expected: FAIL because `sap_ewm_adapter.py` does not exist.

- [ ] **Step 3: Add typed WMS service methods**

```python
async def get_physical_stock(self, connection_id: str, *, product: str | None, storage_bin: str | None,
                             limit: int, cursor: str | None, correlation_id: str) -> SAPPage[SAPStockItem]:
    return await self._get_sap_adapter(connection_id).get_physical_stock(
        product, storage_bin, limit, cursor, correlation_id
    )
async def list_orders_and_tasks(self, connection_id: str, *, order_id: str | None, task_status: str | None,
                                resource: str | None, limit: int, cursor: str | None,
                                correlation_id: str) -> SAPOrderTaskResult:
    return await self._get_sap_adapter(connection_id).list_orders_and_tasks(
        order_id, task_status, resource, limit, cursor, correlation_id
    )
async def assign_warehouse_order(self, connection_id: str, warehouse_order: str, resource: str,
                                 correlation_id: str) -> SAPWriteResult:
    return await self._get_sap_adapter(connection_id).assign_warehouse_order(
        warehouse_order, resource, correlation_id
    )
async def confirm_warehouse_task(self, connection_id: str, warehouse_task: str,
                                 warehouse_task_item: str, correlation_id: str) -> SAPWriteResult:
    return await self._get_sap_adapter(connection_id).confirm_warehouse_task_exact(
        warehouse_task, warehouse_task_item, correlation_id
    )
```

Resolve the connection once through a private `_get_sap_adapter(connection_id) -> SAPEWMAdapter`; raise a typed configuration error if the connection is absent or not SAP EWM.

- [ ] **Step 4: Implement Tool schemas and validated handlers**

```python
self.tools["sap_ewm_assign_warehouse_order"] = MCPTool(
    name="sap_ewm_assign_warehouse_order",
    description="Assign an SAP EWM warehouse order to an authorized EWM resource",
    tool_type=MCPToolType.FUNCTION,
    parameters=AssignOrderArgs.model_json_schema(),
    handler=self._assign_order,
    metadata={"read_only": False, "mutating": True, "requires_approval": True},
)
```

Use Pydantic models with `extra="forbid"`, `limit` range 1-100, default task item `"0"`, and non-empty `reason` for both writes. Handler output uses `model_dump(mode="json")` and adds `source_system`, `connection_id`, `warehouse`, `request_id`, and UTC timestamp. It never includes credentials, token, cookie, full URL, or raw exception text.

Define the adapter construction and disabled behavior explicitly:

```python
@dataclass
class SAPEWMMCPAdapterConfig(AdapterConfig):
    name: str = "sap_ewm_tools"
    adapter_type: AdapterType = AdapterType.WMS
    endpoint: str = "local://sap_ewm_tools"

class SAPEWMMCPAdapter(MCPAdapter):
    def __init__(self, config: SAPEWMMCPAdapterConfig, sap_config: SAPEWMConfig,
                 wms_service: WMSIntegrationService, request_id_factory=lambda: str(uuid4())):
        super().__init__(config)
        self.sap_config = sap_config
        self.wms_service = wms_service
        self.request_id_factory = request_id_factory

_sap_ewm_mcp_adapter: SAPEWMMCPAdapter | None = None

async def get_sap_ewm_mcp_adapter() -> SAPEWMMCPAdapter | None:
    global _sap_ewm_mcp_adapter
    sap_config = SAPEWMConfig.from_env()
    if not sap_config.enabled:
        return None
    if _sap_ewm_mcp_adapter is not None:
        return _sap_ewm_mcp_adapter
    adapter = SAPEWMMCPAdapter(SAPEWMMCPAdapterConfig(), sap_config, wms_service)
    if not await adapter.initialize():
        raise SAPEWMError(SAPEWMErrorCode.SAP_UNAVAILABLE, "SAP EWM adapter initialization failed")
    _sap_ewm_mcp_adapter = adapter
    return _sap_ewm_mcp_adapter
```

`initialize()` calls `wms_service.add_wms_connection("sap_ewm", sap_config, sap_config.connection_id)` once, registers the four Tool objects, and connects. Update `WMSAdapterFactory.create_adapter()` and `WMSIntegrationService.add_wms_connection()` annotations to accept `dict[str, Any] | SAPEWMConfig`; `SAPEWMAdapter.__init__()` normalizes a dictionary through `SAPEWMConfig.model_validate()` and otherwise retains the already validated model. Each handler creates one request ID, passes it through the service/Adapter/HTTP client as `correlation_id`, and returns the same ID to the caller.

- [ ] **Step 5: Remove the fixed SAP success path**

Stop registering the legacy `src/api/services/mcp/adapters/wms_adapter.py` as SAP. Replace `_get_inventory_levels()` fixed `ITEM001` response with an explicit unsupported error or delegation to WMSIntegrationService so no reachable SAP handler fabricates success.

- [ ] **Step 6: Run tests and commit**

Run: `python -m pytest tests/unit/test_sap_ewm_mcp_adapter.py -q`

Expected: PASS for schemas, delegation, serialization, input rejection, exactly four tools, and no fixed `ITEM001` result.

```bash
git add src/adapters/wms/factory.py src/api/services/wms/integration_service.py src/api/services/mcp/adapters/sap_ewm_adapter.py src/api/services/mcp/adapters/wms_adapter.py tests/unit/test_sap_ewm_mcp_adapter.py
git commit -m "feat: expose SAP EWM MCP tools"
```

---

### Task 8: Register Tools, Route Operations Intents, and Enforce Approval

**Files:**
- Modify: `src/api/routers/mcp.py:77-125`
- Modify: `src/api/agents/operations/mcp_operations_agent.py:135-159,295-353,356-418,454-557,559-732`
- Create: `tests/unit/test_sap_ewm_agent_routing.py`
- Create: `tests/integration/test_sap_ewm_agent_workflow.py`

**Interfaces:**
- Consumes: `get_sap_ewm_mcp_adapter()` and four Tool names.
- Produces: global/agent discovery source `sap_ewm_tools`; four deterministic operations intents.

- [ ] **Step 1: Write failing discovery, routing, and approval tests**

```python
@pytest.mark.asyncio
async def test_operations_agent_registers_sap_source(agent, monkeypatch):
    monkeypatch.setenv("SAP_EWM_ENABLED", "true")
    await agent._register_mcp_sources()
    assert "sap_ewm_tools" in agent.tool_discovery.discovery_sources


@pytest.mark.parametrize(("intent", "tool_name"), [
    ("sap_stock_query", "sap_ewm_get_physical_stock"),
    ("sap_order_task_query", "sap_ewm_list_orders_and_tasks"),
    ("sap_order_assignment", "sap_ewm_assign_warehouse_order"),
    ("sap_task_confirmation", "sap_ewm_confirm_warehouse_task"),
])
def test_intent_selects_exact_tool(agent, discovered_tools, intent, tool_name):
    query = MCPOperationsQuery(intent=intent, entities={}, context={}, user_query="request")
    plan = agent._create_tool_execution_plan(query, discovered_tools)
    assert [step["tool_name"] for step in plan] == [tool_name]


def test_write_tools_require_approval(discovered_sap_tools):
    policy = ApprovalPolicy()
    assert policy.requires_approval(discovered_sap_tools["sap_ewm_assign_warehouse_order"])
    assert policy.requires_approval(discovered_sap_tools["sap_ewm_confirm_warehouse_task"])
    assert not policy.requires_approval(discovered_sap_tools["sap_ewm_get_physical_stock"])
```

- [ ] **Step 2: Run tests and verify SAP tools are absent**

Run: `python -m pytest tests/unit/test_sap_ewm_agent_routing.py -q`

Expected: FAIL because neither registration path includes `sap_ewm_tools`.

- [ ] **Step 3: Register only when enabled and healthy**

```python
sap_adapter = await get_sap_ewm_mcp_adapter()
if sap_adapter is not None:
    await tool_discovery.register_discovery_source("sap_ewm_tools", sap_adapter, "mcp_adapter")
```

Use the same source name in `src/api/routers/mcp.py` and `MCPOperationsCoordinationAgent._register_mcp_sources()`. If disabled, do not create an empty source; if enabled but initialization fails, log a redacted availability error and leave other tools operational.

- [ ] **Step 4: Add exact intents and entity mapping**

Extend the parser contract with `sap_stock_query`, `sap_order_task_query`, `sap_order_assignment`, and `sap_task_confirmation`. Add a constant map:

```python
SAP_TOOL_BY_INTENT = {
    "sap_stock_query": "sap_ewm_get_physical_stock",
    "sap_order_task_query": "sap_ewm_list_orders_and_tasks",
    "sap_order_assignment": "sap_ewm_assign_warehouse_order",
    "sap_task_confirmation": "sap_ewm_confirm_warehouse_task",
}
```

For these intents, build exactly one execution step. Map `product`, `storage_bin`, `warehouse_order`, `resource`, `warehouse_task`, and `warehouse_task_item`; use `"0"` for a missing task item and the sanitized user query as `reason` for write tools.

- [ ] **Step 5: Verify the approval boundary around actual execution**

In the integration test, inject a recording SAP MCP source and patch the ApprovalGateway with a deterministic fake that records interruption decisions. Assert read calls reach the source immediately; rejection makes zero source calls; approval makes one source call; replay returns the stored result without a second source call. Keep this test independent of a live PostgreSQL server while exercising `ToolDiscoveryService.execute_tool()`.

- [ ] **Step 6: Run affected routing and workflow tests**

Run: `python -m pytest tests/unit/test_sap_ewm_agent_routing.py tests/integration/test_sap_ewm_agent_workflow.py tests/unit/test_mcp_integrated_planner_graph.py -q`

Expected: PASS; existing equipment, operations, safety, forecast, and document routes still initialize.

- [ ] **Step 7: Commit Agent integration**

```bash
git add src/api/routers/mcp.py src/api/agents/operations/mcp_operations_agent.py tests/unit/test_sap_ewm_agent_routing.py tests/integration/test_sap_ewm_agent_workflow.py
git commit -m "feat: route operations agent to SAP EWM tools"
```

---

### Task 9: Add Metrics, Environment Configuration, and Compose Service

**Files:**
- Create: `src/api/services/monitoring/sap_ewm_metrics.py`
- Modify: `src/adapters/wms/sap_ewm_http.py`
- Modify: `.env.example`
- Modify: `deploy/compose/docker-compose.dev.yaml:93-124`
- Create: `tests/unit/test_sap_ewm_metrics.py`

**Interfaces:**
- Produces: `SAPEWMMetrics.observe_request()`, `record_retry()`, `record_csrf_refresh()`, `record_etag_conflict()`, `record_unknown_outcome()`; Compose service at `http://sap-ewm-mock:8010`.

- [ ] **Step 1: Write failing metric tests**

```python
def test_records_redacted_operation_metrics():
    registry = CollectorRegistry()
    metrics = SAPEWMMetrics(registry)
    metrics.observe_request("get_stock", "success", 0.125)
    samples = {sample.name: sample.value for metric in registry.collect() for sample in metric.samples}
    assert samples["sap_ewm_requests_total"] == 1
    assert "base_url" not in metrics.label_names
```

- [ ] **Step 2: Run tests and verify the metrics module is missing**

Run: `python -m pytest tests/unit/test_sap_ewm_metrics.py -q`

Expected: FAIL with import error.

- [ ] **Step 3: Implement bounded-cardinality metrics**

```python
class SAPEWMMetrics:
    def __init__(self, registry: CollectorRegistry = REGISTRY):
        self.requests = Counter("sap_ewm_requests", "SAP EWM requests", ("operation", "result"), registry=registry)
        self.latency = Histogram("sap_ewm_request_duration_seconds", "SAP EWM latency", ("operation",), registry=registry)
        self.events = Counter("sap_ewm_protocol_events", "SAP EWM protocol events", ("event",), registry=registry)

    def observe_request(self, operation: str, result: str, seconds: float) -> None:
        self.requests.labels(operation=operation, result=result).inc()
        self.latency.labels(operation=operation).observe(seconds)
```

Labels may contain only fixed operation/result/event categories; never use product, order, task, resource, URL, user, tenant, or request ID as Prometheus labels.

- [ ] **Step 4: Add safe example environment and Compose wiring**

```yaml
  sap-ewm-mock:
    build:
      context: ../..
      dockerfile: Dockerfile.backend
    command: ["uvicorn", "src.mock_servers.sap_ewm.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
    environment:
      SAP_EWM_MOCK_CONTROL_ENABLED: "true"
      SAP_EWM_MOCK_USERNAME: ${SAP_EWM_USERNAME:-mock-user}
      SAP_EWM_MOCK_PASSWORD: ${SAP_EWM_PASSWORD:-mock-password}
    ports: ["8010:8010"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      interval: 5s
      timeout: 3s
      retries: 20
```

Backend gets `SAP_EWM_ENABLED=true`, `SAP_EWM_MOCK_MODE=true`, `SAP_EWM_BASE_URL=http://sap-ewm-mock:8010`, warehouse `EW01`, client `100`, Basic credentials, and `SAP_EWM_VERIFY_TLS=false`; add `sap-ewm-mock` to backend `depends_on` with healthy condition.

- [ ] **Step 5: Validate metrics and Compose syntax**

Run: `python -m pytest tests/unit/test_sap_ewm_metrics.py -q`

Run: `docker compose -f deploy/compose/docker-compose.dev.yaml config --quiet`

Expected: tests PASS and Compose exits 0 without interpolation or schema errors.

- [ ] **Step 6: Commit deployment wiring**

```bash
git add src/api/services/monitoring/sap_ewm_metrics.py src/adapters/wms/sap_ewm_http.py tests/unit/test_sap_ewm_metrics.py .env.example deploy/compose/docker-compose.dev.yaml
git commit -m "feat: add SAP EWM observability and local service"
```

---

### Task 10: Complete End-to-End Acceptance and Documentation

**Files:**
- Modify: `tests/integration/test_sap_ewm_agent_workflow.py`
- Modify: `docs/wms-integration.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete SAP Mock, Adapter, service, MCP and Agent chain.
- Produces: executable acceptance evidence and truthful operator documentation.

- [ ] **Step 1: Add the four acceptance flows**

```python
def find_tool_result(response: MCPOperationsResponse, tool_name: str) -> dict[str, Any]:
    for item in (response.tool_execution_results or {}).values():
        if item.get("tool_name") == tool_name:
            return item
    raise AssertionError(f"Tool result not found: {tool_name}")


@pytest.mark.asyncio
async def test_stock_query_full_chain(running_mock, configured_agent):
    response = await configured_agent.process_query("查询 EW01 仓库商品 TG11 的库存")
    call = find_tool_result(response, "sap_ewm_get_physical_stock")
    assert call["result"]["data"][0]["sku"] == "TG11"
    assert call["result"]["source_system"] == "sap_ewm"


@pytest.mark.asyncio
async def test_assignment_requires_approval_and_executes_once(approval_workflow):
    interrupted = await approval_workflow.start("把仓库订单 2000005003 分配给 RES2")
    assert interrupted.tool_name == "sap_ewm_assign_warehouse_order"
    assert approval_workflow.mock_request_count("AssignWarehouseOrder") == 0
    completed = await approval_workflow.approve(interrupted.approval_id)
    replayed = await approval_workflow.replay(interrupted.approval_id)
    assert completed.result == replayed.result
    assert approval_workflow.mock_request_count("AssignWarehouseOrder") == 1


@pytest.mark.asyncio
async def test_task_confirmation_rejection_performs_no_write(approval_workflow):
    interrupted = await approval_workflow.start("确认仓库任务 1000004703")
    await approval_workflow.reject(interrupted.approval_id, reason="verification failed")
    assert approval_workflow.mock_request_count("ConfirmWarehouseTaskExact") == 0


@pytest.mark.asyncio
async def test_etag_conflict_requires_new_approval(approval_workflow):
    first = await approval_workflow.start("把仓库订单 2000005003 分配给 RES2")
    await approval_workflow.mutate_order_version("2000005003")
    with pytest.raises(SAPEWMError) as error:
        await approval_workflow.approve(first.approval_id)
    assert error.value.code is SAPEWMErrorCode.SAP_ETAG_CONFLICT
    second = await approval_workflow.start("把仓库订单 2000005003 分配给 RES2")
    assert second.approval_id != first.approval_id
```

Implement the `approval_workflow` fixture in this test module as a thin harness around the compiled LangGraph workflow, its public interrupt/resume commands, and the Mock control endpoints. Its exact interface is `start(message) -> ApprovalInterruptPayload`, `approve(approval_id)`, `reject(approval_id, reason)`, `replay(approval_id)`, `mutate_order_version(order_id)`, and `mock_request_count(operation)`. It must use the real `ApprovalGateway`; only the durable repository is replaced by an in-memory test repository implementing `ensure_pending`, `record_rejection`, `claim_approved_execution`, `mark_executed`, and `mark_failed` with the same `ApprovalRecord` transitions.

Add named tests `test_expired_approval_performs_no_write`, `test_read_429_retries_then_succeeds`, `test_read_timeout_returns_sap_timeout`, `test_apply_then_timeout_is_confirmed_by_readback`, and `test_unverifiable_write_returns_unknown_outcome`. Each test asserts both the standard error/result and the exact Mock request count; none may rely only on log output.

- [ ] **Step 2: Run all SAP-specific tests with coverage**

Run:

```bash
python -m pytest tests/unit/test_mcp_tool_metadata.py tests/unit/test_sap_ewm_config.py tests/unit/test_sap_ewm_http.py tests/unit/test_sap_ewm_adapter.py tests/unit/test_sap_ewm_mcp_adapter.py tests/unit/test_sap_ewm_agent_routing.py tests/unit/test_sap_ewm_metrics.py tests/contract/test_sap_ewm_mock_read.py tests/contract/test_sap_ewm_mock_write.py tests/integration/test_sap_ewm_http_integration.py tests/integration/test_sap_ewm_agent_workflow.py --cov=src.adapters.wms --cov=src.mock_servers.sap_ewm --cov=src.api.services.mcp.adapters.sap_ewm_adapter --cov-report=term-missing --cov-fail-under=80
```

Expected: all selected tests PASS and coverage command exits 0 at 80% or higher.

- [ ] **Step 3: Run affected regression suites**

Run:

```bash
python -m pytest src/adapters/wms/tests/test_wms_adapters.py tests/unit/test_mcp_system.py tests/unit/test_mcp_integrated_planner_graph.py tests/integration/test_mcp_agent_workflows.py -q
```

Expected: PASS. If a pre-existing unrelated test fails, record its exact test ID and failure output; do not weaken assertions or hide the failure.

- [ ] **Step 4: Run local Compose smoke test**

Run:

```bash
docker compose -f deploy/compose/docker-compose.dev.yaml up -d sap-ewm-mock
curl -u mock-user:mock-password "http://localhost:8010/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/sap/whsephysicalstockproducts/0001/WarehousePhysicalStockProducts?%24filter=EWMWarehouse%20eq%20%27EW01%27%20and%20Product%20eq%20%27TG11%27"
docker compose -f deploy/compose/docker-compose.dev.yaml stop sap-ewm-mock
```

Expected: health is ready, curl returns product `TG11`, and stop preserves other Compose services.

- [ ] **Step 5: Update operator and interview documentation**

Document exact environment variables, startup commands, four natural-language examples, approval behavior, fault-control requests, standard errors, log redaction, and real-SAP cutover checklist. README wording must say “协议兼容 Mock/可替换型预集成” and must not say “已真实上线接入 SAP EWM”.

- [ ] **Step 6: Commit acceptance evidence**

```bash
git add tests/integration/test_sap_ewm_agent_workflow.py docs/wms-integration.md README.md
git commit -m "test: verify SAP EWM agent workflow"
```

- [ ] **Step 7: Perform final repository verification**

Run: `git status --short`

Expected: only user-owned pre-existing changes remain; no generated secrets, `.env`, coverage database, test cache, or Mock state files are staged.
