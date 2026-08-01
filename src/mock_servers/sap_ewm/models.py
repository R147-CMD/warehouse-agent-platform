"""Deterministic in-memory records used by the SAP EWM mock."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


def _odata_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


@dataclass
class StockRecord:
    warehouse: str
    product: str
    storage_bin: str
    storage_section: str
    batch: str
    quantity: Decimal
    unit: str
    stock_item_uuid: str

    def to_odata(self) -> dict[str, object]:
        return {
            "EWMWarehouse": self.warehouse,
            "Product": self.product,
            "EWMStorageBin": self.storage_bin,
            "EWMStorageSection": self.storage_section,
            "Batch": self.batch,
            "EWMStockQuantityInBaseUnit": _odata_number(self.quantity),
            "EWMStockQuantityBaseUnit": self.unit,
            "StockItemUUID": self.stock_item_uuid,
        }


@dataclass
class OrderRecord:
    warehouse: str
    order_id: str
    status: str
    executing_resource: str | None
    version: int = 1

    @property
    def etag(self) -> str:
        return f'W/"MOCK-{self.order_id}-{self.version}"'

    def to_odata(self) -> dict[str, object]:
        return {
            "@odata.etag": self.etag,
            "EWMWarehouse": self.warehouse,
            "WarehouseOrder": self.order_id,
            "WarehouseOrderStatus": self.status,
            "ExecutingResource": self.executing_resource or "",
        }


@dataclass
class TaskRecord:
    warehouse: str
    task_id: str
    task_item: str
    order_id: str
    status: str
    product: str
    source_bin: str
    destination_bin: str
    executing_resource: str | None
    version: int = 1

    @property
    def etag(self) -> str:
        return f'W/"MOCK-{self.task_id}-{self.task_item}-{self.version}"'

    def to_odata(self) -> dict[str, object]:
        return {
            "@odata.etag": self.etag,
            "EWMWarehouse": self.warehouse,
            "WarehouseTask": self.task_id,
            "WarehouseTaskItem": self.task_item,
            "WarehouseOrder": self.order_id,
            "WarehouseTaskStatus": self.status,
            "Product": self.product,
            "SourceStorageBin": self.source_bin,
            "DestinationStorageBin": self.destination_bin,
            "ExecutingResource": self.executing_resource or "",
        }
