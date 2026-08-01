"""SAP EWM OData V4 domain adapter.

The adapter maps official SAP fields into stable warehouse-domain models. HTTP,
authentication, CSRF, ETag, pagination, and retry behavior remain isolated in
``SAPEWMODataClient``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .base import (
    BaseWMSAdapter,
    InventoryItem,
    Location,
    Order,
    Task,
    TaskStatus,
    TaskType,
    WMSConnectionError,
    WMSDataError,
)
from .sap_ewm_config import SAPEWMConfig
from .sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from .sap_ewm_http import SAPEWMODataClient
from .sap_ewm_models import (
    SAPOrderTaskResult,
    SAPPage,
    SAPStockItem,
    SAPWarehouseOrder,
    SAPWarehouseTask,
    SAPWriteResult,
)


class SAPEWMAdapter(BaseWMSAdapter):
    """Map SAP EWM OData V4 entities to stable domain contracts."""

    def __init__(
        self,
        config: dict[str, Any] | SAPEWMConfig,
        *,
        client: SAPEWMODataClient | None = None,
    ) -> None:
        self.sap_config = (
            config
            if isinstance(config, SAPEWMConfig)
            else SAPEWMConfig.model_validate(config)
        )
        super().__init__(self.sap_config.model_dump(mode="python"))
        self.client = client or SAPEWMODataClient(self.sap_config)

    async def connect(self) -> bool:
        try:
            self.connected = await self.client.connect()
            return self.connected
        except SAPEWMError as exc:
            self.connected = False
            raise WMSConnectionError("SAP EWM connection failed") from exc

    async def disconnect(self) -> bool:
        try:
            await self.client.close()
            self.connected = False
            return True
        except Exception:
            self.connected = False
            return False

    async def get_physical_stock(
        self,
        product: str | None = None,
        storage_bin: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
        correlation_id: str | None = None,
    ) -> SAPPage[SAPStockItem]:
        self._require_connected()
        _validate_limit(limit)
        if cursor:
            payload = await self.client.get_cursor_page(cursor, "stock", correlation_id)
        else:
            filters = [f"EWMWarehouse eq {_odata_literal(self.sap_config.warehouse)}"]
            if product:
                filters.append(f"Product eq {_odata_literal(product)}")
            if storage_bin:
                filters.append(f"EWMStorageBin eq {_odata_literal(storage_bin)}")
            payload = await self.client.get_collection(
                "stock",
                "/WarehousePhysicalStockProducts",
                {"$filter": " and ".join(filters), "$top": str(limit)},
                correlation_id,
            )

        items = [self._map_stock(row) for row in _collection_rows(payload)]
        return SAPPage(
            items=items,
            next_cursor=self.client.encode_next_link(
                payload.get("@odata.nextLink"), "stock"
            ),
        )

    async def list_orders_and_tasks(
        self,
        order_id: str | None = None,
        task_status: str | None = None,
        resource: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
        correlation_id: str | None = None,
    ) -> SAPOrderTaskResult:
        self._require_connected()
        _validate_limit(limit)

        if order_id:
            order_rows = [await self._get_order_entity(order_id, correlation_id)]
            next_cursor = None
        elif cursor:
            payload = await self.client.get_cursor_page(
                cursor, "orders", correlation_id
            )
            order_rows = _collection_rows(payload)
            next_cursor = self.client.encode_next_link(
                payload.get("@odata.nextLink"), "orders"
            )
        else:
            filters = [f"EWMWarehouse eq {_odata_literal(self.sap_config.warehouse)}"]
            if resource:
                filters.append(f"ExecutingResource eq {_odata_literal(resource)}")
            payload = await self.client.get_collection(
                "orders",
                "/WarehouseOrder",
                {"$filter": " and ".join(filters), "$top": str(limit)},
                correlation_id,
            )
            order_rows = _collection_rows(payload)
            next_cursor = self.client.encode_next_link(
                payload.get("@odata.nextLink"), "orders"
            )

        orders: list[SAPWarehouseOrder] = []
        for row in order_rows:
            mapped_order = self._map_order(row)
            task_filters: list[str] = []
            if task_status:
                task_filters.append(
                    f"WarehouseTaskStatus eq {_odata_literal(task_status)}"
                )
            if resource:
                task_filters.append(f"ExecutingResource eq {_odata_literal(resource)}")
            task_params = {"$top": "100"}
            if task_filters:
                task_params["$filter"] = " and ".join(task_filters)
                task_params = {
                    "$filter": task_params["$filter"],
                    "$top": "100",
                }
            task_payload = await self.client.get_collection(
                "orders",
                self._order_path(mapped_order.order_id) + "/_WarehouseTask",
                task_params,
                correlation_id,
            )
            mapped_order.tasks = [
                self._map_task(task) for task in _collection_rows(task_payload)
            ]
            orders.append(mapped_order)

        return SAPOrderTaskResult(orders=orders, next_cursor=next_cursor)

    async def assign_warehouse_order(
        self,
        warehouse_order: str,
        resource: str,
        correlation_id: str | None = None,
    ) -> SAPWriteResult:
        self._require_connected()
        order = await self._get_order_entity(warehouse_order, correlation_id)
        if (order.get("ExecutingResource") or None) == resource:
            return SAPWriteResult(
                operation="assign_warehouse_order",
                entity_id=warehouse_order,
                status="ASSIGNED",
                outcome_confirmed_by_readback=True,
            )

        try:
            await self.client.post_action(
                "orders",
                self._order_path(warehouse_order) + "/SAP__self.AssignWarehouseOrder",
                {"EWMResource": resource},
                _etag(order),
                correlation_id,
            )
        except SAPEWMError as exc:
            if exc.code is not SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN:
                raise
            try:
                current = await self._get_order_entity(warehouse_order, correlation_id)
            except SAPEWMError as readback_error:
                raise SAPEWMError.unknown_outcome(
                    "SAP warehouse order assignment could not be verified"
                ) from readback_error
            if (current.get("ExecutingResource") or None) != resource:
                raise
            return SAPWriteResult(
                operation="assign_warehouse_order",
                entity_id=warehouse_order,
                status="ASSIGNED",
                outcome_confirmed_by_readback=True,
            )

        return SAPWriteResult(
            operation="assign_warehouse_order",
            entity_id=warehouse_order,
            status="ASSIGNED",
        )

    async def confirm_warehouse_task_exact(
        self,
        warehouse_task: str,
        warehouse_task_item: str = "0",
        correlation_id: str | None = None,
    ) -> SAPWriteResult:
        self._require_connected()
        task = await self._get_task_entity(
            warehouse_task, warehouse_task_item, correlation_id
        )
        if task.get("WarehouseTaskStatus") == "C":
            return SAPWriteResult(
                operation="confirm_warehouse_task_exact",
                entity_id=warehouse_task,
                status="CONFIRMED",
                outcome_confirmed_by_readback=True,
            )

        try:
            await self.client.post_action(
                "orders",
                self._task_path(warehouse_task, warehouse_task_item)
                + "/SAP__self.ConfirmWarehouseTaskExact",
                {},
                _etag(task),
                correlation_id,
            )
        except SAPEWMError as exc:
            if exc.code is not SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN:
                raise
            try:
                current = await self._get_task_entity(
                    warehouse_task, warehouse_task_item, correlation_id
                )
            except SAPEWMError as readback_error:
                raise SAPEWMError.unknown_outcome(
                    "SAP warehouse task confirmation could not be verified"
                ) from readback_error
            if current.get("WarehouseTaskStatus") != "C":
                raise
            return SAPWriteResult(
                operation="confirm_warehouse_task_exact",
                entity_id=warehouse_task,
                status="CONFIRMED",
                outcome_confirmed_by_readback=True,
            )

        return SAPWriteResult(
            operation="confirm_warehouse_task_exact",
            entity_id=warehouse_task,
            status="CONFIRMED",
        )

    async def get_inventory(
        self, location: str | None = None, sku: str | None = None
    ) -> list[InventoryItem]:
        page = await self.get_physical_stock(
            product=sku, storage_bin=location, limit=100
        )
        return [
            InventoryItem(
                sku=item.sku,
                name=item.sku,
                quantity=int(item.quantity),
                available_quantity=int(item.quantity),
                reserved_quantity=0,
                location=item.storage_bin,
                zone=item.storage_section,
                lot_number=item.batch,
                status="active",
            )
            for item in page.items
        ]

    async def update_inventory(self, items: list[InventoryItem]) -> bool:
        raise _unsupported("Inventory adjustment")

    async def get_tasks(
        self,
        status: TaskStatus | None = None,
        assigned_to: str | None = None,
    ) -> list[Task]:
        task_status = self._map_task_status_to_sap(status) if status else None
        result = await self.list_orders_and_tasks(
            task_status=task_status,
            resource=assigned_to,
            limit=100,
        )
        return [
            Task(
                task_id=task.task_id,
                task_type=TaskType.PICK,
                status=self._map_sap_task_status(task.status),
                assigned_to=task.executing_resource,
                location=task.source_bin,
                destination=task.destination_bin,
                items=[{"sku": task.product}] if task.product else [],
            )
            for order in result.orders
            for task in order.tasks
        ]

    async def create_task(self, task: Task) -> str:
        raise _unsupported("Warehouse task creation")

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        notes: str | None = None,
    ) -> bool:
        if status is not TaskStatus.COMPLETED:
            raise _unsupported("Warehouse task status update")
        await self.confirm_warehouse_task_exact(task_id, "0")
        return True

    async def get_orders(
        self, status: str | None = None, order_type: str | None = None
    ) -> list[Order]:
        if order_type:
            raise _unsupported("Warehouse order type filtering")
        result = await self.list_orders_and_tasks(limit=100)
        orders = [
            Order(
                order_id=order.order_id,
                order_type="WAREHOUSE",
                status=order.status,
                items=[{"task_id": task.task_id} for task in order.tasks],
            )
            for order in result.orders
        ]
        if status:
            return [order for order in orders if order.status == status]
        return orders

    async def create_order(self, order: Order) -> str:
        raise _unsupported("Warehouse order creation")

    async def get_locations(
        self, zone: str | None = None, location_type: str | None = None
    ) -> list[Location]:
        if location_type and location_type != "storage":
            return []
        page = await self.get_physical_stock(limit=100)
        locations: dict[str, Location] = {}
        for item in page.items:
            if zone and item.storage_section != zone:
                continue
            locations.setdefault(
                item.storage_bin,
                Location(
                    location_id=item.storage_bin,
                    name=item.storage_bin,
                    zone=item.storage_section or "",
                    location_type="storage",
                ),
            )
        return list(locations.values())

    async def get_system_status(self) -> dict[str, Any]:
        if not self.connected:
            return {"status": "disconnected", "connected": False}
        try:
            await self.get_physical_stock(limit=1)
        except SAPEWMError:
            return {
                "status": "error",
                "connected": False,
                "warehouse": self.sap_config.warehouse,
            }
        return {
            "status": "connected",
            "connected": True,
            "warehouse": self.sap_config.warehouse,
            "mock_mode": self.sap_config.mock_mode,
            "auth_mode": self.sap_config.auth_mode.value,
        }

    def _map_stock(self, row: dict[str, Any]) -> SAPStockItem:
        try:
            return SAPStockItem(
                warehouse=str(row["EWMWarehouse"]),
                sku=str(row["Product"]),
                storage_bin=str(row["EWMStorageBin"]),
                storage_section=str(row.get("EWMStorageSection") or "") or None,
                batch=str(row.get("Batch") or "") or None,
                quantity=Decimal(str(row["EWMStockQuantityInBaseUnit"])),
                unit=str(row["EWMStockQuantityBaseUnit"]),
                stock_item_uuid=str(row["StockItemUUID"]),
            )
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise _invalid_response("physical stock") from exc

    def _map_order(self, row: dict[str, Any]) -> SAPWarehouseOrder:
        try:
            return SAPWarehouseOrder(
                warehouse=str(row["EWMWarehouse"]),
                order_id=str(row["WarehouseOrder"]),
                status=str(row["WarehouseOrderStatus"]),
                executing_resource=(str(row.get("ExecutingResource") or "") or None),
                etag=_etag(row),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid_response("warehouse order") from exc

    def _map_task(self, row: dict[str, Any]) -> SAPWarehouseTask:
        try:
            return SAPWarehouseTask(
                warehouse=str(row["EWMWarehouse"]),
                task_id=str(row["WarehouseTask"]),
                task_item=str(row["WarehouseTaskItem"]),
                order_id=str(row["WarehouseOrder"]),
                status=str(row["WarehouseTaskStatus"]),
                product=str(row.get("Product") or "") or None,
                source_bin=str(row.get("SourceStorageBin") or "") or None,
                destination_bin=(str(row.get("DestinationStorageBin") or "") or None),
                executing_resource=(str(row.get("ExecutingResource") or "") or None),
                etag=_etag(row),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid_response("warehouse task") from exc

    async def _get_order_entity(
        self, order_id: str, correlation_id: str | None
    ) -> dict[str, Any]:
        return await self.client.get_entity(
            "orders", self._order_path(order_id), correlation_id
        )

    async def _get_task_entity(
        self,
        task_id: str,
        task_item: str,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        return await self.client.get_entity(
            "orders", self._task_path(task_id, task_item), correlation_id
        )

    def _order_path(self, order_id: str) -> str:
        return (
            "/WarehouseOrder(EWMWarehouse="
            f"{_odata_literal(self.sap_config.warehouse)},WarehouseOrder="
            f"{_odata_literal(order_id)})"
        )

    def _task_path(self, task_id: str, task_item: str) -> str:
        return (
            "/WarehouseTask(EWMWarehouse="
            f"{_odata_literal(self.sap_config.warehouse)},WarehouseTask="
            f"{_odata_literal(task_id)},WarehouseTaskItem="
            f"{_odata_literal(task_item)})"
        )

    def _require_connected(self) -> None:
        if not self.connected:
            raise WMSConnectionError("Not connected to SAP EWM")

    def _map_task_status_to_sap(self, status: TaskStatus) -> str:
        return {
            TaskStatus.PENDING: "P",
            TaskStatus.IN_PROGRESS: "I",
            TaskStatus.COMPLETED: "C",
            TaskStatus.FAILED: "F",
            TaskStatus.CANCELLED: "X",
        }.get(status, "P")

    def _map_sap_task_status(self, sap_status: str) -> TaskStatus:
        return {
            "O": TaskStatus.PENDING,
            "P": TaskStatus.PENDING,
            "I": TaskStatus.IN_PROGRESS,
            "C": TaskStatus.COMPLETED,
            "F": TaskStatus.FAILED,
            "X": TaskStatus.CANCELLED,
        }.get(sap_status, TaskStatus.PENDING)

    def _map_task_type_to_sap(self, task_type: TaskType) -> str:
        return {
            TaskType.PICK: "PICK",
            TaskType.PACK: "PACK",
            TaskType.SHIP: "SHIP",
            TaskType.RECEIVE: "RECEIVE",
            TaskType.PUTAWAY: "PUTAWAY",
            TaskType.CYCLE_COUNT: "COUNT",
            TaskType.TRANSFER: "TRANSFER",
        }.get(task_type, "PICK")

    def _map_sap_task_type(self, sap_task_type: str) -> TaskType:
        return {
            "PICK": TaskType.PICK,
            "PACK": TaskType.PACK,
            "SHIP": TaskType.SHIP,
            "RECEIVE": TaskType.RECEIVE,
            "PUTAWAY": TaskType.PUTAWAY,
            "COUNT": TaskType.CYCLE_COUNT,
            "TRANSFER": TaskType.TRANSFER,
        }.get(sap_task_type, TaskType.PICK)


def _collection_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("value")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise _invalid_response("collection")
    return rows


def _etag(row: dict[str, Any]) -> str:
    etag = row.get("@odata.etag")
    if not isinstance(etag, str) or not etag:
        raise _invalid_response("ETag")
    return etag


def _odata_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")


def _unsupported(operation: str) -> WMSDataError:
    return WMSDataError(f"{operation} is not supported by the SAP EWM pre-integration")


def _invalid_response(entity: str) -> SAPEWMError:
    return SAPEWMError(
        SAPEWMErrorCode.SAP_RESPONSE_INVALID,
        f"SAP returned an invalid {entity} response",
    )
