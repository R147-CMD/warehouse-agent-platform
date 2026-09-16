from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


def _types():
    from src.api.domain.evidence_protocols import (
        Citation,
        Claim,
        EntityRef,
        EvidenceRef,
    )
    from src.api.domain.identity import AccessControl

    return {
        "AccessControl": AccessControl,
        "Citation": Citation,
        "Claim": Claim,
        "EntityRef": EntityRef,
        "EvidenceRef": EvidenceRef,
    }


def _evidence(types):
    return types["EvidenceRef"](
        evidence_id="ev-1",
        evidence_type="structured_record",
        source_system="sap_ewm",
        source_locator={"entity_set": "WarehouseTask", "key": "WT-1"},
        entity_refs=(
            types["EntityRef"](entity_type="warehouse_task", entity_id="WT-1"),
        ),
        observed_at=datetime.now(UTC),
        trust_level="authoritative",
        content_hash="a" * 64,
        acl=types["AccessControl"](
            tenant_id="tenant-a",
            warehouse_ids=("WH-01",),
            required_scopes=("warehouse.task.read",),
        ),
    )


def test_evidence_rejects_invalid_validity_interval():
    types = _types()
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        types["EvidenceRef"](
            evidence_id="ev-1",
            evidence_type="document_chunk",
            source_system="knowledge_base",
            source_locator={"chunk_id": "chunk-1"},
            observed_at=now,
            valid_from=now,
            valid_to=now - timedelta(days=1),
            trust_level="verified",
            content_hash="b" * 64,
            acl=types["AccessControl"](tenant_id="tenant-a"),
        )


def test_supported_claim_requires_supporting_evidence():
    types = _types()

    with pytest.raises(ValidationError):
        types["Claim"](
            claim_id="claim-1",
            statement="WT-1 is confirmed",
            status="supported",
            confidence=0.9,
        )

    evidence = _evidence(types)
    claim = types["Claim"](
        claim_id="claim-1",
        statement="WT-1 is confirmed",
        status="supported",
        confidence=0.9,
        supporting_evidence=(evidence,),
    )
    citation = types["Citation"](
        citation_id="cite-1",
        claim_id=claim.claim_id,
        evidence_id=evidence.evidence_id,
        label="SAP EWM warehouse task WT-1",
    )

    assert citation.evidence_id == "ev-1"
