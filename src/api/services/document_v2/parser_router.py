"""Page-level parser routing: native first, OCR selectively, VLM for complexity."""

from __future__ import annotations

from collections.abc import Iterable

from .models import PageProfile, ParseDecision


class ParserRouter:
    def __init__(self, *, native_text_threshold: int = 80) -> None:
        self.native_text_threshold = native_text_threshold

    def route(self, pages: Iterable[PageProfile]) -> tuple[ParseDecision, ...]:
        decisions = []
        for page in pages:
            if page.complex_table or page.handwriting:
                parser, reason = "vlm", "complex_layout_or_handwriting"
            elif page.native_text_chars >= self.native_text_threshold:
                parser, reason = "native", "extractable_text_layer"
            else:
                parser, reason = "ocr", "insufficient_native_text"
            decisions.append(
                ParseDecision(
                    page_number=page.page_number, parser=parser, reason=reason
                )
            )
        return tuple(decisions)
