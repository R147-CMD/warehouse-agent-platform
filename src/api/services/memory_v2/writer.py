"""Post-answer policy gate for short-term turns and long-term memories."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from src.api.domain.identity import AccessControl, IdentityContext

from .models import (
    ConversationTurn,
    MemoryCandidate,
    MemoryItem,
    MemoryRejection,
    MemoryWriteReport,
)
from .store import MemoryStore


class MemoryWriter:
    ALLOWED_TYPES = {
        "preference",
        "stable_constraint",
        "business_glossary",
        "summary",
    }
    ALLOWED_SOURCES = {"user", "system", "approved_summary"}
    INJECTION_MARKERS = (
        "ignore previous",
        "ignore all previous",
        "system prompt",
        "忽略以前",
        "忽略之前",
        "系统提示",
    )
    SENSITIVE_PATTERN = re.compile(
        r"(?i)(password|passwd|access[_ -]?token|api[_ -]?key|authorization|secret)\s*[:=]"
    )
    LIVE_FACT_PATTERN = re.compile(
        r"(?i)((当前|实时|现在).{0,20}(库存|订单|设备|状态|数量)|"
        r"(inventory|order|equipment).{0,20}(current|live|status))"
    )
    LIVE_FACT_KEY_PREFIXES = ("inventory.", "order.current", "equipment.current")

    def __init__(
        self,
        store: MemoryStore,
        *,
        default_ttl: timedelta = timedelta(days=90),
        short_term_ttl: timedelta = timedelta(days=1),
    ) -> None:
        self.store = store
        self.default_ttl = default_ttl
        self.short_term_ttl = short_term_ttl

    async def write_candidate(
        self,
        identity: IdentityContext,
        *,
        memory_key: str | None = None,
        content: str,
        memory_type: str,
        user_confirmed: bool,
        source: str,
        ttl: timedelta | None = timedelta(days=90),
        confidence: float = 1.0,
        source_refs: tuple[str, ...] = (),
        warehouse_ids: tuple[str, ...] = (),
        required_scopes: tuple[str, ...] = (),
    ) -> MemoryItem | None:
        normalized_content = content.strip()
        key = memory_key or self._content_key(memory_type, normalized_content)
        candidate = MemoryCandidate(
            memory_key=key,
            content=normalized_content,
            memory_type=memory_type,
            user_confirmed=user_confirmed,
            source=source,
            ttl_seconds=int(ttl.total_seconds()) if ttl is not None else None,
            confidence=confidence,
            source_refs=source_refs,
            warehouse_ids=warehouse_ids,
            required_scopes=required_scopes,
        )
        item, _reason = await self._store_candidate(
            identity, candidate, apply_default_ttl=False
        )
        return item

    async def extract_and_store(
        self, run_result: dict[str, Any], identity: IdentityContext
    ) -> MemoryWriteReport:
        turns_written = await self._write_short_term_turns(run_result, identity)
        context = _mapping(_mapping(run_result.get("request")).get("context"))
        raw_candidates = context.get("memory_candidates") or ()
        stored_ids = []
        rejections = []
        run_id = str(_mapping(run_result.get("run")).get("run_id") or "")
        for raw in raw_candidates:
            try:
                candidate = MemoryCandidate.model_validate(raw)
            except ValidationError:
                rejections.append(
                    MemoryRejection(
                        memory_key="unknown", reason_code="invalid_candidate"
                    )
                )
                continue
            # Candidates in request.context originate at the user/API trust
            # boundary and cannot promote themselves to system-approved memory.
            if candidate.source != "user":
                rejections.append(
                    MemoryRejection(
                        memory_key=candidate.memory_key,
                        reason_code="untrusted_source",
                    )
                )
                continue
            if run_id and run_id not in candidate.source_refs:
                candidate = candidate.model_copy(
                    update={"source_refs": (*candidate.source_refs, run_id)}
                )
            item, reason = await self._store_candidate(
                identity, candidate, apply_default_ttl=True
            )
            if item is None:
                rejections.append(
                    MemoryRejection(
                        memory_key=candidate.memory_key,
                        reason_code=reason or "policy_rejected",
                    )
                )
            else:
                stored_ids.append(item.memory_id)
        status = (
            "partial"
            if stored_ids and rejections
            else "succeeded" if stored_ids or turns_written else "skipped"
        )
        return MemoryWriteReport(
            status=status,
            stored_memory_ids=tuple(stored_ids),
            rejections=tuple(rejections),
            short_term_turns_written=turns_written,
        )

    async def _store_candidate(
        self,
        identity: IdentityContext,
        candidate: MemoryCandidate,
        *,
        apply_default_ttl: bool,
    ) -> tuple[MemoryItem | None, str | None]:
        reason = self._rejection_reason(identity, candidate)
        if reason is not None:
            return None, reason
        now = datetime.now(UTC)
        existing = await self.store.get_by_key(identity, candidate.memory_key)
        memory_id = (
            existing.memory_id if existing else self._memory_id(identity, candidate)
        )
        ttl_seconds = candidate.ttl_seconds
        if ttl_seconds is None and apply_default_ttl:
            ttl_seconds = int(self.default_ttl.total_seconds())
        expires_at = (
            now + timedelta(seconds=ttl_seconds) if ttl_seconds is not None else None
        )
        item = MemoryItem(
            memory_id=memory_id,
            memory_key=candidate.memory_key.strip(),
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            memory_type=candidate.memory_type,
            content=candidate.content.strip(),
            source=candidate.source,
            source_refs=candidate.source_refs,
            confidence=candidate.confidence,
            acl=AccessControl(
                tenant_id=identity.tenant_id,
                warehouse_ids=candidate.warehouse_ids,
                required_scopes=candidate.required_scopes,
            ),
            created_at=existing.created_at if existing else now,
            updated_at=now,
            expires_at=expires_at,
            version=existing.version + 1 if existing else 1,
        )
        return await self.store.upsert(item), None

    def _rejection_reason(
        self, identity: IdentityContext, candidate: MemoryCandidate
    ) -> str | None:
        content = candidate.content.strip()
        lowered = content.lower()
        if candidate.source not in self.ALLOWED_SOURCES:
            return "untrusted_source"
        if not candidate.user_confirmed:
            return "confirmation_required"
        if candidate.memory_type not in self.ALLOWED_TYPES:
            return "unsupported_memory_type"
        if not content:
            return "empty_content"
        if any(marker in lowered for marker in self.INJECTION_MARKERS):
            return "prompt_injection"
        if self.SENSITIVE_PATTERN.search(content):
            return "sensitive_content"
        if self.LIVE_FACT_PATTERN.search(content) or candidate.memory_key.startswith(
            self.LIVE_FACT_KEY_PREFIXES
        ):
            return "realtime_fact_forbidden"
        if not set(candidate.warehouse_ids).issubset(identity.warehouse_scope):
            return "warehouse_scope_forbidden"
        if not set(candidate.required_scopes).issubset(identity.scopes):
            return "permission_scope_forbidden"
        return None

    async def _write_short_term_turns(
        self, run_result: dict[str, Any], identity: IdentityContext
    ) -> int:
        run = _mapping(run_result.get("run"))
        request = _mapping(run_result.get("request"))
        answer = _mapping(run_result.get("final_answer"))
        conversation_id = str(run.get("conversation_id") or "").strip()
        user_message = str(request.get("message") or "").strip()
        assistant_message = str(answer.get("message") or "").strip()
        if not conversation_id:
            return 0
        now = datetime.now(UTC)
        written = 0
        for role, content in (
            ("user", user_message),
            ("assistant", assistant_message),
        ):
            if not content:
                continue
            occurred_at = now + timedelta(microseconds=written)
            await self.store.append_turn(
                ConversationTurn(
                    turn_id=f"turn-{uuid4()}",
                    tenant_id=identity.tenant_id,
                    user_id=identity.user_id,
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                    created_at=occurred_at,
                    expires_at=occurred_at + self.short_term_ttl,
                )
            )
            written += 1
        return written

    @staticmethod
    def _memory_id(identity: IdentityContext, candidate: MemoryCandidate) -> str:
        digest = sha256(
            (
                f"{identity.tenant_id}:{identity.user_id}:"
                f"{candidate.memory_type}:{candidate.memory_key.strip()}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        return f"mem-{digest}"

    @staticmethod
    def _content_key(memory_type: str, content: str) -> str:
        digest = sha256(content.encode("utf-8")).hexdigest()[:20]
        return f"{memory_type}.{digest}"


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return {}
