from __future__ import annotations

import pytest

from src.api.services.document_v2.chunking import DifferentialChunker
from src.api.services.document_v2.models import DocumentElement, DocumentIR, PageProfile
from src.api.services.document_v2.parser_router import ParserRouter
from src.api.services.document_v2.quality_gate import DocumentQualityGate


def test_parser_router_uses_native_then_ocr_or_vlm_per_page() -> None:
    router = ParserRouter()
    decisions = router.route(
        (
            PageProfile(page_number=1, native_text_chars=1200, image_ratio=0.1),
            PageProfile(page_number=2, native_text_chars=4, image_ratio=0.95),
            PageProfile(
                page_number=3,
                native_text_chars=30,
                image_ratio=0.8,
                complex_table=True,
            ),
        )
    )

    assert [item.parser for item in decisions] == ["native", "ocr", "vlm"]


def test_quality_gate_rejects_empty_or_low_confidence_without_synthetic_content() -> (
    None
):
    gate = DocumentQualityGate(min_document_confidence=0.7)
    empty = DocumentIR(
        document_id="doc-empty", source_hash="a" * 64, parser_version="1"
    )
    assert gate.evaluate(empty).accepted is False

    low = empty.model_copy(
        update={
            "document_id": "doc-low",
            "elements": (
                DocumentElement(
                    element_id="e1",
                    page_number=1,
                    element_type="text",
                    text="unreadable",
                    reading_order=1,
                    parser="ocr",
                    confidence=0.4,
                    source_hash="b" * 64,
                ),
            ),
        }
    )
    report = gate.evaluate(low)
    assert report.accepted is False
    assert report.reprocess_pages == (1,)


def test_differential_chunker_preserves_sop_steps_and_table_headers() -> None:
    document = DocumentIR(
        document_id="doc-1",
        source_hash="c" * 64,
        parser_version="docling-2",
        elements=(
            DocumentElement(
                element_id="s1",
                page_number=1,
                element_type="sop_step",
                text="步骤1：关闭电源。",
                heading_path=("叉车维修",),
                reading_order=1,
                parser="native",
                confidence=0.99,
                source_hash="d" * 64,
            ),
            DocumentElement(
                element_id="t1",
                page_number=2,
                element_type="table",
                text="SKU|库存\nA|10\nB|20",
                table_headers=("SKU", "库存"),
                reading_order=2,
                parser="native",
                confidence=0.95,
                source_hash="e" * 64,
            ),
        ),
    )

    chunks = DifferentialChunker(child_tokens=100, parent_tokens=300).chunk(document)

    assert {item.chunk_type for item in chunks} == {"sop", "table"}
    table = next(item for item in chunks if item.chunk_type == "table")
    assert table.content.startswith("SKU | 库存")
    assert all(item.parent_id for item in chunks)
