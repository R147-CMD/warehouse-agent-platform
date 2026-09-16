"""Canonical action hashing and business idempotency helpers."""

from __future__ import annotations

import json
from hashlib import sha256

from src.api.domain.agent_protocols import ProposedAction


def action_hash(action: ProposedAction) -> str:
    canonical = json.dumps(
        action.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
