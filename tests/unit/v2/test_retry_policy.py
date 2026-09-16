from __future__ import annotations

import pytest

from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.api.services.execution.retry_policy import RetryPolicy


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 412])
def test_client_and_concurrency_errors_are_not_blindly_retried(
    status_code: int,
) -> None:
    decision = RetryPolicy(jitter_ratio=0).classify(
        SAPEWMError(
            SAPEWMErrorCode.SAP_RESPONSE_INVALID,
            "request rejected",
            status_code=status_code,
        ),
        attempt=1,
    )

    assert decision.disposition == "fail"
    assert decision.delay_seconds == 0


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_transient_remote_errors_use_bounded_exponential_backoff(
    status_code: int,
) -> None:
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=2, jitter_ratio=0)

    first = policy.classify(
        SAPEWMError(
            SAPEWMErrorCode.SAP_UNAVAILABLE,
            "temporarily unavailable",
            status_code=status_code,
            retriable=True,
        ),
        attempt=1,
    )
    second = policy.classify(
        SAPEWMError(
            SAPEWMErrorCode.SAP_UNAVAILABLE,
            "temporarily unavailable",
            status_code=status_code,
            retriable=True,
        ),
        attempt=2,
    )

    assert (first.disposition, first.delay_seconds) == ("retry", 2)
    assert (second.disposition, second.delay_seconds) == ("retry", 4)


def test_response_timeout_requires_readback_before_any_retry() -> None:
    decision = RetryPolicy(jitter_ratio=0).classify(
        SAPEWMError.unknown_outcome("response lost after submission"),
        attempt=1,
    )

    assert decision.disposition == "reconcile"
    assert decision.category == "outcome_unknown"


def test_typed_read_timeout_can_retry_when_adapter_knows_no_write_was_sent() -> None:
    decision = RetryPolicy(jitter_ratio=0).classify(
        SAPEWMError(
            SAPEWMErrorCode.SAP_TIMEOUT,
            "SAP read timed out",
            retriable=True,
        ),
        attempt=1,
    )

    assert decision.disposition == "retry"


def test_retry_budget_is_terminal() -> None:
    decision = RetryPolicy(max_attempts=3, jitter_ratio=0).classify(
        SAPEWMError(
            SAPEWMErrorCode.SAP_RATE_LIMITED,
            "rate limited",
            status_code=429,
            retriable=True,
        ),
        attempt=3,
    )

    assert decision.disposition == "fail"
    assert decision.category == "retry_exhausted"
