"""Request-scoped run execution context."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .models import RunExecutionContext


_run_context: ContextVar[RunExecutionContext | None] = ContextVar(
    "agent_run_execution_context",
    default=None,
)


@contextmanager
def bind_run_context(context: RunExecutionContext) -> Iterator[RunExecutionContext]:
    """Bind run context and restore the previous context on exit."""

    token = _run_context.set(context)
    try:
        yield context
    finally:
        _run_context.reset(token)


def get_run_context() -> RunExecutionContext | None:
    """Return the currently bound run context, if any."""

    return _run_context.get()
