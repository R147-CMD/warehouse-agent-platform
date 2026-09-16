"""Build explicitly segmented, trust-labelled model context."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from .trust_boundary_v2 import PromptEnvelope, PromptSection
from .trust_labels import RedactionReport, redact_with_report


class SegmentedPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sections: tuple[PromptSection, ...]
    rendered: str
    redaction: RedactionReport


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


class PromptContextBuilder:
    """Keep instructions separate from user/evidence/tool data and redact secrets."""

    def build(
        self,
        system: str,
        user: str,
        evidence: Any = (),
        tool_output: Any = (),
    ) -> SegmentedPrompt:
        values = (system, user, evidence, tool_output)
        redacted_values: list[Any] = []
        paths: list[str] = []
        total = 0
        for index, value in enumerate(values):
            redacted, report = redact_with_report(value)
            redacted_values.append(redacted)
            total += report.redacted_count
            paths.extend(f"section[{index}].{path}" for path in report.paths)

        sections = (
            PromptSection(
                kind="system",
                content=str(redacted_values[0]),
                trust="trusted_instruction",
            ),
            PromptSection(
                kind="user", content=str(redacted_values[1]), trust="user_input"
            ),
            PromptSection(
                kind="evidence",
                content=_serialize(redacted_values[2]),
                trust="untrusted_data",
            ),
            PromptSection(
                kind="tool_output",
                content=_serialize(redacted_values[3]),
                trust="untrusted_data",
            ),
        )
        envelope = PromptEnvelope(sections)
        return SegmentedPrompt(
            sections=sections,
            rendered=envelope.render(),
            redaction=RedactionReport(redacted_count=total, paths=tuple(paths)),
        )
