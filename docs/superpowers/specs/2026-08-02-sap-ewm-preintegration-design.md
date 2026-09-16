# SAP EWM 可替换型预集成设计

- 日期：2026-08-02
- 状态：设计已确认，等待书面规格复核
- 适用项目：Multi-Agent Intelligent Warehouse

## 1. 背景

项目已经包含 WMS 抽象、`SAPEWMAdapter`、`WMSIntegrationService` 和通用 WMS MCP Adapter，但当前实现尚不能代表真实 SAP EWM 接入：

- `SAPEWMAdapter` 使用 `EWM_INVENTORY_SRV`、`InventorySet` 等通用占位服务和实体名称，没有对齐 SAP 官方 OData V4 A2X API。
- RFC 分支未实现，本期也没有 RFC 接入需求。
- 通用 WMS MCP Adapter 的 SAP 连接和 Tool Handler 仍返回固定数据，没有委托给 `WMSIntegrationService`。
- WMS MCP Adapter 尚未进入主 MCP 注册链路和 Operations Agent 的工具发现链路。
- SAP 写操作缺少 CSRF Token、ETag、结果未知回查等真实协议处理。
- 当前没有可访问的 SAP EWM 测试环境。

本设计通过独立、协议兼容的 SAP EWM Mock Server 完成 Agent 到 OData 服务的真实 HTTP 全链路。以后获得真实 SAP 环境时，保持 Agent 和 MCP Tool Schema 不变，通过连接配置及有限字段映射切换到真实系统。

## 2. 目标

首期实现以下四项能力：

1. 查询 Warehouse Physical Stock by Product。
2. 查询 Warehouse Order 及其 Warehouse Task。
3. 人工审批后将 Warehouse Order 分配给 EWM Resource。
4. 人工审批后通过 `ConfirmWarehouseTaskExact` 确认 Warehouse Task。

首期完成标准为“可替换型预集成”：Mock 遵循目标 SAP OData V4 路径和关键响应语义，覆盖认证、CSRF Token、ETag、分页、标准错误和超时；Agent、MCP、Integration Service 和 SAP Adapter 之间使用稳定接口。

## 3. 非目标

本期不实现：

- RFC 或 `pyrfc` 接入。
- 盘点单创建、盘点计数和差异过账。
- 库存调整、计划外发料和库存转储。
- 入库单、出库单或 Warehouse Task 创建。
- 带数量差异、批次变化、异常码、序列号或库位变化的任务确认。
- SAP 系统角色配置、企业网络打通和真实 SAP 联调验收。
- 生产级 SAP 高可用、灾备或跨数据中心部署。

## 4. 方案选择

采用独立 SAP EWM Mock 微服务，不采用进程内 HTTP Mock，也不新增绕过 WMS Integration Service 的独立远程 MCP Server。

选择独立 Mock 服务的原因：

- 能验证真实 HTTP、容器网络、认证、Header、分页和错误处理。
- `SAPEWMAdapter` 对 Mock 和真实 SAP 使用同一客户端代码。
- Mock 可独立重置数据和注入故障，适合契约测试与面试演示。
- 保留项目已有 WMS 抽象，避免 Agent 与 SAP 协议直接耦合。

## 5. 总体架构

```text
用户
  -> LangGraph Planner/Router
  -> Operations Agent
  -> ToolDiscoveryService
  -> SAP EWM MCP Adapter
  -> WMSIntegrationService
  -> SAPEWMAdapter
  -> SAP EWM Mock Server
```

职责边界：

### 5.1 SAP EWM Mock Server

独立 FastAPI 服务，模拟本期使用的 SAP OData V4 服务组、实体、动作、Header、分页和错误格式。Mock 只承担外部 SAP 系统角色，不包含 Agent、审批或 MCP 逻辑。

建议代码边界为 `src/mock_servers/sap_ewm/`，并通过开发 Docker Compose 的 `sap-ewm-mock` 服务启动。测试控制接口仅在 Mock 模式启用。

### 5.2 SAPEWMAdapter

作为唯一 SAP HTTP/OData 客户端，负责：

