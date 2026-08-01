# WMS Integration Guide

This guide explains how to integrate external WMS systems with the Warehouse Operational Assistant.

## Supported WMS Systems

The repository contains adapters for the following WMS families. Their maturity
is not identical:

- **SAP Extended Warehouse Management (EWM)** — 协议兼容 Mock/可替换型预集成;
  the Agent-to-OData chain is executable locally, but no customer SAP tenant is
  included or claimed as production-connected.
- **Manhattan Associates WMS** — legacy adapter skeleton and tests.
- **Oracle WMS** — legacy adapter skeleton and tests.

## Architecture Overview

The WMS integration system consists of:

1. **Base WMS Adapter** - Common interface for all WMS systems
2. **Specific Adapters** - Implementation for each WMS system
3. **Factory Pattern** - Creates and manages adapter instances
4. **Integration Service** - Unified service for WMS operations
5. **REST API** - HTTP endpoints for WMS operations

The SAP path is:

`Operations Agent -> MCP ToolDiscovery -> SAPEWMMCPAdapter -> WMSIntegrationService -> SAPEWMAdapter -> OData V4`

## SAP EWM Protocol-compatible Pre-integration

This is a replaceable pre-integration. The local Mock follows the SAP OData V4
service paths and protocol behavior used by the adapter: Basic/OAuth2
authentication, CSRF token and session cookie handling, ETag concurrency,
pagination, typed error mapping, bounded read retries, write timeout ambiguity,
and result readback. Replacing the Mock with real SAP requires environment and
field-mapping changes plus SAP-side validation; it does not justify saying the
project is already live on SAP EWM.

### Exposed Agent tools

| MCP tool | Purpose | Approval |
| --- | --- | --- |
| `sap_ewm_get_physical_stock` | Query physical stock by product/bin | No |
| `sap_ewm_list_orders_and_tasks` | Query warehouse orders and tasks | No |
| `sap_ewm_assign_warehouse_order` | Assign an order to an EWM resource | Required |
| `sap_ewm_confirm_warehouse_task` | Confirm an exact warehouse task item | Required |

Write tools pause the compiled LangGraph at `ApprovalGateway`. Rejection and
expiry perform no SAP write. Approval resumes the same checkpoint; the durable
approval action key and stored result prevent a replay from executing the write
twice. A failed ETag comparison returns `SAP_ETAG_CONFLICT`; the user must issue
a new request and obtain a new approval instead of silently overwriting SAP.

### Environment variables

| Variable | Local Mock value | Real SAP guidance |
| --- | --- | --- |
| `SAP_EWM_ENABLED` | `true` | Explicit opt-in only |
| `SAP_EWM_CONNECTION_ID` | `sap-ewm-default` | Stable non-secret identifier |
| `SAP_EWM_MOCK_MODE` | `true` | Set `false` |
| `SAP_EWM_BASE_URL` | `http://sap-ewm-mock:8010` | HTTPS SAP host only |
| `SAP_EWM_WAREHOUSE` | `EW01` | Authorized EWM warehouse number |
| `SAP_EWM_CLIENT` | `100` | SAP client |
| `SAP_EWM_AUTH_MODE` | `basic` | `basic` or `oauth2_client_credentials` |
| `SAP_EWM_USERNAME` / `SAP_EWM_PASSWORD` | Mock credentials | Secret-store values; never commit |
| `SAP_EWM_TOKEN_URL` | unset | Required for OAuth2 |
| `SAP_EWM_CLIENT_ID` / `SAP_EWM_CLIENT_SECRET` | unset | Required for OAuth2; secret-store values |
| `SAP_EWM_SCOPE` | unset | Optional OAuth2 scope |
| `SAP_EWM_VERIFY_TLS` | `false` | Must be `true` |
| `SAP_EWM_CONNECT_TIMEOUT_SECONDS` | `5` | Tune from measured latency |
| `SAP_EWM_READ_TIMEOUT_SECONDS` | `15` | Tune from measured latency |
| `SAP_EWM_MAX_READ_ATTEMPTS` | `3` | Range 1–5; reads only |

