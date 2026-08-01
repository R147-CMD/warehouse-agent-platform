"""Unit tests for the secure SAP EWM OData HTTP client."""

import base64
import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest

from src.adapters.wms.sap_ewm_config import SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient


def sap_config(**overrides) -> SAPEWMConfig:
    values = {
        "enabled": True,
        "mock_mode": True,
        "base_url": "http://sap.example.test",
        "warehouse": "EW01",
        "client": "100",
        "auth_mode": "basic",
        "username": "svc-user",
        "password": "svc-password",
        "verify_tls": False,
        "max_read_attempts": 3,
    }
    values.update(overrides)
    return SAPEWMConfig(**values)


async def make_client(
    handler,
    *,
    config: SAPEWMConfig | None = None,
    sleeper=None,
) -> SAPEWMODataClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SAPEWMODataClient(
        config or sap_config(),
        http_client=http_client,
        sleeper=sleeper or AsyncMock(),
    )
    assert await client.connect() is True
    return client


@pytest.mark.asyncio
async def test_basic_get_sends_client_correlation_and_credentials() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"value": []})

    client = await make_client(handler)
    try:
        result = await client.get_collection(
            "stock",
            "/WarehousePhysicalStockProducts",
            params={"$top": "10"},
            correlation_id="request-1",
        )
    finally:
        await client.close()

    expected_basic = base64.b64encode(b"svc-user:svc-password").decode("ascii")
    assert result == {"value": []}
    assert requests[0].headers["Authorization"] == f"Basic {expected_basic}"
    assert requests[0].headers["X-Correlation-ID"] == "request-1"
    assert requests[0].url.params["sap-client"] == "100"
    assert requests[0].url.params["$top"] == "10"


@pytest.mark.asyncio
async def test_get_retries_503_then_succeeds() -> None:
    attempts = 0
    sleeper = AsyncMock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"value": []})

    client = await make_client(handler, sleeper=sleeper)
    try:
        result = await client.get_collection(
            "stock", "/WarehousePhysicalStockProducts", params={}
        )
    finally:
        await client.close()

    assert result["value"] == []
    assert client.read_attempts == 2
    sleeper.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_honors_retry_after() -> None:
    attempts = 0
    sleeper = AsyncMock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json={"value": []})

    client = await make_client(handler, sleeper=sleeper)
    try:
        await client.get_collection(
            "stock", "/WarehousePhysicalStockProducts", params={}
        )
    finally:
        await client.close()

    sleeper.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_read_timeout_becomes_typed_error_after_bounded_attempts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("slow", request=request)

    client = await make_client(handler, config=sap_config(max_read_attempts=2))
    try:
        with pytest.raises(SAPEWMError) as captured:
            await client.get_collection(
                "stock", "/WarehousePhysicalStockProducts", params={}
            )
    finally:
        await client.close()

    assert attempts == 2
    assert captured.value.code is SAPEWMErrorCode.SAP_TIMEOUT
    assert captured.value.retriable is True


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (401, SAPEWMErrorCode.SAP_AUTH_FAILED),
        (403, SAPEWMErrorCode.SAP_FORBIDDEN),
        (404, SAPEWMErrorCode.SAP_ENTITY_NOT_FOUND),
        (409, SAPEWMErrorCode.SAP_BUSINESS_CONFLICT),
        (412, SAPEWMErrorCode.SAP_ETAG_CONFLICT),
    ],
)
@pytest.mark.asyncio
async def test_maps_sap_http_errors(
    status: int, expected_code: SAPEWMErrorCode
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"code": "REMOTE", "message": "safe remote message"}},
        )

    client = await make_client(handler, config=sap_config(max_read_attempts=1))
    try:
        with pytest.raises(SAPEWMError) as captured:
            await client.get_entity("orders", "/WarehouseOrder('missing')")
    finally:
        await client.close()

    assert captured.value.code is expected_code
    assert captured.value.status_code == status


