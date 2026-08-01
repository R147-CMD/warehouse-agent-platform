"""Stable domain models for the SAP EWM pre-integration."""

from __future__ import annotations

from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


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
