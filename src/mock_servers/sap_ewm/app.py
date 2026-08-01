"""FastAPI application exposing a SAP EWM OData V4 compatible mock."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import Response

from .faults import FaultController, FaultSpec
from .models import AssignOrderPayload
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
from .security import MockSecurity, SESSION_COOKIE


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


def create_app(
    repository: MockRepository | None = None,
    *,
    control_enabled: bool | None = None,
) -> FastAPI:
    app = FastAPI(title="SAP EWM Protocol-compatible Mock", version="1.0.0")
    app.state.repository = repository or MockRepository()
    app.state.security = MockSecurity()
    app.state.faults = FaultController()
    controls_are_enabled = (
        _env_bool("SAP_EWM_MOCK_CONTROL_ENABLED", False)
        if control_enabled is None
        else control_enabled
    )

    @app.exception_handler(ODataRequestError)
    async def handle_odata_error(
        _request: Request, error: ODataRequestError
    ):
        return odata_error_response(error)

    @app.middleware("http")
    async def enforce_sap_security(request: Request, call_next):
        if not request.url.path.startswith("/sap/opu/odata4/"):
            return await call_next(request)

        try:
            _security(request).authenticate(request)
        except ODataRequestError as error:
            response = odata_error_response(error)
            response.headers["WWW-Authenticate"] = 'Basic realm="SAP EWM Mock"'
            return response

        response = await call_next(request)
        if (
            request.method == "GET"
            and request.headers.get("X-CSRF-Token", "").lower() == "fetch"
            and response.status_code < 400
        ):
            session_id, token = _security(request).issue_csrf()
            response.headers["X-CSRF-Token"] = token
            response.set_cookie(
                SESSION_COOKIE,
                session_id,
                httponly=True,
                secure=False,
                samesite="strict",
                path="/",
            )
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "sap-ewm-mock"}

    @app.post("/oauth/token")
    async def oauth_token(
        grant_type: Annotated[str, Form()],
        client_id: Annotated[str, Form()],
        client_secret: Annotated[str, Form()],
        scope: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        if grant_type != "client_credentials":
            raise ODataRequestError(
                "UNSUPPORTED_GRANT_TYPE",
                "Only client_credentials is supported",
                400,
            )
        token = app.state.security.issue_access_token(client_id, client_secret)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": scope or "",
        }

    if controls_are_enabled:

        @app.post("/_mock/faults/next", status_code=204)
        async def set_next_fault(spec: FaultSpec) -> Response:
            await app.state.faults.set_next(spec)
            return Response(status_code=204)

        @app.get("/_mock/requests")
        async def request_counts() -> dict[str, int]:
            return await app.state.faults.counts()

        @app.post("/_mock/reset", status_code=204)
        async def reset_mock() -> Response:
            app.state.repository.reset()
            app.state.security.reset()
            await app.state.faults.reset()
            return Response(status_code=204)

    @app.get(STOCK_ROOT + "/$metadata")
    @app.get(ORDER_ROOT + "/$metadata")
    async def metadata() -> Response:
        return Response(METADATA_XML, media_type="application/xml")

    @app.get(STOCK_ROOT + "/WarehousePhysicalStockProducts")
    async def list_stock(request: Request) -> dict[str, object]:
        await _before_operation(request, "get_stock")
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
        await _before_operation(request, "list_orders")
        filters = parse_eq_filter(
            request.query_params.get("$filter"),
            {
                "EWMWarehouse",
                "WarehouseOrder",
                "WarehouseOrderStatus",
                "ExecutingResource",
            },
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
        await _before_operation(request, "list_tasks")
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
        await _before_operation(request, "list_order_tasks")
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

    @app.post(order_key + "/SAP__self.AssignWarehouseOrder", status_code=204)
    async def assign_warehouse_order(
        request: Request,
        warehouse: str,
        order_id: str,
        payload: AssignOrderPayload,
    ) -> Response:
        fault = await _before_operation(
            request, "assign_order", allow_apply_then_timeout=True
        )
        _verify_write_headers(request)
        await _repository(request).assign_order(
            warehouse,
            order_id,
            payload.EWMResource,
            request.headers["If-Match"],
        )
        await _finish_apply_then_timeout(fault)
        return Response(status_code=204)

    @app.post(
        task_key + "/SAP__self.ConfirmWarehouseTaskExact", status_code=204
    )
    async def confirm_warehouse_task_exact(
        request: Request,
        warehouse: str,
        task_id: str,
        task_item: str,
    ) -> Response:
        fault = await _before_operation(
            request, "confirm_task", allow_apply_then_timeout=True
        )
        _verify_write_headers(request)
        await _repository(request).confirm_task_exact(
            warehouse,
            task_id,
            task_item,
            request.headers["If-Match"],
        )
        await _finish_apply_then_timeout(fault)
        return Response(status_code=204)

    @app.get(order_key)
    async def get_order(
        request: Request, warehouse: str, order_id: str
    ) -> dict[str, object]:
        await _before_operation(request, "get_order")
        order = _repository(request).get_order(warehouse, order_id)
        if order is None:
            raise entity_not_found("WarehouseOrder")
        return order

    @app.get(task_key)
    async def get_task(
        request: Request, warehouse: str, task_id: str, task_item: str
    ) -> dict[str, object]:
        await _before_operation(request, "get_task")
        task = _repository(request).get_task(warehouse, task_id, task_item)
        if task is None:
            raise entity_not_found("WarehouseTask")
        return task

    return app


def _repository(request: Request) -> MockRepository:
    return request.app.state.repository


def _security(request: Request) -> MockSecurity:
    return request.app.state.security


def _faults(request: Request) -> FaultController:
    return request.app.state.faults


async def _before_operation(
    request: Request,
    operation: str,
    *,
    allow_apply_then_timeout: bool = False,
) -> FaultSpec | None:
    fault = await _faults(request).take(operation)
    if fault is None:
        return None
    if fault.apply_then_timeout and allow_apply_then_timeout:
        return fault
    if fault.delay_ms:
        await asyncio.sleep(fault.delay_ms / 1000)
    if fault.status_code is not None:
        raise ODataRequestError(
            f"MOCK_FAULT_{fault.status_code}",
            "Injected SAP EWM mock fault",
            fault.status_code,
        )
    if fault.apply_then_timeout:
        raise ODataRequestError(
            "MOCK_APPLY_THEN_TIMEOUT",
            "Injected response timeout after operation",
            504,
        )
    return fault


async def _finish_apply_then_timeout(fault: FaultSpec | None) -> None:
    if fault is None or not fault.apply_then_timeout:
        return
    if fault.delay_ms:
        await asyncio.sleep(fault.delay_ms / 1000)
    raise ODataRequestError(
        "MOCK_APPLY_THEN_TIMEOUT",
        "Injected response timeout after operation",
        504,
    )


def _verify_write_headers(request: Request) -> None:
    _security(request).verify_csrf(
        request.cookies.get(SESSION_COOKIE),
        request.headers.get("X-CSRF-Token"),
    )
    if not request.headers.get("If-Match"):
        raise ODataRequestError(
            "ETAG_REQUIRED", "If-Match is required for SAP writes", 428
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


app = create_app()
