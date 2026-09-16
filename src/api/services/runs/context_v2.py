"""Identifiers for isolated, resumable V2 agent runs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.api.domain.identity import IdentityContext


class RunExecutionContextV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1, max_length=256)
    request_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=256)
    trace_id: str = Field(min_length=1, max_length=128)
    identity: IdentityContext
    created_at: datetime
    resumed_from_request_id: str | None = None


class RunIdentityFactory:
    """Create identifiers without conflating a conversation with one graph run."""

    @staticmethod
    def create(
        conversation_id: str,
        identity: IdentityContext,
        request_id: str | None = None,
    ) -> RunExecutionContextV2:
        normalized_conversation = conversation_id.strip()
        if not normalized_conversation:
            raise ValueError("conversation_id cannot be blank")

        run_id = str(uuid4())
        return RunExecutionContextV2(
            conversation_id=normalized_conversation,
            request_id=request_id.strip() if request_id and request_id.strip() else str(uuid4()),
            run_id=run_id,
            thread_id=f"run:{run_id}",
            trace_id=uuid4().hex,
            identity=identity,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def resume(
        previous: RunExecutionContextV2,
        identity: IdentityContext,
    ) -> RunExecutionContextV2:
        if (
            identity.tenant_id != previous.identity.tenant_id
            or identity.user_id != previous.identity.user_id
        ):
            raise ValueError("a run can only be resumed by its original identity")

        return RunExecutionContextV2(
            conversation_id=previous.conversation_id,
            request_id=str(uuid4()),
            run_id=previous.run_id,
            thread_id=previous.thread_id,
            trace_id=uuid4().hex,
            identity=identity,
            created_at=datetime.now(UTC),
            resumed_from_request_id=previous.request_id,
        )
