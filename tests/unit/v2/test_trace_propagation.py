from __future__ import annotations

from src.api.services.monitoring.tracing_v2 import current_trace, trace_span


def test_nested_spans_propagate_trace_id_and_parent_relationship() -> None:
    with trace_span("api.request", {"run_id": "run-1"}) as root:
        with trace_span("agent.task", {"node_id": "query"}) as child:
            assert child.trace_id == root.trace_id
            assert child.parent_span_id == root.span_id
            assert current_trace().span_id == child.span_id
        assert current_trace().span_id == root.span_id


def test_trace_attributes_are_redacted_before_recording() -> None:
    with trace_span(
        "tool.call", {"authorization": "Bearer secret", "safe": "ok"}
    ) as span:
        assert span.attributes["authorization"] == "[REDACTED]"
        assert span.attributes["safe"] == "ok"


def test_w3c_traceparent_can_be_forwarded_to_downstream_service() -> None:
    with trace_span("worker", {}) as span:
        header = span.traceparent

    assert header.startswith("00-")
    assert span.trace_id in header
    assert span.span_id in header
