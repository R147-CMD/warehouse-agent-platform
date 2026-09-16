from datetime import UTC, datetime


def _identity(warehouse_scope=("WH-01",)):
    from src.api.domain.identity import IdentityContext

    return IdentityContext(
        tenant_id="tenant-a",
        user_id="user-1",
        username="operator",
        roles=("operator",),
        scopes=("inventory.read",),
        warehouse_scope=warehouse_scope,
        authenticated_at=datetime.now(UTC),
    )


def test_query_understanding_preserves_identifiers_and_resolves_today():
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    now = datetime(2026, 9, 7, 10, 30, tzinfo=UTC)
    envelope = QueryUnderstandingService().parse(
        "查询 WH-01 今天 WO-202609-001 的状态",
        _identity(),
        now,
    )

    assert envelope.query_type == "structured_fact"
    assert envelope.protected_terms == ("WH-01", "WO-202609-001")
    assert envelope.time_range is not None
    assert envelope.time_range.start.isoformat() == "2026-09-07T00:00:00+00:00"
    assert envelope.filters["tenant_id"] == "tenant-a"
    assert envelope.filters["warehouse_ids"] == ["WH-01"]


def test_query_understanding_marks_ambiguous_equipment_query():
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    envelope = QueryUnderstandingService().parse(
        "设备有没有坏？",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert envelope.query_type == "structured_fact"
    assert [item.field_name for item in envelope.missing_inputs] == [
        "equipment_id_or_area"
    ]


def test_query_understanding_routes_fact_plus_sop_to_hybrid():
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    envelope = QueryUnderstandingService().parse(
        "查询 EQ-03 当前故障状态，并给出处置 SOP",
        _identity(),
        datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert envelope.query_type == "hybrid"
    assert {entity.entity_type for entity in envelope.entities} == {"equipment"}


def test_query_understanding_never_expands_identity_warehouse_scope():
    from src.retrieval.v2.query_understanding import QueryUnderstandingService

    envelope = QueryUnderstandingService().parse(
        "查询 WH-99 的库存",
        _identity(("WH-01",)),
        datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert envelope.filters["warehouse_ids"] == ["WH-01"]
    assert "WH-99" in envelope.unauthorized_terms
