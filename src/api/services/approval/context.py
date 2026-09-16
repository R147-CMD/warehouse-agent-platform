"""Request-scoped approval execution context for graph tool calls."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .models import ApprovalExecutionContext


_approval_context: ContextVar[ApprovalExecutionContext | None] = ContextVar(
    "approval_execution_context", default=None
)


@contextmanager
def bind_approval_context(context: ApprovalExecutionContext) -> Iterator[ApprovalExecutionContext]:
    """Bind approval context for a graph invocation and always restore prior state."""

    token = _approval_context.set(context)
    try:
        yield context
    finally:
        _approval_context.reset(token)


def get_approval_context() -> ApprovalExecutionContext | None:
    """Return the currently bound approval context, if any."""

    return _approval_context.get()
