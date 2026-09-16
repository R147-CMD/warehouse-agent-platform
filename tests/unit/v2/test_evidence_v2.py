from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.api.domain.evidence_protocols import EntityRef
from src.api.domain.identity import AccessControl, IdentityContext
from src.api.services.evidence_v2.claim_validator import ClaimValidator
from src.api.services.evidence_v2.citation_mapper import CitationMapper
from src.api.services.evidence_v2.models import Evidence
from src.api.services.evidence_v2.resolver import EvidenceResolver
from src.api.services.evidence_v2.store import InMemoryEvidenceStore

NOW = datetime.now(UTC)


def identity() -> IdentityContext:
    return IdentityContext(
        tenant_id="t1",
        user_id="u1",
        scopes=("inventory.read",),
        warehouse_scope=("WH-01",),
        authenticated_at=NOW,
    )


def evidence(
    source: str, value: int, observed_at: datetime, trust="verified"
) -> Evidence:
    return Evidence.create(
        evidence_type="structured_record",
        source_system=source,
        source_locator={"table": "stock", "row": "SKU-1"},
        content={"sku": "SKU-1", "quantity": value},
        entity_refs=(
            EntityRef(entity_type="sku", entity_id="SKU-1", source_system=source),
        ),
        observed_at=observed_at,
        event_time=observed_at,
        source_version="7",
        trust_level=trust,
        acl=AccessControl(
            tenant_id="t1",
            warehouse_ids=("WH-01",),
            required_scopes=("inventory.read",),
        ),
    )


@pytest.mark.asyncio
async def test_store_is_immutable_and_enforces_acl() -> None:
    store = InMemoryEvidenceStore()
    item = evidence("sap_ewm", 12, NOW)
    await store.append(item)
    await store.append(item)

    assert await store.get(item.ref.evidence_id, identity()) == item
    assert len(await store.query(identity(), entity_type="sku", entity_id="SKU-1")) == 1

    foreign = identity().model_copy(update={"tenant_id": "t2"})
    assert await store.get(item.ref.evidence_id, foreign) is None


def test_resolver_prefers_authoritative_source_then_freshness() -> None:
    old_sap = evidence("sap_ewm", 12, NOW - timedelta(hours=1), "authoritative")
    new_cache = evidence("cache", 20, NOW, "verified")

    resolution = EvidenceResolver(
        source_priority={"quantity": ("sap_ewm", "cache")}
    ).resolve((old_sap, new_cache), field="quantity")

    assert resolution.selected == old_sap
    assert resolution.conflicted is True
    assert resolution.reason == "source_priority"


def test_claim_validation_and_stable_citation() -> None:
    item = evidence("sap_ewm", 12, NOW, "authoritative")
    claim = ClaimValidator().validate(
        statement="SKU-1 当前库存为 12",
        subject=item.ref.entity_refs[0],
        predicate="quantity",
        value=12,
        evidence=(item,),
    )
    citation = CitationMapper().map(claim)[0]

    assert claim.status == "supported"
    assert claim.confidence >= 0.9
    assert citation.evidence_id == item.ref.evidence_id
    assert CitationMapper().map(claim)[0].citation_id == citation.citation_id