@pytest.mark.asyncio
async def test_oauth_refreshes_once_after_401() -> None:
    token_calls = 0
    business_calls = 0
    authorization_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, business_calls
        if request.url.path == "/oauth/token":
            token_calls += 1
            form = parse_qs(request.content.decode("utf-8"))
            assert form["client_id"] == ["client-id"]
            assert form["client_secret"] == ["client-secret"]
            return httpx.Response(
                200,
                json={
                    "access_token": f"token-{token_calls}",
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            )
        business_calls += 1
        authorization_headers.append(request.headers["Authorization"])
        if business_calls == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"value": []})

    config = sap_config(
        auth_mode="oauth2_client_credentials",
        username=None,
        password=None,
        token_url="http://sap.example.test/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
    )
    client = await make_client(handler, config=config)
    try:
        result = await client.get_collection(
            "stock", "/WarehousePhysicalStockProducts", params={}
        )
    finally:
        await client.close()

    assert result == {"value": []}
    assert token_calls == 2
    assert authorization_headers == ["Bearer token-1", "Bearer token-2"]


@pytest.mark.asyncio
async def test_post_sends_csrf_cookie_and_if_match() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            assert request.headers["X-CSRF-Token"] == "Fetch"
            return httpx.Response(
                200,
                headers={
                    "X-CSRF-Token": "csrf-token",
                    "Set-Cookie": "SAP_SESSIONID_MOCK=session-1; Path=/; HttpOnly",
                },
                content=b"metadata",
            )
        return httpx.Response(204)

    client = await make_client(handler)
    try:
        await client.post_action(
            "orders",
            "/WarehouseOrder(EWMWarehouse='EW01',WarehouseOrder='2000005003')"
            "/SAP__self.AssignWarehouseOrder",
            {"EWMResource": "RES2"},
            etag='W/"1"',
        )
    finally:
        await client.close()

    posted = requests[-1]
    assert posted.headers["X-CSRF-Token"] == "csrf-token"
    assert posted.headers["If-Match"] == 'W/"1"'
    assert "SAP_SESSIONID_MOCK=session-1" in posted.headers["Cookie"]


@pytest.mark.asyncio
async def test_post_refreshes_csrf_once_after_explicit_rejection() -> None:
    csrf_fetches = 0
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal csrf_fetches, post_calls
        if request.method == "GET":
            csrf_fetches += 1
            return httpx.Response(
                200,
                headers={
                    "X-CSRF-Token": f"csrf-{csrf_fetches}",
                    "Set-Cookie": (
                        f"SAP_SESSIONID_MOCK=session-{csrf_fetches}; Path=/"
                    ),
                },
                content=b"metadata",
            )
        post_calls += 1
        if post_calls == 1:
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": "CSRF_TOKEN_INVALID",
                        "message": "expired",
                    }
                },
            )
        assert request.headers["X-CSRF-Token"] == "csrf-2"
        return httpx.Response(204)

    client = await make_client(handler)
    try:
        await client.post_action("orders", "/action", {}, etag='W/"1"')
    finally:
        await client.close()

    assert csrf_fetches == 2
    assert post_calls == 2


@pytest.mark.asyncio
async def test_post_timeout_is_unknown_and_is_not_retried() -> None:
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"X-CSRF-Token": "csrf-token"},
                content=b"metadata",
            )
        post_calls += 1
        raise httpx.ReadTimeout("response not received", request=request)

    client = await make_client(handler)
    try:
        with pytest.raises(SAPEWMError) as captured:
            await client.post_action("orders", "/action", {}, etag='W/"1"')
    finally:
        await client.close()

    assert post_calls == 1
    assert captured.value.code is SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN
    assert captured.value.outcome_unknown is True


def test_cursor_rejects_other_origin_and_service_prefix() -> None:
    client = SAPEWMODataClient(sap_config())
    evil = base64.urlsafe_b64encode(b"https://evil.example/steal").decode()
    wrong_service = base64.urlsafe_b64encode(
        (
            "http://sap.example.test"
            + SAPEWMODataClient.SERVICE_ROOTS["orders"]
            + "/WarehouseOrder"
        ).encode()
    ).decode()

    with pytest.raises(SAPEWMError) as evil_error:
        client.decode_cursor(evil, expected_service="stock")
    with pytest.raises(SAPEWMError) as service_error:
        client.decode_cursor(wrong_service, expected_service="stock")

    assert evil_error.value.code is SAPEWMErrorCode.SAP_RESPONSE_INVALID
    assert service_error.value.code is SAPEWMErrorCode.SAP_RESPONSE_INVALID