Mock-only variables are `SAP_EWM_MOCK_CONTROL_ENABLED`,
`SAP_EWM_MOCK_USERNAME`, `SAP_EWM_MOCK_PASSWORD`,
`SAP_EWM_MOCK_CLIENT_ID`, and `SAP_EWM_MOCK_CLIENT_SECRET`. Never enable Mock
control endpoints on an Internet-facing deployment.

### Start and verify the local chain

From the repository root:

```bash
docker compose -f deploy/compose/docker-compose.dev.yaml up -d sap-ewm-mock backend
curl http://localhost:8010/health
curl -u mock-user:mock-password \
  "http://localhost:8010/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/sap/whsephysicalstockproducts/0001/WarehousePhysicalStockProducts?%24filter=EWMWarehouse%20eq%20%27EW01%27%20and%20Product%20eq%20%27TG11%27"
```

The four intended natural-language examples are:

```text
查询 EW01 仓库商品 TG11 的库存
查询仓库订单 2000005003 及其任务
把仓库订单 2000005003 分配给 RES2
确认仓库任务 1000004703
```

The last two requests return an approval interrupt before the Mock receives a
write. Approve or reject them through the application's approval API/UI.

### Deterministic fault controls

Controls are available only when `SAP_EWM_MOCK_CONTROL_ENABLED=true`:

```bash
# Reset seed data, sessions, faults, and request counters
curl -X POST http://localhost:8010/_mock/reset

# Make the next stock read return HTTP 429; the adapter should retry
curl -X POST http://localhost:8010/_mock/faults/next \
  -H "Content-Type: application/json" \
  -d '{"operation":"get_stock","status_code":429}'

# Apply an assignment, then delay the response long enough to force readback
curl -X POST http://localhost:8010/_mock/faults/next \
  -H "Content-Type: application/json" \
  -d '{"operation":"assign_order","delay_ms":250,"apply_then_timeout":true}'

# Inspect exact operation counts used by acceptance tests
curl http://localhost:8010/_mock/requests
```

Supported fault operation names include `get_stock`, `get_orders`, `get_tasks`,
`get_order`, `get_task`, `assign_order`, and `confirm_task`.

### Stable errors, logs, and metrics

The integration exposes stable error codes: `SAP_AUTH_FAILED`, `SAP_FORBIDDEN`,
`SAP_ENTITY_NOT_FOUND`, `SAP_BUSINESS_CONFLICT`, `SAP_ETAG_CONFLICT`,
`SAP_RATE_LIMITED`, `SAP_UNAVAILABLE`, `SAP_TIMEOUT`, `SAP_OUTCOME_UNKNOWN`, and
`SAP_RESPONSE_INVALID`. Writes are never generically retried. If a write response
is lost, the adapter reads the entity back; it reports success only when the
desired state is observable, otherwise it preserves `SAP_OUTCOME_UNKNOWN`.

Prometheus exports `sap_ewm_requests_total`,
`sap_ewm_request_duration_seconds`, and `sap_ewm_protocol_events_total`.
Labels are fixed operation/result/event categories. URLs, products, orders,
tasks, resources, users, tenants, request IDs, credentials, authorization
headers, cookies, tokens, and raw SAP response bodies are not metric labels or
normal tool output. Logs use correlation IDs and stable error codes; credential
material must remain redacted.

### Real SAP cutover checklist

1. Ask SAP Basis to enable and authorize the exact A2X OData V4 services and
   versions used under `SERVICE_ROOTS`; confirm paths in the target landscape.
2. Provision a least-privilege communication user/arrangement for the authorized
   warehouse, read entities, and only the two required actions.
3. Verify the target's actual entity/action field names against the Mock mapping;
   update only the adapter mapping when the customer release differs.
4. Configure private network routing, proxy rules, DNS, HTTPS certificate trust,
   and `SAP_EWM_VERIFY_TLS=true`. Do not bypass certificate validation.
