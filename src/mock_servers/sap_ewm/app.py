"""FastAPI application exposing a SAP EWM OData V4 compatible mock."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import Response

from .odata import (
    ODataRequestError,
    entity_not_found,
    odata_collection,
    odata_error_response,
    parse_eq_filter,
    parse_skiptoken,
    parse_top,
)
from .repository import MockRepository


STOCK_ROOT = (
    "/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/"
    "sap/whsephysicalstockproducts/0001"
)
ORDER_ROOT = (
    "/sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/"
    "sap/warehouseorder/0001"
)

METADATA_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="SAP.EWM.Mock" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="WarehousePhysicalStockProduct">
        <Key><PropertyRef Name="StockItemUUID" /></Key>
        <Property Name="EWMWarehouse" Type="Edm.String" Nullable="false" />
        <Property Name="Product" Type="Edm.String" Nullable="false" />
        <Property Name="EWMStorageBin" Type="Edm.String" Nullable="false" />
        <Property Name="EWMStorageSection" Type="Edm.String" />
        <Property Name="Batch" Type="Edm.String" />
        <Property Name="EWMStockQuantityInBaseUnit" Type="Edm.Decimal" />
        <Property Name="EWMStockQuantityBaseUnit" Type="Edm.String" />
        <Property Name="StockItemUUID" Type="Edm.String" Nullable="false" />
      </EntityType>
      <EntityType Name="WarehouseOrder">
        <Key>
          <PropertyRef Name="EWMWarehouse" />
          <PropertyRef Name="WarehouseOrder" />
        </Key>
        <Property Name="EWMWarehouse" Type="Edm.String" Nullable="false" />
        <Property Name="WarehouseOrder" Type="Edm.String" Nullable="false" />
        <Property Name="WarehouseOrderStatus" Type="Edm.String" />
        <Property Name="ExecutingResource" Type="Edm.String" />
      </EntityType>
      <EntityType Name="WarehouseTask">
        <Key>
          <PropertyRef Name="EWMWarehouse" />
          <PropertyRef Name="WarehouseTask" />
          <PropertyRef Name="WarehouseTaskItem" />
        </Key>
        <Property Name="EWMWarehouse" Type="Edm.String" Nullable="false" />
        <Property Name="WarehouseTask" Type="Edm.String" Nullable="false" />
        <Property Name="WarehouseTaskItem" Type="Edm.String" Nullable="false" />
        <Property Name="WarehouseOrder" Type="Edm.String" />
        <Property Name="WarehouseTaskStatus" Type="Edm.String" />
        <Property Name="Product" Type="Edm.String" />
        <Property Name="SourceStorageBin" Type="Edm.String" />
        <Property Name="DestinationStorageBin" Type="Edm.String" />
        <Property Name="ExecutingResource" Type="Edm.String" />
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="WarehousePhysicalStockProducts" EntityType="SAP.EWM.Mock.WarehousePhysicalStockProduct" />
        <EntitySet Name="WarehouseOrder" EntityType="SAP.EWM.Mock.WarehouseOrder" />
        <EntitySet Name="WarehouseTask" EntityType="SAP.EWM.Mock.WarehouseTask" />
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""


def create_app(repository: MockRepository | None = None) -> FastAPI:
    app = FastAPI(title="SAP EWM Protocol-compatible Mock", version="1.0.0")
    app.state.repository = repository or MockRepository()

    @app.exception_handler(ODataRequestError)
    async def handle_odata_error(
        _request: Request, error: ODataRequestError
    ):
        return odata_error_response(error)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "sap-ewm-mock"}

    @app.get(STOCK_ROOT + "/$metadata")
    @app.get(ORDER_ROOT + "/$metadata")
    async def metadata() -> Response:
        return Response(METADATA_XML, media_type="application/xml")

    @app.get(STOCK_ROOT + "/WarehousePhysicalStockProducts")
    async def list_stock(request: Request) -> dict[str, object]:
        filters = parse_eq_filter(
            request.query_params.get("$filter"),
            {"EWMWarehouse", "Product", "EWMStorageBin"},
        )
        return odata_collection(
            request,
            service_root=STOCK_ROOT,
            entity_set="WarehousePhysicalStockProducts",
            rows=_repository(request).list_stock(filters),
            top=parse_top(request),
            offset=parse_skiptoken(request),
        )

    @app.get(ORDER_ROOT + "/WarehouseOrder")
    async def list_orders(request: Request) -> dict[str, object]:
        filters = parse_eq_filter(
            request.query_params.get("$filter"),
            {"EWMWarehouse", "WarehouseOrder", "WarehouseOrderStatus", "ExecutingResource"},
        )
        return odata_collection(
            request,
            service_root=ORDER_ROOT,
            entity_set="WarehouseOrder",
            rows=_repository(request).list_orders(filters),
            top=parse_top(request),
            offset=parse_skiptoken(request),
        )

    @app.get(ORDER_ROOT + "/WarehouseTask")
    async def list_tasks(request: Request) -> dict[str, object]:
        filters = parse_eq_filter(
            request.query_params.get("$filter"),
            {
                "EWMWarehouse",
                "WarehouseOrder",
                "WarehouseTask",
                "WarehouseTaskItem",
                "WarehouseTaskStatus",
                "ExecutingResource",
            },
        )
        return odata_collection(
            request,
            service_root=ORDER_ROOT,
            entity_set="WarehouseTask",
            rows=_repository(request).list_tasks(filters),
            top=parse_top(request),
            offset=parse_skiptoken(request),
        )

    order_key = (
        ORDER_ROOT
        + "/WarehouseOrder(EWMWarehouse='{warehouse}',WarehouseOrder='{order_id}')"
    )
    task_key = (
        ORDER_ROOT
        + "/WarehouseTask(EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',"
        "WarehouseTaskItem='{task_item}')"
    )

    @app.get(order_key + "/_WarehouseTask")
    async def list_order_tasks(
        request: Request, warehouse: str, order_id: str
    ) -> dict[str, object]:
        if _repository(request).get_order(warehouse, order_id) is None:
            raise entity_not_found("WarehouseOrder")
        return odata_collection(
            request,
            service_root=ORDER_ROOT,
            entity_set="WarehouseTask",
            rows=_repository(request).list_order_tasks(warehouse, order_id),
            top=parse_top(request),
            offset=parse_skiptoken(request),
        )

    @app.get(order_key)
    async def get_order(
        request: Request, warehouse: str, order_id: str
    ) -> dict[str, object]:
        order = _repository(request).get_order(warehouse, order_id)
        if order is None:
            raise entity_not_found("WarehouseOrder")
        return order

    @app.get(task_key)
    async def get_task(
        request: Request, warehouse: str, task_id: str, task_item: str
    ) -> dict[str, object]:
        task = _repository(request).get_task(warehouse, task_id, task_item)
        if task is None:
            raise entity_not_found("WarehouseTask")
        return task

    return app


def _repository(request: Request) -> MockRepository:
    return request.app.state.repository


app = create_app()