def test_cursor_round_trip_accepts_same_origin_service_url() -> None:
    client = SAPEWMODataClient(sap_config())
    next_link = (
        "http://sap.example.test"
        + SAPEWMODataClient.SERVICE_ROOTS["stock"]
        + "/WarehousePhysicalStockProducts?%24filter="
        + "EWMWarehouse%20eq%20%27EW01%27&%24skiptoken=1&sap-client=100"
    )

    cursor = client.encode_next_link(next_link, "stock")

    assert cursor is not None
    assert client.decode_cursor(cursor, expected_service="stock") == next_link
    assert client.encode_next_link(None, "stock") is None


def test_cursor_signature_rejects_tampered_warehouse_filter() -> None:
    client = SAPEWMODataClient(sap_config())
    next_link = (
        "http://sap.example.test"
        + SAPEWMODataClient.SERVICE_ROOTS["stock"]
        + "/WarehousePhysicalStockProducts?%24filter="
        + "EWMWarehouse%20eq%20%27EW01%27&%24skiptoken=1&sap-client=100"
    )
    cursor = client.encode_next_link(next_link, "stock")
    assert cursor is not None
    encoded_payload, signature = cursor.split(".", maxsplit=1)
    padding = "=" * (-len(encoded_payload) % 4)
    payload = json.loads(
        base64.urlsafe_b64decode(encoded_payload + padding).decode("utf-8")
    )
    payload["url"] = payload["url"].replace("EW01", "OTHER")
    tampered_payload = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )

    with pytest.raises(SAPEWMError) as captured:
        client.decode_cursor(
            f"{tampered_payload}.{signature}", expected_service="stock"
        )

    assert captured.value.code is SAPEWMErrorCode.SAP_RESPONSE_INVALID


def test_cursor_is_bound_to_connection_warehouse_and_client() -> None:
    client = SAPEWMODataClient(sap_config())
    other_warehouse_client = SAPEWMODataClient(sap_config(warehouse="OTHER"))
    next_link = (
        "http://sap.example.test"
        + SAPEWMODataClient.SERVICE_ROOTS["stock"]
        + "/WarehousePhysicalStockProducts?%24skiptoken=1&sap-client=100"
    )
    cursor = client.encode_next_link(next_link, "stock")
    assert cursor is not None

    with pytest.raises(SAPEWMError) as captured:
        other_warehouse_client.decode_cursor(cursor, expected_service="stock")

    assert captured.value.code is SAPEWMErrorCode.SAP_RESPONSE_INVALID


def test_next_link_rejects_mismatched_sap_client() -> None:
    client = SAPEWMODataClient(sap_config())
    next_link = (
        "http://sap.example.test"
        + SAPEWMODataClient.SERVICE_ROOTS["stock"]
        + "/WarehousePhysicalStockProducts?%24skiptoken=1&sap-client=200"
    )

    with pytest.raises(SAPEWMError) as captured:
        client.encode_next_link(next_link, "stock")

    assert captured.value.code is SAPEWMErrorCode.SAP_RESPONSE_INVALID


@pytest.mark.asyncio
async def test_get_cursor_page_fetches_the_validated_next_link() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"value": [{"Product": "TG12"}]})

    client = await make_client(handler)
    next_link = (
        "http://sap.example.test"
        + SAPEWMODataClient.SERVICE_ROOTS["stock"]
        + "/WarehousePhysicalStockProducts?%24skiptoken=1&sap-client=100"
    )
    cursor = client.encode_next_link(next_link, "stock")
    assert cursor is not None
    try:
        page = await client.get_cursor_page(
            cursor, "stock", correlation_id="request-page-2"
        )
    finally:
        await client.close()

    assert page["value"][0]["Product"] == "TG12"
    assert requested_urls == [next_link]
