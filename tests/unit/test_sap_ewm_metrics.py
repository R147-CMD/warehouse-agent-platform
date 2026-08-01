"""Bounded-cardinality observability tests for SAP EWM."""

from unittest.mock import AsyncMock

import httpx
from prometheus_client import CollectorRegistry
import pytest

from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient
from src.api.services.monitoring.sap_ewm_metrics import SAPEWMMetrics


def _samples(registry: CollectorRegistry):
    return [sample for metric in registry.collect() for sample in metric.samples]


def _config(max_read_attempts: int = 2) -> SAPEWMConfig:
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
        max_read_attempts=max_read_attempts,
    )


def test_records_request_latency_and_fixed_protocol_events() -> None:
    registry = CollectorRegistry()
    metrics = SAPEWMMetrics(registry)

    metrics.observe_request("get_stock", "success", 0.125)
    metrics.record_retry()
    metrics.record_csrf_refresh()
    metrics.record_etag_conflict()
    metrics.record_unknown_outcome()

    samples = _samples(registry)
    request = next(
        sample for sample in samples if sample.name == "sap_ewm_requests_total"
    )
    duration_count = next(
        sample
        for sample in samples
        if sample.name == "sap_ewm_request_duration_seconds_count"
    )
    events = {
        sample.labels["event"]: sample.value
        for sample in samples
        if sample.name == "sap_ewm_protocol_events_total"
    }

    assert request.labels == {"operation": "get_stock", "result": "success"}
    assert request.value == 1
    assert duration_count.labels == {"operation": "get_stock"}
    assert duration_count.value == 1
    assert events == {
        "retry": 1,
        "csrf_refresh": 1,
        "etag_conflict": 1,
        "unknown_outcome": 1,
    }
    assert metrics.label_names == frozenset({"operation", "result", "event"})
    assert "base_url" not in metrics.label_names


@pytest.mark.parametrize(
    ("operation", "result"),
    [
        ("https://sap.example/secret", "success"),
        ("get_stock", "TG11"),
        ("order_2000005003", "success"),
    ],
)
def test_rejects_unbounded_metric_labels(operation: str, result: str) -> None:
    metrics = SAPEWMMetrics(CollectorRegistry())

    with pytest.raises(ValueError, match="unsupported SAP EWM metric"):
        metrics.observe_request(operation, result, 0.1)


def test_rejects_invalid_duration() -> None:
    metrics = SAPEWMMetrics(CollectorRegistry())

    with pytest.raises(ValueError, match="duration"):
        metrics.observe_request("get_stock", "success", -0.1)


@pytest.mark.asyncio
async def test_http_client_records_retry_and_final_read_result() -> None:
    registry = CollectorRegistry()
    metrics = SAPEWMMetrics(registry)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"value": []}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SAPEWMODataClient(
            _config(),
            http_client=http,
            sleeper=AsyncMock(),
            metrics=metrics,
        )
        await client.connect()
        await client.get_collection(
            "stock", "/WarehousePhysicalStockProducts", {}, "request-1"
        )

    samples = _samples(registry)
    assert (
        next(
            sample.value
            for sample in samples
            if sample.name == "sap_ewm_protocol_events_total"
            and sample.labels == {"event": "retry"}
        )
        == 1
    )
    assert (
        next(
            sample.value
            for sample in samples
            if sample.name == "sap_ewm_requests_total"
            and sample.labels == {"operation": "get_stock", "result": "success"}
        )
        == 1
    )


@pytest.mark.asyncio
async def test_http_client_records_csrf_refresh_and_etag_conflict() -> None:
    registry = CollectorRegistry()
    metrics = SAPEWMMetrics(registry)
    post_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_attempts
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"X-CSRF-Token": f"token-{post_attempts}"},
                request=request,
            )
        post_attempts += 1
        if post_attempts == 1:
            return httpx.Response(
                403,
                json={"error": {"code": "CSRF_TOKEN_INVALID"}},
                request=request,
            )
        return httpx.Response(412, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SAPEWMODataClient(_config(), http_client=http, metrics=metrics)
        await client.connect()
        with pytest.raises(SAPEWMError) as raised:
            await client.post_action(
                "orders",
                "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='1')/"
                "SAP__self.AssignWarehouseOrder",
                {"EWMResource": "RES2"},
                'W/"1"',
                "request-2",
            )

    assert raised.value.code is SAPEWMErrorCode.SAP_ETAG_CONFLICT
    events = {
        sample.labels["event"]: sample.value
        for sample in _samples(registry)
        if sample.name == "sap_ewm_protocol_events_total"
    }
    assert events == {"csrf_refresh": 1, "etag_conflict": 1}


@pytest.mark.asyncio
async def test_http_client_records_unknown_write_outcome() -> None:
    registry = CollectorRegistry()
    metrics = SAPEWMMetrics(registry)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"X-CSRF-Token": "token"},
                request=request,
            )
        raise httpx.ReadTimeout("response lost", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SAPEWMODataClient(_config(), http_client=http, metrics=metrics)
        await client.connect()
        with pytest.raises(SAPEWMError) as raised:
            await client.post_action(
                "orders",
                "/WarehouseTask(EWMWarehouse='EW01',WarehouseTask='1',"
                "WarehouseTaskItem='0')/SAP__self.ConfirmWarehouseTaskExact",
                {},
                'W/"1"',
                "request-3",
            )

    assert raised.value.code is SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN
    samples = _samples(registry)
    assert (
        next(
            sample.value
            for sample in samples
            if sample.name == "sap_ewm_protocol_events_total"
            and sample.labels == {"event": "unknown_outcome"}
        )
        == 1
    )
    assert (
        next(
            sample.value
            for sample in samples
            if sample.name == "sap_ewm_requests_total"
            and sample.labels
            == {"operation": "confirm_task", "result": "unknown_outcome"}
        )
        == 1
    )
