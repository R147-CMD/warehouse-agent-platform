def _feature_flags_type():
    from src.api.services.feature_flags import FeatureFlags

    return FeatureFlags


def test_v2_feature_flags_default_to_disabled(monkeypatch):
    for name in (
        "WAREHOUSE_AGENT_RUNTIME_V2_ENABLED",
        "WAREHOUSE_RETRIEVAL_V2_ENABLED",
        "WAREHOUSE_EXECUTION_V2_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    flags = _feature_flags_type().from_env()

    assert flags.agent_runtime_v2_enabled is False
    assert flags.retrieval_v2_enabled is False
    assert flags.execution_v2_enabled is False


def test_v2_feature_flags_accept_explicit_truthy_values(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_RUNTIME_V2_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_RETRIEVAL_V2_ENABLED", "1")
    monkeypatch.setenv("WAREHOUSE_EXECUTION_V2_ENABLED", "ON")

    flags = _feature_flags_type().from_env()

    assert flags.agent_runtime_v2_enabled is True
    assert flags.retrieval_v2_enabled is True
    assert flags.execution_v2_enabled is True


def test_v2_feature_flags_fail_closed_for_unknown_values(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_RUNTIME_V2_ENABLED", "enabled")
    monkeypatch.setenv("WAREHOUSE_RETRIEVAL_V2_ENABLED", "maybe")
    monkeypatch.setenv("WAREHOUSE_EXECUTION_V2_ENABLED", "2")

    flags = _feature_flags_type().from_env()

    assert flags.agent_runtime_v2_enabled is False
    assert flags.retrieval_v2_enabled is False
    assert flags.execution_v2_enabled is False
