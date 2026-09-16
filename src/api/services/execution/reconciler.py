"""Resolve unknown remote outcomes through readback before any retry."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime

from src.api.services.evidence_v2.store import EvidenceStore

from .execution_evidence import command_readback_evidence
from .models import Command
from .store import ExecutionStore
from .worker import ExecutionOutcome


class CommandReconciler:
    def __init__(
        self,
        store: ExecutionStore,
        readers: dict[str, Callable[[Command], object]],
        *,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        self.store = store
        self.readers = readers
        self.evidence_store = evidence_store

    async def reconcile(self, command_id: str) -> Command:
        command = await self.store.get_command(command_id)
        if command is None:
            raise LookupError("command not found")
        if command.status != "result_unknown":
            return command
        reader = self.readers.get(command.capability)
        if reader is None:
            return command
        outcome = reader(command)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        outcome = ExecutionOutcome.model_validate(outcome)
        if outcome.verified:
            status = "succeeded"
        elif not outcome.accepted:
            status = "failed"
        else:
            status = "result_unknown"
        updated = command.model_copy(
            update={
                "status": status,
                "external_reference": outcome.external_reference,
                "readback": outcome.readback,
                "updated_at": datetime.now(UTC),
            }
        )
        if updated.status == "succeeded":
            evidence = command_readback_evidence(updated)
            if self.evidence_store is not None:
                await self.evidence_store.append(evidence)
            updated = updated.model_copy(update={"evidence_refs": (evidence.ref,)})
        await self.store.update_command(updated)
        return updated