5. Store Basic/OAuth2 secrets in the deployment secret manager. Set
   `SAP_EWM_MOCK_MODE=false`; do not deploy Mock control endpoints.
6. Validate authentication, pagination next links, CSRF/session behavior, ETag
   handling, 401 refresh, 429/5xx reads, and both actions in SAP QA.
7. Run the four Agent acceptance scenarios with representative authorization
   roles; verify rejected/expired approvals produce zero writes and replay is
   idempotent.
8. Baseline latency/error/unknown-outcome metrics, configure alerts and audit
   retention, document rollback, then obtain business/SAP owner sign-off before
   production enablement.

## Legacy Generic WMS API

The endpoints below belong to the repository's generic WMS API surface. The SAP
Agent path above is configured through `SAP_EWM_*` variables and MCP discovery;
do not pass the obsolete `host/user/warehouse_number` shape to `SAPEWMConfig`.

### 1. Add a WMS Connection

```bash
curl -X POST "http://localhost:8001/api/v1/wms/connections" \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "legacy_wms_main",
    "wms_type": "manhattan",
    "config": {
      "base_url": "https://wms.example.com",
      "username": "WMS_USER",
      "password": "secure_password",
      "facility_id": "FAC001"
    }
  }'
```

### 2. Check Connection Status

```bash
curl "http://localhost:8001/api/v1/wms/connections/legacy_wms_main/status"
```

### 3. Get Inventory

```bash
curl "http://localhost:8001/api/v1/wms/connections/legacy_wms_main/inventory"
```

## Configuration Examples

### SAP EWM Configuration

```python
from src.adapters.wms.sap_ewm_config import SAPEWMConfig

sap_config = SAPEWMConfig(
    enabled=True,
    connection_id="sap-ewm-qa",
    mock_mode=False,
    base_url="https://sap-ewm.company.example",
    warehouse="EW01",
    client="100",
    auth_mode="oauth2_client_credentials",
    token_url="https://identity.company.example/oauth/token",
    client_id="from-secret-manager",
    client_secret="from-secret-manager",
    verify_tls=True,
)
```

### Manhattan WMS Configuration

```python
manhattan_config = {
    "host": "manhattan-wms.company.com",
    "port": 8080,
    "username": "wms_user",
    "password": "secure_password",
    "facility_id": "FAC001",
    "client_id": "CLIENT001",
    "use_ssl": True
}
```

### Oracle WMS Configuration

```python
oracle_config = {
    "host": "oracle-wms.company.com",
    "port": 8000,
    "username": "wms_user",
    "password": "secure_password",
    "organization_id": "ORG001",
    "warehouse_id": "WH001",
    "use_ssl": True
}
```

## API Endpoints

### Connection Management

- `POST /api/v1/wms/connections` - Add WMS connection
- `DELETE /api/v1/wms/connections/{connection_id}` - Remove WMS connection
- `GET /api/v1/wms/connections` - List all connections
- `GET /api/v1/wms/connections/{connection_id}/status` - Get connection status
- `GET /api/v1/wms/connections/status` - Get all connection status

### Inventory Operations

- `GET /api/v1/wms/connections/{connection_id}/inventory` - Get inventory
- `GET /api/v1/wms/inventory/aggregated` - Get aggregated inventory
- `POST /api/v1/wms/sync/inventory` - Sync inventory between systems

### Task Operations

- `GET /api/v1/wms/connections/{connection_id}/tasks` - Get tasks
- `POST /api/v1/wms/connections/{connection_id}/tasks` - Create task
- `PATCH /api/v1/wms/connections/{connection_id}/tasks/{task_id}` - Update task status

### Order Operations

- `GET /api/v1/wms/connections/{connection_id}/orders` - Get orders
- `POST /api/v1/wms/connections/{connection_id}/orders` - Create order

### Location Operations

- `GET /api/v1/wms/connections/{connection_id}/locations` - Get locations

## Data Models

### Inventory Item