- Base URL、SAP Client 和认证配置。
- OData 查询构造、转义和分页。
- SAP 字段到内部领域模型的映射。
- CSRF Token 获取、缓存和失效刷新。
- ETag 读取与 `If-Match` 写入。
- 超时、受限重试、错误标准化和写后状态回查。

Agent 和 MCP 层不得直接拼装 SAP URL 或 Header。

### 5.3 WMSIntegrationService

负责连接生命周期和面向业务的统一方法。它根据 `connection_id` 找到已初始化的 WMS Adapter，并提供库存查询、订单与任务查询、订单分配、任务确认能力。

### 5.4 SAP EWM MCP Adapter

MCP 层只负责 Tool 定义、Pydantic/JSON Schema 参数校验、调用 `WMSIntegrationService` 和返回值标准化。它不保存 SAP 凭证，不生成 CSRF Token，也不直接发送 HTTP 请求。

为避免继续暴露通用 WMS Adapter 中未实现的工具，本期注册专用 `sap_ewm_tools` Discovery Source，只公开四个已经完成端到端实现的 Tool。原通用 WMS 固定数据 Handler 不再作为 SAP 能力暴露，并移除 `ITEM001` 固定成功响应。

### 5.5 Operations Agent

Operations Agent 注册 `sap_ewm_tools`，将库存、订单和任务查询视为只读操作，将订单分配与任务确认标记为有副作用的高风险操作。LLM 只负责选择 Tool 和生成业务参数，执行权属于应用程序。

## 6. SAP OData V4 契约

目标契约依据 SAP S/4HANA EWM A2X OData V4 API：

- Warehouse Physical Stock by Product：
  `https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/5aadd5aa0ed541e49b1e006d7e17919b/68b18afb9d6d4c0083242919d1a88315.html`
- Warehouse Order and Task：
  `https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/5aadd5aa0ed541e49b1e006d7e17919b/de6f70f9c74d414a93af3c3825005772.html`
- Assign Warehouse Order：
  `https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/5aadd5aa0ed541e49b1e006d7e17919b/202d3898930c4ab6a15de77eb4b06422.html`
- Confirm Warehouse Task Exact：
  `https://help.sap.com/docs/sap_s4hana_cloud/c46da892efa14cea8347e9b872199d6f/8dddf948573246cf8e4ded175d0c2b59.html`

### 6.1 库存查询

```http
GET /sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/sap/whsephysicalstockproducts/0001/WarehousePhysicalStockProducts
```

支持本期需要的 `$filter`、`$top` 和 `$skiptoken`。允许按 `EWMWarehouse`、`Product` 和 `EWMStorageBin` 过滤。响应包含 `@odata.context`、`value` 和可选 `@odata.nextLink`。

主要字段映射：

| SAP 字段 | 内部字段 |
| --- | --- |
| `EWMWarehouse` | `warehouse` |
| `Product` | `sku` |
| `EWMStorageBin` | `location` |
| `EWMStorageSection` | `zone` |
| `Batch` | `lot_number` |
| `EWMStockQuantityInBaseUnit` | `quantity` |
| `EWMStockQuantityBaseUnit` | `unit` |
| `StockItemUUID` | `source_entity_id` |

### 6.2 订单和任务查询

```http
GET /sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder
GET /sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder(EWMWarehouse='{warehouse}',WarehouseOrder='{order}')/_WarehouseTask
GET /sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseTask(EWMWarehouse='{warehouse}',WarehouseTask='{task}',WarehouseTaskItem='{item}')
```

查询结果保留 SAP 订单号、任务号、任务项、状态、执行资源、源库位、目标库位、产品、目标数量、实际数量、单位、创建时间、确认时间及 ETag。

### 6.3 分配仓库订单

```http
POST /sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder(EWMWarehouse='{warehouse}',WarehouseOrder='{order}')/SAP__self.AssignWarehouseOrder
X-CSRF-Token: {token}
If-Match: {etag}
Content-Type: application/json

{"EWMResource": "RES2"}
```

成功返回 `204 No Content`。目标 Resource 必须存在并与用户关系满足 Mock 业务规则；已被其他资源占用或状态不允许分配时返回业务冲突。

