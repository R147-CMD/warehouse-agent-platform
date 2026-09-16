"""Shadow-build and atomic-alias index activation contract."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .models import DocumentChunk


@dataclass(frozen=True)
class IndexVersion:
    index_id: str
    alias: str
    parser_version: str
    chunker_version: str
    embedding_version: str
    document_count: int
    chunk_count: int
    status: str


class InMemoryShadowIndex:
    """Reference implementation used by tests and local development."""

    def __init__(self) -> None:
        self._indexes: dict[str, tuple[DocumentChunk, ...]] = {}
        self._aliases: dict[str, str] = {}

    async def build_shadow(
        self,
        alias: str,
        chunks: tuple[DocumentChunk, ...],
        *,
        embedding_version: str,
    ) -> IndexVersion:
        signature = ":".join(
            [alias, embedding_version, *(item.chunk_id for item in chunks)]
        )
        index_id = "idx-" + sha256(signature.encode("utf-8")).hexdigest()[:24]
        self._indexes[index_id] = chunks
        return IndexVersion(
            index_id=index_id,
            alias=alias,
            parser_version=chunks[0].parser_version if chunks else "unknown",
            chunker_version=chunks[0].chunker_version if chunks else "unknown",
            embedding_version=embedding_version,
            document_count=len({item.document_id for item in chunks}),
            chunk_count=len(chunks),
            status="shadow",
        )

    async def activate(self, version: IndexVersion) -> IndexVersion:
        if version.index_id not in self._indexes:
            raise LookupError("shadow index not found")
        self._aliases[version.alias] = version.index_id
        return IndexVersion(**{**version.__dict__, "status": "active"})

    def resolve(self, alias: str) -> tuple[DocumentChunk, ...]:
        index_id = self._aliases.get(alias)
        return self._indexes.get(index_id, ()) if index_id else ()