```python
{
    "sku": "SKU001",
    "name": "Product Name",
    "quantity": 100,
    "available_quantity": 95,
    "reserved_quantity": 5,
    "location": "A1-B2-C3",
    "zone": "ZONE_A",
    "status": "active"
}
```

### Task

```python
{
    "task_id": "TASK001",
    "task_type": "pick",
    "priority": 1,
    "status": "pending",
    "assigned_to": "worker001",
    "location": "A1-B2-C3",
    "destination": "PACK_STATION_1",
    "notes": "Urgent order"
}
```

### Order

```python
{
    "order_id": "ORDER001",
    "order_type": "sales",
    "status": "pending",
    "priority": 1,
    "customer_id": "CUST001",
    "required_date": "2024-01-15T10:00:00Z"
}
```

## Error Handling

The WMS integration system provides comprehensive error handling:

- **WMSConnectionError** - Connection-related errors
- **WMSDataError** - Data processing errors
- **HTTP 400** - Bad request (invalid parameters)
- **HTTP 404** - Connection not found
- **HTTP 500** - Internal server error

## Monitoring and Logging

All WMS operations are logged for audit purposes:

```python
{
    "adapter": "SAPEWMAdapter",
    "operation": "get_inventory",
    "timestamp": "2024-01-15T10:00:00Z",
    "count": 150
}
```

## Best Practices

### 1. Connection Management

- Use descriptive connection IDs
- Implement connection pooling for high-volume operations
- Monitor connection health regularly
- Handle connection failures gracefully

### 2. Data Synchronization

- Use batch operations for large data sets
- Implement incremental sync for better performance
- Handle data conflicts appropriately
- Validate data before synchronization

### 3. Error Handling

- Implement retry logic for transient failures
- Log all errors with sufficient context
- Provide meaningful error messages to users
- Monitor error rates and patterns

### 4. Security

- Use secure authentication methods
- Encrypt sensitive configuration data
- Implement proper access controls
- Regular security audits

## Troubleshooting

### Common Issues

1. **Connection Timeout**
   - Check network connectivity
   - Verify WMS system availability
   - Adjust timeout settings

2. **Authentication Failures**
   - Verify credentials
   - Check user permissions
   - Ensure proper authentication method

3. **Data Mapping Issues**
   - Verify field mappings
   - Check data formats
   - Validate required fields

### Debug Mode

Enable debug logging for detailed troubleshooting:

```python
import logging
logging.getLogger('adapters.wms').setLevel(logging.DEBUG)
```

## Performance Optimization

### 1. Connection Pooling

```python
# Configure connection pooling
config = {
    "host": "wms.company.com",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
}
```

### 2. Batch Operations

```python
# Process multiple items in batches
batch_size = 100
for i in range(0, len(items), batch_size):
    batch = items[i:i + batch_size]
    await adapter.update_inventory(batch)
```

### 3. Caching

```python
# Implement caching for frequently accessed data
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_location_info(location_id):
    return adapter.get_location(location_id)
```

## Testing

### Unit Tests

```bash
# Run the SAP unit and protocol-contract tests
python -m pytest tests/unit -k sap_ewm -q
python -m pytest tests/contract -k sap_ewm_mock -q
```

### Integration Tests

```bash
# Runs against the local protocol-compatible Mock, not a real SAP tenant
python -m pytest tests/integration/test_sap_ewm_http_integration.py \
  tests/integration/test_sap_ewm_agent_workflow.py -q
```

Real-SAP QA tests require customer-owned connectivity and credentials and must
be run separately after completing the cutover checklist.

## Support

For additional support:

1. Check the API documentation at `/docs`
2. Review the logs for error details
3. Test with the health check endpoint
4. Contact the development team

## Changelog

### Version 1.0.0
- Initial release
- SAP EWM protocol-compatible Mock/replaceable pre-integration; legacy adapter
  surfaces for Manhattan and Oracle WMS
- REST API for WMS operations
- Comprehensive error handling and logging
