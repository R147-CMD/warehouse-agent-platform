"""Stable errors exposed by the SAP EWM integration boundary."""

from __future__ import annotations

from enum import Enum


class SAPEWMErrorCode(str, Enum):
    SAP_AUTH_FAILED = "SAP_AUTH_FAILED"
    SAP_FORBIDDEN = "SAP_FORBIDDEN"
    SAP_ENTITY_NOT_FOUND = "SAP_ENTITY_NOT_FOUND"
    SAP_BUSINESS_CONFLICT = "SAP_BUSINESS_CONFLICT"
    SAP_ETAG_CONFLICT = "SAP_ETAG_CONFLICT"
    SAP_RATE_LIMITED = "SAP_RATE_LIMITED"
    SAP_UNAVAILABLE = "SAP_UNAVAILABLE"
    SAP_TIMEOUT = "SAP_TIMEOUT"
    SAP_OUTCOME_UNKNOWN = "SAP_OUTCOME_UNKNOWN"
    SAP_RESPONSE_INVALID = "SAP_RESPONSE_INVALID"


class SAPEWMError(Exception):
    """Typed failure without leaking raw remote response details."""

    def __init__(
        self,
        code: SAPEWMErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        retriable: bool = False,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retriable = retriable
        self.outcome_unknown = outcome_unknown

    @classmethod
    def unknown_outcome(cls, message: str) -> "SAPEWMError":
        return cls(
            SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN,
            message,
            retriable=False,
            outcome_unknown=True,
        )
