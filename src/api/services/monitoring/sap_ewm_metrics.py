"""Bounded-cardinality Prometheus metrics for the SAP EWM boundary."""

from __future__ import annotations

import math

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram

SAP_EWM_OPERATIONS = frozenset(
    {
        "get_stock",
        "get_orders_tasks",
        "assign_order",
        "confirm_task",
        "post_action",
        "oauth_token",
    }
)
SAP_EWM_RESULTS = frozenset(
    {"success", "error", "timeout", "unavailable", "unknown_outcome"}
)
SAP_EWM_EVENTS = frozenset(
    {"retry", "csrf_refresh", "etag_conflict", "unknown_outcome"}
)


class SAPEWMMetrics:
    """Record SAP protocol health without business identifiers as labels."""

    label_names = frozenset({"operation", "result", "event"})

    def __init__(self, registry: CollectorRegistry = REGISTRY) -> None:
        self.requests = Counter(
            "sap_ewm_requests",
            "SAP EWM requests",
            ("operation", "result"),
            registry=registry,
        )
        self.latency = Histogram(
            "sap_ewm_request_duration_seconds",
            "SAP EWM request latency",
            ("operation",),
            registry=registry,
        )
        self.events = Counter(
            "sap_ewm_protocol_events",
            "SAP EWM protocol events",
            ("event",),
            registry=registry,
        )

    def observe_request(self, operation: str, result: str, seconds: float) -> None:
        self._validate_label(operation, SAP_EWM_OPERATIONS, "operation")
        self._validate_label(result, SAP_EWM_RESULTS, "result")
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("SAP EWM metric duration must be finite and non-negative")
        self.requests.labels(operation=operation, result=result).inc()
        self.latency.labels(operation=operation).observe(seconds)

    def record_retry(self) -> None:
        self._record_event("retry")

    def record_csrf_refresh(self) -> None:
        self._record_event("csrf_refresh")

    def record_etag_conflict(self) -> None:
        self._record_event("etag_conflict")

    def record_unknown_outcome(self) -> None:
        self._record_event("unknown_outcome")

    def _record_event(self, event: str) -> None:
        self._validate_label(event, SAP_EWM_EVENTS, "event")
        self.events.labels(event=event).inc()

    @staticmethod
    def _validate_label(value: str, allowed: frozenset[str], label_name: str) -> None:
        if value not in allowed:
            raise ValueError(f"unsupported SAP EWM metric {label_name}: {value!r}")


sap_ewm_metrics = SAPEWMMetrics()


__all__ = [
    "SAPEWMMetrics",
    "SAP_EWM_EVENTS",
    "SAP_EWM_OPERATIONS",
    "SAP_EWM_RESULTS",
    "sap_ewm_metrics",
]
