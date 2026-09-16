"""Classify command failures without blindly repeating remote writes."""

from __future__ import annotations

import random
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode


class RetryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: Literal["retry", "reconcile", "fail"]
    category: str
    delay_seconds: float = Field(default=0, ge=0)
    reason: str


class RetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_delay_seconds: float = 2,
        max_delay_seconds: float = 60,
        jitter_ratio: float = 0.2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.jitter_ratio = jitter_ratio

    def classify(self, error: Exception, *, attempt: int) -> RetryDecision:
        if _outcome_is_unknown(error):
            return RetryDecision(
                disposition="reconcile",
                category="outcome_unknown",
                reason="remote write may have succeeded; read back before retry",
            )

        status_code = getattr(error, "status_code", None)
        if status_code in {400, 401, 403, 404, 409, 412}:
            return RetryDecision(
                disposition="fail",
                category="request_rejected",
                reason=f"remote request rejected with HTTP {status_code}",
            )

        transient = status_code == 429 or (
            isinstance(status_code, int) and 500 <= status_code <= 599
        )
        transient = transient or isinstance(error, httpx.ConnectError)
        transient = transient or (
            isinstance(error, SAPEWMError)
            and error.code
            in {
                SAPEWMErrorCode.SAP_RATE_LIMITED,
                SAPEWMErrorCode.SAP_UNAVAILABLE,
                SAPEWMErrorCode.SAP_TIMEOUT,
            }
        )
        if transient:
            if attempt >= self.max_attempts:
                return RetryDecision(
                    disposition="fail",
                    category="retry_exhausted",
                    reason="transient retry budget exhausted",
                )
            return RetryDecision(
                disposition="retry",
                category="transient",
                delay_seconds=self._delay(attempt),
                reason="transient remote or transport failure",
            )

        return RetryDecision(
            disposition="fail",
            category="non_retriable",
            reason=f"{type(error).__name__} is not safe to retry",
        )

    def _delay(self, attempt: int) -> float:
        base = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(attempt - 1, 0)),
        )
        if self.jitter_ratio == 0:
            return base
        jitter = base * self.jitter_ratio * random.random()
        return min(self.max_delay_seconds, base + jitter)


def _outcome_is_unknown(error: Exception) -> bool:
    if isinstance(error, SAPEWMError):
        return error.outcome_unknown or error.code in {
            SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN,
        }
    return isinstance(error, (httpx.ReadTimeout, httpx.WriteError))