### 6.4 确认仓库任务

```http
POST /sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseTask(EWMWarehouse='{warehouse}',WarehouseTask='{task}',WarehouseTaskItem='{item}')/SAP__self.ConfirmWarehouseTaskExact
X-CSRF-Token: {token}
If-Match: {etag}
```

成功返回 `204 No Content`。首期只允许无业务字段变更的精确确认。任务必须存在、未确认，并满足订单分配或配置允许的直接确认规则。

## 7. MCP Tool 契约

| Tool | 业务参数 | 审批 |
| --- | --- | --- |
| `sap_ewm_get_physical_stock` | `product?`, `storage_bin?`, `limit?`, `cursor?` | 否 |
| `sap_ewm_list_orders_and_tasks` | `order_id?`, `task_status?`, `resource?`, `limit?`, `cursor?` | 否 |
| `sap_ewm_assign_warehouse_order` | `warehouse_order`, `resource`, `reason` | 是 |
| `sap_ewm_confirm_warehouse_task` | `warehouse_task`, `warehouse_task_item`, `reason` | 是 |

`connection_id`、`EWMWarehouse` 和 `sap-client` 根据认证用户、租户配置和授权仓库在服务端解析。LLM 不得传入 SAP 地址、凭证或任意仓库号。

查询 Tool 标准返回：

```json
{
  "success": true,
  "source_system": "sap_ewm",
  "connection_id": "sap-ewm-default",
  "warehouse": "EW01",
  "data": [],
  "pagination": {"next_cursor": null},
  "request_id": "correlation-id",
  "retrieved_at": "ISO-8601 timestamp"
}
```

写 Tool 额外返回操作对象、最终状态和 `outcome_confirmed_by_readback`。原始 SAP Token、Cookie、完整 URL 和敏感 Header 不进入 Tool 结果。

## 8. Mock 状态模型

Mock 使用 Repository 接口与内存实现，种子数据包含：

- 仓库 `EW01`。
- 多个商品、批次、库位和 Stock Item UUID。
- 资源 `RES1`、`RES2` 及用户关系。
- Open、In Process、Completed 三类 Warehouse Order。
- Open 和 Confirmed Warehouse Task。
- 每个可变订单和任务的单调递增版本号。

ETag 由实体标识和版本号稳定生成。写操作在单 Worker 内通过异步锁原子检查 ETag、业务前置条件和状态更新。容器重启后恢复种子状态是预期行为，不把 Mock 当作生产数据库。

仅在 `SAP_EWM_MOCK_CONTROL_ENABLED=true` 时启用测试控制接口，用于：

- 重置种子数据。
- 设置下一次请求返回认证失败、限流、服务错误或延迟。
- 模拟 POST 已落地但客户端收到超时。
- 模拟并发修改造成 ETag 冲突。

控制接口不属于 SAP 契约，真实 SAP Adapter 不调用它。

## 9. 认证、CSRF、ETag 和分页

### 9.1 认证

Adapter 支持：

- `basic`：用户名与密码。
- `oauth2_client_credentials`：Token URL、Client ID、Client Secret 和可选 Scope。

Mock 必须验证 Basic Auth，并提供用于自动化测试的简化 OAuth2 Client Credentials Token Endpoint。认证实现通过策略接口封装，业务请求代码不区分 Token 来源。

### 9.2 CSRF Token

写操作前，Adapter 对对应服务根执行带 `X-CSRF-Token: Fetch` 的读取请求。Token 与会话 Cookie 一起缓存。若 SAP 明确返回 Token 校验失败，刷新 Token 后只重放尚未被服务端接受的请求一次。

### 9.3 ETag

分配订单和确认任务前，Adapter 读取目标实体的最新 ETag，并通过 `If-Match` 提交。`412` 不自动覆盖或重试；返回 `SAP_ETAG_CONFLICT`，重新读取业务状态并要求发起新的审批。

### 9.4 分页

Adapter 将 `@odata.nextLink` 转换为服务端签名或编码的不透明 Cursor。恢复 Cursor 时验证目标 URL 与配置的 SAP Origin、服务组和实体一致，拒绝跨主机或跨服务跳转。

