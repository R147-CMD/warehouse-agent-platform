"""End-to-end document ingestion orchestration without synthetic success."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .chunking import DifferentialChunker
from .indexing import InMemoryShadowIndex, IndexVersion
from .models import DocumentIR, PageProfile
from .parser_router import ParserRouter
from .quality_gate import DocumentQualityGate, QualityReport


class DocumentIngestionResult:
    def __init__(
        self,
        *,
        document: DocumentIR,
        quality: QualityReport,
        index: IndexVersion | None,
    ) -> None:
        self.document = document
        self.quality = quality
        self.index = index


class DocumentIngestionPipeline:
    def __init__(
        self,
        parsers: dict[str, Callable[..., Any]],
        *,
        router: ParserRouter | None = None,
        quality_gate: DocumentQualityGate | None = None,
        chunker: DifferentialChunker | None = None,
        index: InMemoryShadowIndex | None = None,
    ) -> None:
        self.parsers = parsers
        self.router = router or ParserRouter()
        self.quality_gate = quality_gate or DocumentQualityGate()
        self.chunker = chunker or DifferentialChunker()
        self.index = index or InMemoryShadowIndex()

    async def ingest(
        self,
        document_id: str,
        pages: tuple[PageProfile, ...],
        source: bytes,
        *,
        alias: str,
        embedding_version: str,
    ) -> DocumentIngestionResult:
        decisions = self.router.route(pages)
        elements = []
        parser_versions = set()
        for decision in decisions:
            parser = self.parsers.get(decision.parser)
            if parser is None:
                raise RuntimeError(f"required {decision.parser} parser is unavailable")
            parsed = parser(source, decision.page_number)
            if hasattr(parsed, "__await__"):
                parsed = await parsed
            page_elements, parser_version = parsed
            elements.extend(page_elements)
            parser_versions.add(parser_version)
        from hashlib import sha256

        document = DocumentIR(
            document_id=document_id,
            source_hash=sha256(source).hexdigest(),
            parser_version="+".join(sorted(parser_versions)),
            elements=tuple(elements),
        )
        quality = self.quality_gate.evaluate(document)
        if not quality.accepted:
            return DocumentIngestionResult(
                document=document, quality=quality, index=None
            )
        chunks = self.chunker.chunk(document)
        shadow = await self.index.build_shadow(
            alias, chunks, embedding_version=embedding_version
        )
        active = await self.index.activate(shadow)
        return DocumentIngestionResult(document=document, quality=quality, index=active)
