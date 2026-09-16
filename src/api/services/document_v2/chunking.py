"""Differential chunking for body text, SOP steps, tables and images."""

from __future__ import annotations

from hashlib import sha256

from .models import DocumentChunk, DocumentElement, DocumentIR


def _tokens(text: str) -> list[str]:
    # Deterministic fallback estimator. Production tokenizers can implement this contract.
    return text.split() if " " in text else list(text)


class DifferentialChunker:
    VERSION = "differential-1.0"

    def __init__(
        self,
        *,
        child_tokens: int = 400,
        parent_tokens: int = 1_200,
        overlap_tokens: int = 60,
    ) -> None:
        if child_tokens < 1 or parent_tokens < child_tokens:
            raise ValueError("invalid child/parent token policy")
        self.child_tokens = child_tokens
        self.parent_tokens = parent_tokens
        self.overlap_tokens = min(overlap_tokens, max(0, child_tokens - 1))

    def chunk(self, document: DocumentIR) -> tuple[DocumentChunk, ...]:
        provisional: list[DocumentChunk] = []
        for element in sorted(document.elements, key=lambda item: item.reading_order):
            if not element.text.strip():
                continue
            chunk_type, contents = self._split_element(element)
            parent_key = "/".join(element.heading_path) or document.document_id
            parent_id = (
                "parent-"
                + sha256(
                    f"{document.document_id}:{parent_key}".encode("utf-8")
                ).hexdigest()[:24]
            )
            for index, content in enumerate(contents):
                chunk_id = (
                    "chunk-"
                    + sha256(
                        f"{document.source_hash}:{element.element_id}:{index}:{self.VERSION}".encode(
                            "utf-8"
                        )
                    ).hexdigest()[:24]
                )
                provisional.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        parent_id=parent_id,
                        chunk_type=chunk_type,
                        content=content,
                        heading_path=element.heading_path,
                        page_numbers=(element.page_number,),
                        element_ids=(element.element_id,),
                        token_count=max(1, len(_tokens(content))),
                        parser_version=document.parser_version,
                        chunker_version=self.VERSION,
                        source_hash=document.source_hash,
                    )
                )
        linked = []
        for index, item in enumerate(provisional):
            linked.append(
                item.model_copy(
                    update={
                        "previous_chunk_id": (
                            provisional[index - 1].chunk_id if index else None
                        ),
                        "next_chunk_id": (
                            provisional[index + 1].chunk_id
                            if index + 1 < len(provisional)
                            else None
                        ),
                    }
                )
            )
        return tuple(linked)

    def _split_element(self, element: DocumentElement) -> tuple[str, list[str]]:
        if element.element_type == "sop_step":
            return "sop", [element.text.strip()]
        if element.element_type == "table":
            body = element.text.strip().splitlines()
            header = " | ".join(element.table_headers)
            if body and "|" in body[0] and element.table_headers:
                body = body[1:]
            normalized = "\n".join([header, *body]) if header else element.text.strip()
            return "table", [normalized]
        if element.element_type in {"image", "caption"}:
            return "image", [element.text.strip()]
        tokens = _tokens(element.text.strip())
        if len(tokens) <= self.child_tokens:
            return "body", [element.text.strip()]
        step = self.child_tokens - self.overlap_tokens
        chunks = []
        for start in range(0, len(tokens), step):
            window = tokens[start : start + self.child_tokens]
            if not window:
                break
            separator = " " if " " in element.text else ""
            chunks.append(separator.join(window))
            if start + self.child_tokens >= len(tokens):
                break
        return "body", chunks