## 10. 人工审批与幂等

沿用现有 `ApprovalPolicy`、`ApprovalGateway`、PostgreSQL Approval Repository、LangGraph Interrupt 和 Checkpoint：

1. Agent 生成 Tool 和业务参数。
2. `ApprovalPolicy` 根据 Tool 元数据将两个写 Tool 判定为高风险。
3. `ApprovalGateway` 持久化待审批记录和幂等键，并触发 Interrupt。
4. 审批界面显示连接、仓库、订单或任务、目标资源、当前状态、操作原因和风险说明。
5. 拒绝、过期或审批上下文缺失时不调用 SAP。
6. 批准后原子认领执行权，再调用 `WMSIntegrationService`。
7. 执行结果持久化；工作流重放时返回已保存结果，不重复调用 SAP。

SAP 动作本身不接收客户端幂等键，因此对写请求采用状态回查：

- 明确未发送或明确业务拒绝：返回失败。
- 超时后回查发现目标状态已经达成：返回成功，并设置 `outcome_confirmed_by_readback=true`。
- 超时后回查发现状态未变化：返回失败，不自动重发。
- 回查也失败或状态无法判断：返回 `SAP_OUTCOME_UNKNOWN`，要求人工检查，禁止 Agent 自动重试。

## 11. 错误与重试

统一错误码：

| 情况 | 标准错误码 | 处理 |
| --- | --- | --- |
| `401` | `SAP_AUTH_FAILED` | 不重试普通请求；OAuth Token 失效可刷新一次 |
| `403` | `SAP_FORBIDDEN` | CSRF 明确失效时刷新一次，否则不重试 |
| `404` | `SAP_ENTITY_NOT_FOUND` | 不重试 |
| `409` | `SAP_BUSINESS_CONFLICT` | 返回最新业务状态 |
| `412` | `SAP_ETAG_CONFLICT` | 不覆盖，重新审批 |
| `429` | `SAP_RATE_LIMITED` | 只读请求遵循 `Retry-After` |
| `5xx` | `SAP_UNAVAILABLE` | 只读请求受限重试 |
| 网络超时 | `SAP_TIMEOUT` 或 `SAP_OUTCOME_UNKNOWN` | 写操作执行回查 |
| 响应无法解析 | `SAP_RESPONSE_INVALID` | 记录脱敏摘要，不重试写操作 |

只读请求对网络错误、`429` 和可恢复 `5xx` 最多尝试三次，采用带抖动的指数退避。写操作不使用通用自动重试。

## 12. 配置与安全

配置项包括：

- `SAP_EWM_ENABLED`
- `SAP_EWM_CONNECTION_ID`
- `SAP_EWM_BASE_URL`
- `SAP_EWM_WAREHOUSE`
- `SAP_EWM_CLIENT`
- `SAP_EWM_AUTH_MODE`
- `SAP_EWM_USERNAME` / `SAP_EWM_PASSWORD`
- `SAP_EWM_TOKEN_URL` / `SAP_EWM_CLIENT_ID` / `SAP_EWM_CLIENT_SECRET` / `SAP_EWM_SCOPE`
- `SAP_EWM_CONNECT_TIMEOUT_SECONDS`
- `SAP_EWM_READ_TIMEOUT_SECONDS`
- `SAP_EWM_VERIFY_TLS`

安全规则：

- 生产配置默认 `verify_tls=true`；仅显式 Mock 模式允许 HTTP。
- 凭证使用 Secret 类型和部署环境密钥注入，不写入源码、配置示例真实值或日志。
- 日志隐藏 Authorization、Token、Cookie、密码、Client Secret 和查询中的敏感标识。
- Base URL 与 Token URL 经过协议和 Host Allowlist 校验，防止 LLM 参数造成 SSRF。
- Agent 无权修改连接配置。
- Run ID、Tool Call ID、Approval ID 和 SAP Request ID 贯通日志、Metrics 和审计记录。

## 13. 可观测性

记录以下 Metrics 和结构化事件：

