"""Trust labels and secret redaction for model-visible payloads."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TrustLabel = Literal[
    "trusted_instruction", "user_input", "trusted_data", "untrusted_data"
]

_SECRET_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "client_secret",
    "access_token",
    "refresh_token",
    "csrf_token",
    "cookie",
}
_SECRET_TEXT = re.compile(
    r"(?i)(\b(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+"
    r"|(\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;]+"
)


class RedactionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    redacted_count: int = Field(default=0, ge=0)
    paths: tuple[str, ...] = ()


def _redact(value: Any, path: str, paths: list[str]) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text.lower().replace("-", "_") in _SECRET_KEYS:
                result[key] = "[REDACTED]"
                paths.append(child_path)
            else:
                result[key] = _redact(item, child_path, paths)
        return result
    if isinstance(value, (list, tuple)):
        items = [
            _redact(item, f"{path}[{index}]", paths) for index, item in enumerate(value)
        ]
        return tuple(items) if isinstance(value, tuple) else items
    if isinstance(value, str):
        redacted = _SECRET_TEXT.sub(
            lambda match: f"{match.group(1) or match.group(2)}[REDACTED]", value
        )
        if redacted != value:
            paths.append(path or "<text>")
        return redacted
    return value


def redact_with_report(value: Any) -> tuple[Any, RedactionReport]:
    """Return a deep-redacted copy and an auditable count of changed fields."""

    paths: list[str] = []
    redacted = _redact(value, "", paths)
    return redacted, RedactionReport(redacted_count=len(paths), paths=tuple(paths))
