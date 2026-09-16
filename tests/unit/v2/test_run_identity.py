from datetime import UTC, datetime


def _identity():
    from src.api.domain.identity import IdentityContext

    return IdentityContext(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("supervisor",),
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=datetime.now(UTC),
    )


def test_same_conversation_creates_isolated_runs_and_threads():
    from src.api.services.runs.context_v2 import RunIdentityFactory

    first = RunIdentityFactory.create("conversation-1", _identity())
    second = RunIdentityFactory.create("conversation-1", _identity())

    assert first.conversation_id == second.conversation_id
    assert first.request_id != second.request_id
    assert first.run_id != second.run_id
    assert first.thread_id != second.thread_id
    assert first.trace_id != second.trace_id


def test_resume_preserves_run_and_thread_but_creates_request():
    from src.api.services.runs.context_v2 import RunIdentityFactory

    created = RunIdentityFactory.create("conversation-1", _identity())
    resumed = RunIdentityFactory.resume(created, _identity())

    assert resumed.run_id == created.run_id
    assert resumed.thread_id == created.thread_id
    assert resumed.request_id != created.request_id
    assert resumed.trace_id != created.trace_id
