from datetime import UTC, datetime


def _evidence(evidence_id: str):
    from src.api.domain.evidence_protocols import EvidenceRef
    from src.api.domain.identity import AccessControl

    return EvidenceRef(
        evidence_id=evidence_id,
        evidence_type="structured_record",
        source_system="wms",
        source_locator={"id": evidence_id},
        observed_at=datetime.now(UTC),
        trust_level="authoritative",
        content_hash="a" * 64,
        acl=AccessControl(tenant_id="tenant-a"),
    )


def _result(task_id: str, summary: str):
    from src.api.domain.agent_protocols import AgentResult

    return AgentResult(
        task_id=task_id,
        status="succeeded",
        summary=summary,
        confidence=0.9,
    )


def test_agent_results_merge_by_task_id_with_latest_update():
    from src.api.graphs.state_v2 import merge_agent_results

    merged = merge_agent_results(
        [_result("task-b", "old"), _result("task-a", "a")],
        [_result("task-b", "new")],
    )

    assert [item.task_id for item in merged] == ["task-a", "task-b"]
    assert merged[1].summary == "new"


def test_evidence_refs_are_deduplicated_by_evidence_id():
    from src.api.graphs.state_v2 import merge_evidence_refs

    merged = merge_evidence_refs(
        [_evidence("ev-b"), _evidence("ev-a")],
        [_evidence("ev-b")],
    )

    assert [item.evidence_id for item in merged] == ["ev-a", "ev-b"]