- SAP 请求数、成功率和延迟，按操作和标准结果分类。
- 只读重试次数、限流次数、Token 刷新次数和 ETag 冲突次数。
- 写操作审批、批准、拒绝、过期、执行成功、回查确认和结果未知数量。
- Tool 发现、选择、执行和标准化错误。

日志只记录脱敏后的服务标识、实体 ID、状态码、错误码、耗时和关联 ID，不记录响应中的非必要业务明细。

## 14. 测试策略

### 14.1 单元测试

- OData 字符串转义和过滤构造。
- SAP 响应到内部领域模型的字段映射。
- Cursor 编解码及同源校验。
- 错误码映射和可重试判定。
- ETag、CSRF Token 缓存和失效逻辑。
- Tool 参数 Schema 和输出标准化。

### 14.2 Mock 契约测试

- `$metadata` 返回可解析的 OData V4 XML。
- Basic 与 OAuth2 成功和失败。
- 库存、订单、任务查询和分页。
- 分配订单与确认任务的 `204` 语义和状态更新。
- 缺少或错误 CSRF Token。
- 缺少、过期或错误 ETag。
- `401`、`403`、`404`、`409`、`412`、`429`、`5xx` 和延迟注入。

### 14.3 Adapter 集成测试

使用真实 HTTP 启动 Mock Server，验证 `SAPEWMAdapter` 的认证、查询、分页、写操作和回查，不用 monkeypatch 代替网络链路。

### 14.4 MCP 与 Agent 工作流测试

- 两个查询 Tool 不触发审批。
- 两个写 Tool 必须产生 Interrupt。
- 拒绝或过期后 Mock 请求计数保持不变。
- 批准后只执行一次。
- Checkpoint 恢复和重复批准不重复写入。
- ETag 冲突要求新审批。
- 写超时后通过状态回查确定成功或返回结果未知。

## 15. 验收标准

1. 开发 Compose 能同时启动 API 和 `sap-ewm-mock`，健康检查通过。
2. 用户询问“查询 EW01 仓库商品 TG11 的库存”时，Agent 调用 SAP 库存 Tool，返回 Mock 当前数据、来源和查询时间。
3. 用户要求“把仓库订单 2000005003 分配给 RES2”时，工作流暂停审批；批准后 Mock 订单状态与资源发生变化。
4. 用户要求“确认任务 1000004703”时，工作流暂停审批；批准后任务状态和确认时间发生变化。
5. 拒绝、审批过期、工作流恢复或重复批准不会造成 SAP 写操作重复执行。
6. 认证失败、CSRF 失败、ETag 冲突、限流、服务错误、读取超时和写结果未知均有确定的测试和标准错误结果。
7. 主 Agent 工具发现链路只暴露四个已完成能力，不把占位 WMS Tool 宣称为真实 SAP 能力。
8. MCP Handler 不再返回固定 `ITEM001` 成功数据。
9. 所有新增单元、契约、集成和工作流测试通过；新模块行覆盖率目标不低于 80%。
10. 切换到真实 SAP 时不修改 Agent Prompt、Tool 名称和 Tool Schema，只更换配置并根据真实系统元数据调整必要字段映射。

## 16. 真实 SAP 切换边界

获得真实 SAP 环境后必须完成以下外部验收，才能在简历或面试中表述为“真实接入 SAP EWM”：

1. 确认 SAP S/4HANA/EWM 版本以及两个 A2X API 的可用性。
2. 在 SAP 中启用对应 OData V4 Service Group，并配置通信用户和业务授权。
3. 获得非生产 Base URL、SAP Client、Warehouse Number 和认证方式。
4. 对照真实 `$metadata` 校准属性、状态码和扩展字段。
5. 完成证书信任、企业网络、防火墙和代理配置。
6. 在真实非生产环境执行四项业务的只读与受控写入联调。
7. 保存脱敏的测试证据、审计记录和回滚说明。

在完成上述真实环境验收之前，准确表述应为“基于 SAP 官方 OData V4 契约构建可替换型 SAP EWM 预集成与协议兼容 Mock”，而不是“已上线接入 SAP EWM”。
