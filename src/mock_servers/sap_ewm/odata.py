"""Small, strict subset of OData V4 used by the SAP EWM mock."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


FILTER_TERM = re.compile(
    r"(?P<field>[A-Za-z][A-Za-z0-9_]*)\s+eq\s+'(?P<value>(?:''|[^'])*)'"
)


class ODataRequestError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def parse_eq_filter(raw: str | None, allowed: set[str]) -> dict[str, str]:
    if not raw:
        return {}

    filters: dict[str, str] = {}
    for term in re.split(r"\s+and\s+", raw, flags=re.IGNORECASE):
        match = FILTER_TERM.fullmatch(term.strip())
        if not match or match.group("field") not in allowed:
            raise ODataRequestError(
                "INVALID_FILTER", "Unsupported $filter expression", 400
            )
        filters[match.group("field")] = match.group("value").replace("''", "'")
    return filters


def parse_top(request: Request, *, default: int = 100, maximum: int = 100) -> int:
    return _parse_nonnegative_integer(
        request.query_params.get("$top"),
        name="$top",
        default=default,
        minimum=1,
        maximum=maximum,
    )


def parse_skiptoken(request: Request) -> int:
    return _parse_nonnegative_integer(
        request.query_params.get("$skiptoken"),
        name="$skiptoken",
        default=0,
        minimum=0,
        maximum=1_000_000,
    )


def odata_collection(
    request: Request,
    *,
    service_root: str,
    entity_set: str,
    rows: Iterable[dict[str, Any]],
    top: int,
    offset: int,
) -> dict[str, Any]:
    values = list(rows)
    page = values[offset : offset + top]
    base_url = str(request.base_url).rstrip("/")
    result: dict[str, Any] = {
        "@odata.context": f"{base_url}{service_root}/$metadata#{entity_set}",
        "value": page,
    }
    if offset + top < len(values):
        result["@odata.nextLink"] = str(
            request.url.include_query_params(**{"$skiptoken": str(offset + top)})
        )
    return result


def entity_not_found(entity: str) -> ODataRequestError:
    return ODataRequestError(
        "ENTITY_NOT_FOUND", f"{entity} was not found", 404
    )


def odata_error_response(error: ODataRequestError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


def _parse_nonnegative_integer(
    raw: str | None,
    *,
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ODataRequestError(
            "INVALID_QUERY_OPTION", f"{name} must be an integer", 400
        ) from exc
    if not minimum <= value <= maximum:
        raise ODataRequestError(
            "INVALID_QUERY_OPTION",
            f"{name} must be between {minimum} and {maximum}",
            400,
        )
    return value
