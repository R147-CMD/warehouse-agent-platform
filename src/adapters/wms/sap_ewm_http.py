"""Secure OData V4 HTTP client for SAP EWM and its protocol mock."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .sap_ewm_config import SAPAuthMode, SAPEWMConfig
from .sap_ewm_errors import SAPEWMError, SAPEWMErrorCode


logger = logging.getLogger(__name__)

_RETRIABLE_READ_STATUSES = {429, 500, 502, 503, 504}
_CSRF_ERROR_CODES = {"CSRF_TOKEN_INVALID", "CSRF_TOKEN_MISSING"}


class SAPEWMODataClient:
    """Own authentication, protocol headers, retries, and safe pagination."""

    SERVICE_ROOTS = {
        "stock": (
            "/sap/opu/odata4/sap/api_whse_physstockprod/srvd_a2x/"
            "sap/whsephysicalstockproducts/0001"
        ),
        "orders": (
            "/sap/opu/odata4/sap/api_warehouse_order_task_2/srvd_a2x/"
            "sap/warehouseorder/0001"
        ),
    }

    def __init__(
        self,
        config: SAPEWMConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self._client = http_client
        self._sleeper = sleeper
        self._clock = clock
        self._connected = False
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._csrf_tokens: dict[str, str] = {}
        self.read_attempts = 0

    async def connect(self) -> bool:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self.config.connect_timeout_seconds,
                read=self.config.read_timeout_seconds,
                write=self.config.read_timeout_seconds,
                pool=self.config.connect_timeout_seconds,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                verify=self.config.verify_tls,
                follow_redirects=False,
            )
        self._connected = True
        return True

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._connected = False

    async def get_collection(
        self,
        service: str,
        entity: str,
        params: dict[str, str],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._read_json(
            self._service_url(service, entity),
            params=self._client_params(params),
            correlation_id=correlation_id,
        )

    async def get_entity(
        self,
        service: str,
        path: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._read_json(
            self._service_url(service, path),
            params=self._client_params({}),
            correlation_id=correlation_id,
        )

    async def get_cursor_page(
        self,
        cursor: str,
        expected_service: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        absolute_url = self.decode_cursor(
            cursor, expected_service=expected_service
        )
        return await self._read_json(
            absolute_url,
            params=None,
            correlation_id=correlation_id,
        )

    async def post_action(
        self,
        service: str,
        path: str,
        body: dict[str, Any] | None,
        etag: str,
        correlation_id: str | None = None,
    ) -> None:
        self._ensure_connected()
        url = self._service_url(service, path)
        request_id = correlation_id or str(uuid4())

        for csrf_attempt in range(2):
            token = await self._csrf_token(service, request_id)
            headers = {
                "X-CSRF-Token": token,
                "If-Match": etag,
                "X-Correlation-ID": request_id,
            }
            try:
                response = await self._send_with_oauth_refresh(
                    "POST",
                    url,
                    params=self._client_params({}),
                    json=body,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                raise SAPEWMError.unknown_outcome(
                    "SAP write response was not received"
                ) from exc
            except httpx.NetworkError as exc:
                raise SAPEWMError.unknown_outcome(
                    "SAP write connection ended before a response was received"
                ) from exc

            if response.status_code == 204:
                return
            if csrf_attempt == 0 and self._is_csrf_rejection(response):
                self._csrf_tokens.pop(service, None)
                continue
            raise self._response_error(response)

        raise SAPEWMError(
            SAPEWMErrorCode.SAP_FORBIDDEN,
            "SAP rejected the refreshed CSRF token",
            status_code=403,
        )

    def encode_cursor(self, absolute_url: str) -> str:
        encoded = base64.urlsafe_b64encode(absolute_url.encode("utf-8"))
        return encoded.decode("ascii").rstrip("=")

    def encode_next_link(
        self, next_link: str | None, expected_service: str
    ) -> str | None:
        if next_link is None:
            return None
        self._validate_next_link(next_link, expected_service)
        return self.encode_cursor(next_link)

    def decode_cursor(self, cursor: str, expected_service: str) -> str:
        try:
            padding = "=" * (-len(cursor) % 4)
            absolute_url = base64.urlsafe_b64decode(
                (cursor + padding).encode("ascii")
            ).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "SAP pagination cursor is malformed",
            ) from exc
        self._validate_next_link(absolute_url, expected_service)
        return absolute_url

    async def _read_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        self._ensure_connected()
        request_id = correlation_id or str(uuid4())
        self.read_attempts = 0

        for attempt in range(1, self.config.max_read_attempts + 1):
            self.read_attempts = attempt
            try:
                response = await self._send_with_oauth_refresh(
                    "GET",
                    url,
                    params=params,
                    headers={"X-Correlation-ID": request_id},
                )
            except httpx.TimeoutException as exc:
                if attempt < self.config.max_read_attempts:
                    await self._sleeper(self._backoff(attempt, None))
                    continue
                raise SAPEWMError(
                    SAPEWMErrorCode.SAP_TIMEOUT,
                    "SAP read timed out",
                    retriable=True,
                ) from exc
            except httpx.NetworkError as exc:
                if attempt < self.config.max_read_attempts:
                    await self._sleeper(self._backoff(attempt, None))
                    continue
                raise SAPEWMError(
                    SAPEWMErrorCode.SAP_UNAVAILABLE,
                    "SAP connection is unavailable",
                    retriable=True,
                ) from exc

            if (
                response.status_code in _RETRIABLE_READ_STATUSES
                and attempt < self.config.max_read_attempts
            ):
                await self._sleeper(self._backoff(attempt, response))
                continue
            if not 200 <= response.status_code < 300:
                raise self._response_error(response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise SAPEWMError(
                    SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                    "SAP returned an invalid JSON response",
                    status_code=response.status_code,
                ) from exc
            if not isinstance(payload, dict):
                raise SAPEWMError(
                    SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                    "SAP returned an unexpected response shape",
                    status_code=response.status_code,
                )
            return payload

        raise AssertionError("bounded SAP read loop exhausted unexpectedly")

    async def _csrf_token(self, service: str, correlation_id: str) -> str:
        cached = self._csrf_tokens.get(service)
        if cached:
            return cached
        response = await self._send_with_oauth_refresh(
            "GET",
            self._service_url(service, "/$metadata"),
            params=self._client_params({}),
            headers={
                "X-CSRF-Token": "Fetch",
                "X-Correlation-ID": correlation_id,
            },
        )
        if not 200 <= response.status_code < 300:
            raise self._response_error(response)
        token = response.headers.get("X-CSRF-Token")
        if not token:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "SAP did not return a CSRF token",
                status_code=response.status_code,
            )
        self._csrf_tokens[service] = token
        return token

    async def _send_with_oauth_refresh(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request_headers = {**headers, **(await self._authorization_headers())}
        response = await self._http_client().request(
            method,
            url,
            params=params,
            headers=request_headers,
            json=json,
        )
        if (
            response.status_code == 401
            and self.config.auth_mode
            is SAPAuthMode.OAUTH2_CLIENT_CREDENTIALS
        ):
            await self._oauth_token(force_refresh=True)
            request_headers = {
                **headers,
                **(await self._authorization_headers()),
            }
            response = await self._http_client().request(
                method,
                url,
                params=params,
                headers=request_headers,
                json=json,
            )
        return response

    async def _authorization_headers(self) -> dict[str, str]:
        if self.config.auth_mode is SAPAuthMode.BASIC:
            assert self.config.username is not None
            assert self.config.password is not None
            raw = (
                f"{self.config.username}:"
                f"{self.config.password.get_secret_value()}"
            ).encode("utf-8")
            token = base64.b64encode(raw).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        return {"Authorization": f"Bearer {await self._oauth_token()}"}

    async def _oauth_token(self, *, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token
            and self._clock() < self._access_token_expires_at
        ):
            return self._access_token

        assert self.config.token_url is not None
        assert self.config.client_id is not None
        assert self.config.client_secret is not None
        data = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret.get_secret_value(),
        }
        if self.config.scope:
            data["scope"] = self.config.scope
        try:
            response = await self._http_client().post(
                str(self.config.token_url), data=data
            )
        except httpx.HTTPError as exc:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_AUTH_FAILED,
                "SAP OAuth token endpoint is unavailable",
                retriable=True,
            ) from exc
        if response.status_code != 200:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_AUTH_FAILED,
                "SAP OAuth client authentication failed",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
            token = payload["access_token"]
            expires_in = float(payload.get("expires_in", 300))
        except (KeyError, TypeError, ValueError) as exc:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "SAP OAuth token response is invalid",
                status_code=response.status_code,
            ) from exc
        if not isinstance(token, str) or not token:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "SAP OAuth access token is invalid",
                status_code=response.status_code,
            )
        self._access_token = token
        self._access_token_expires_at = self._clock() + max(
            0.0, expires_in - 30.0
        )
        return token

    def _response_error(self, response: httpx.Response) -> SAPEWMError:
        status = response.status_code
        mapping = {
            401: SAPEWMErrorCode.SAP_AUTH_FAILED,
            403: SAPEWMErrorCode.SAP_FORBIDDEN,
            404: SAPEWMErrorCode.SAP_ENTITY_NOT_FOUND,
            409: SAPEWMErrorCode.SAP_BUSINESS_CONFLICT,
            412: SAPEWMErrorCode.SAP_ETAG_CONFLICT,
            429: SAPEWMErrorCode.SAP_RATE_LIMITED,
        }
        if status in mapping:
            code = mapping[status]
        elif status >= 500:
            code = SAPEWMErrorCode.SAP_UNAVAILABLE
        else:
            code = SAPEWMErrorCode.SAP_RESPONSE_INVALID
        return SAPEWMError(
            code,
            f"SAP request failed with HTTP {status}",
            status_code=status,
            retriable=status in _RETRIABLE_READ_STATUSES,
        )

    def _is_csrf_rejection(self, response: httpx.Response) -> bool:
        if response.status_code != 403:
            return False
        try:
            code = response.json()["error"]["code"]
        except (KeyError, TypeError, ValueError):
            return False
        return code in _CSRF_ERROR_CODES

    def _service_url(self, service: str, path: str) -> str:
        try:
            service_root = self.SERVICE_ROOTS[service]
        except KeyError as exc:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "Unknown SAP EWM service",
            ) from exc
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{str(self.config.base_url).rstrip('/')}{service_root}{suffix}"

    def _client_params(self, params: dict[str, str]) -> dict[str, str]:
        return {**params, "sap-client": self.config.client}

    def _validate_next_link(self, absolute_url: str, service: str) -> None:
        try:
            expected_root = self.SERVICE_ROOTS[service]
        except KeyError as exc:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "Unknown SAP EWM pagination service",
            ) from exc

        candidate = urlsplit(absolute_url)
        configured = urlsplit(str(self.config.base_url))
        if (
            candidate.scheme.lower() != configured.scheme.lower()
            or (candidate.hostname or "").lower()
            != (configured.hostname or "").lower()
            or _effective_port(candidate) != _effective_port(configured)
            or not (
                candidate.path == expected_root
                or candidate.path.startswith(expected_root + "/")
            )
            or candidate.username is not None
            or candidate.password is not None
        ):
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_RESPONSE_INVALID,
                "SAP pagination link is outside the configured service",
            )

    def _backoff(
        self, attempt: int, response: httpx.Response | None
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0.0, min(float(retry_after), 30.0))
                except ValueError:
                    pass
        return min(0.1 * (2 ** (attempt - 1)), 2.0)

    def _ensure_connected(self) -> None:
        if not self._connected or self._client is None:
            raise SAPEWMError(
                SAPEWMErrorCode.SAP_UNAVAILABLE,
                "SAP EWM client is not connected",
            )

    def _http_client(self) -> httpx.AsyncClient:
        self._ensure_connected()
        assert self._client is not None
        return self._client


def _effective_port(parts) -> int | None:
    if parts.port is not None:
        return parts.port
    if parts.scheme.lower() == "https":
        return 443
    if parts.scheme.lower() == "http":
        return 80
    return None
