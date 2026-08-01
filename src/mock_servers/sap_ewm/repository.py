"""Deterministic in-memory repository for the SAP EWM mock."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from .models import OrderRecord, StockRecord, TaskRecord


class MockRepository:
    """Own seeded state and return copies at every read boundary."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.resources = {"RES1", "RES2"}
        self.stock = [
            StockRecord(
                warehouse="EW01",
                product="TG11",
                storage_bin="T010-02-05-A",
                storage_section="S001",
                batch="",
                quantity=Decimal("956"),
                unit="EA",
                stock_item_uuid="stock-uuid-1",
            ),
            StockRecord(
                warehouse="EW01",
                product="TG11",
                storage_bin="T010-02-05-B",
                storage_section="S001",
                batch="BATCH-01",
                quantity=Decimal("44"),
                unit="EA",
                stock_item_uuid="stock-uuid-2",
            ),
            StockRecord(
                warehouse="EW01",
                product="TG12",
                storage_bin="T020-01-01-A",
                storage_section="S002",
                batch="",
                quantity=Decimal("125"),
                unit="EA",
                stock_item_uuid="stock-uuid-3",
            ),
        ]
        self.orders = {
            ("EW01", "2000005003"): OrderRecord(
                warehouse="EW01",
                order_id="2000005003",
                status="O",
                executing_resource="RES1",
            ),
            ("EW01", "2000005004"): OrderRecord(
                warehouse="EW01",
                order_id="2000005004",
                status="O",
                executing_resource=None,
            ),
        }
        self.tasks = {
            ("EW01", "1000004703", "0"): TaskRecord(
                warehouse="EW01",
                task_id="1000004703",
                task_item="0",
                order_id="2000005003",
                status="O",
                product="TG11",
                source_bin="T010-02-05-A",
                destination_bin="GI-DOOR-01",
                executing_resource="RES1",
            ),
            ("EW01", "1000004704", "0"): TaskRecord(
                warehouse="EW01",
                task_id="1000004704",
                task_item="0",
                order_id="2000005004",
                status="O",
                product="TG12",
                source_bin="T020-01-01-A",
                destination_bin="GI-DOOR-02",
                executing_resource=None,
            ),
        }

    def list_stock(self, filters: dict[str, str]) -> list[dict[str, object]]:
        rows = [record.to_odata() for record in self.stock]
        return deepcopy(_matching(rows, filters))

    def list_orders(self, filters: dict[str, str]) -> list[dict[str, object]]:
        rows = [record.to_odata() for record in self.orders.values()]
        return deepcopy(_matching(rows, filters))

    def get_order(
        self, warehouse: str, order_id: str
    ) -> dict[str, object] | None:
        record = self.orders.get((warehouse, order_id))
        return deepcopy(record.to_odata()) if record else None

    def list_tasks(self, filters: dict[str, str]) -> list[dict[str, object]]:
        rows = [record.to_odata() for record in self.tasks.values()]
        return deepcopy(_matching(rows, filters))

    def list_order_tasks(
        self, warehouse: str, order_id: str
    ) -> list[dict[str, object]]:
        return self.list_tasks(
            {"EWMWarehouse": warehouse, "WarehouseOrder": order_id}
        )

    def get_task(
        self, warehouse: str, task_id: str, task_item: str
    ) -> dict[str, object] | None:
        record = self.tasks.get((warehouse, task_id, task_item))
        return deepcopy(record.to_odata()) if record else None


def _matching(
    rows: list[dict[str, object]], filters: dict[str, str]
) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if all(str(row.get(field, "")) == value for field, value in filters.items())
    ]
