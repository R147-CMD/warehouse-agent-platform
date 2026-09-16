"""Small W3C trace-context seam with an OpenTelemetry-compatible shape.

The implementation intentionally works without the optional OpenTelemetry SDK;
production can replace the exporter while keeping the same span contract.
"""

from __future__ import annotations

import contextvars
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from src.api.services.security.trust_labels import redact_with_report


@dataclass
class TraceSpan:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-01"


_CURRENT_SPAN: contextvars.ContextVar[TraceSpan | None] = contextvars.ContextVar(
    "warehouse_current_trace", default=None
)


def current_trace() -> TraceSpan:
    span = _CURRENT_SPAN.get()
    if span is None:
        return TraceSpan("root", secrets.token_hex(16), secrets.token_hex(8))
    return span


def _parse_traceparent(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = value.split("-")
    if len(parts) != 4 or len(parts[1]) != 32 or len(parts[2]) != 16:
        return None, None
    return parts[1], parts[2]


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    *,
    traceparent: str | None = None,
) -> Iterator[TraceSpan]:
    parent = _CURRENT_SPAN.get()
    incoming_trace, incoming_parent = _parse_traceparent(traceparent)
    trace_id = incoming_trace or (parent.trace_id if parent else secrets.token_hex(16))
    parent_span_id = incoming_parent or (parent.span_id if parent else None)
    redacted, _ = redact_with_report(attributes or {})
    span = TraceSpan(
        name=name,
        trace_id=trace_id,
        span_id=secrets.token_hex(8),
        parent_span_id=parent_span_id,
        attributes=redacted,
    )
    token = _CURRENT_SPAN.set(span)
    try:
        yield span
    finally:
        _CURRENT_SPAN.reset(token)
