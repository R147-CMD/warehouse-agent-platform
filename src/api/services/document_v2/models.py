"""Layout-preserving, source-addressable document intermediate representation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x0: float
    y0: float
    x1: float
    y1: float


class PageProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int = Field(ge=1)
    native_text_chars: int = Field(default=0, ge=0)
    image_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    complex_table: bool = False
    handwriting: bool = False


class ParseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int
    parser: Literal["native", "ocr", "vlm"]
    reason: str


class DocumentElement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    element_id: str
    page_number: int = Field(ge=1)
    element_type: Literal["title", "text", "sop_step", "table", "image", "caption"]
    text: str
    heading_path: tuple[str, ...] = ()
    bbox: BoundingBox | None = None
    reading_order: int = Field(ge=0)
    parser: Literal["native", "ocr", "vlm"]
    confidence: float = Field(ge=0.0, le=1.0)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    table_headers: tuple[str, ...] = ()


class DocumentIR(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str
    title: str | None = None
    elements: tuple[DocumentElement, ...] = ()
    schema_version: str = "1.0"


class DocumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    document_id: str
    parent_id: str
    chunk_type: Literal["body", "sop", "table", "image"]
    content: str
    heading_path: tuple[str, ...] = ()
    page_numbers: tuple[int, ...]
    element_ids: tuple[str, ...]
    token_count: int = Field(ge=1)
    parser_version: str
    chunker_version: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
