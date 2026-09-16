from __future__ import annotations

import re

SESSION_ID_MAX_LENGTH = 128
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RESERVED_SESSION_IDS = {"default"}


def validate_session_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("session_id must be a string")
    if value.casefold() in _RESERVED_SESSION_IDS:
        raise ValueError("session_id must identify a unique conversation")
    if not _SESSION_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "session_id must be 1-128 safe characters and start with a letter or digit"
        )
    return value
