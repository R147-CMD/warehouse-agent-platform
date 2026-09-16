"""Quality gate that requests reprocessing instead of fabricating content."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import DocumentIR


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    document_confidence: float
    reprocess_pages: tuple[int, ...] = ()
    reasons: tuple[str, ...] = ()


class DocumentQualityGate:
    def __init__(
        self,
        *,
        min_element_confidence: float = 0.6,
        min_document_confidence: float = 0.75,
    ) -> None:
        self.min_element_confidence = min_element_confidence
        self.min_document_confidence = min_document_confidence

    def evaluate(self, document: DocumentIR) -> QualityReport:
        if not document.elements:
            return QualityReport(
                accepted=False,
                document_confidence=0.0,
                reasons=("no_elements_extracted",),
            )
        confidence = sum(item.confidence for item in document.elements) / len(
            document.elements
        )
        reprocess = tuple(
            sorted(
                {
                    item.page_number
                    for item in document.elements
                    if item.confidence < self.min_element_confidence
                    or not item.text.strip()
                }
            )
        )
        reasons = []
        if confidence < self.min_document_confidence:
            reasons.append("document_confidence_below_threshold")
        if reprocess:
            reasons.append("low_quality_pages")
        return QualityReport(
            accepted=not reasons,
            document_confidence=confidence,
            reprocess_pages=reprocess,
            reasons=tuple(reasons),
        )
