"""Contracts for SAP EWM configuration, domain models, and errors."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.adapters.wms.sap_ewm_config import SAPAuthMode, SAPEWMConfig
from src.adapters.wms.sap_ewm_errors import SAPEWMError, SAPEWMErrorCode
from src.adapters.wms.sap_ewm_models import SAPPage, SAPStockItem, SAPWriteResult


def basic_config(**overrides):
    values = {
        "enabled": True,
        "mock_mode": True,
        "base_url": "http://127.0.0.1:8010",
        "warehouse": "EW01",
        "client": "100",
        "auth_mode": "basic",
        "username": "mock-user",
        "password": "mock-password",
    }
    values.update(overrides)
    return values


def test_real_connection_rejects_http() -> None:
    with pytest.raises(ValidationError, match="require HTTPS"):
        SAPEWMConfig(**basic_config(mock_mode=False))


def test_real_connection_rejects_disabled_tls_verification() -> None:
    with pytest.raises(ValidationError, match="TLS verification"):
        SAPEWMConfig(
            **basic_config(
                mock_mode=False,
                base_url="https://sap.example.test",
                verify_tls=False,
            )
        )


def test_mock_connection_allows_http_and_redacts_secrets() -> None:
    config = SAPEWMConfig(**basic_config())

    assert config.password is not None
    assert config.password.get_secret_value() == "mock-password"
    assert "mock-password" not in repr(config)
    assert str(config.base_url).rstrip("/") == "http://127.0.0.1:8010"


def test_basic_auth_requires_username_and_password() -> None:
    values = basic_config()
    values.pop("username")
    values.pop("password")

    with pytest.raises(ValidationError, match="Basic auth"):
        SAPEWMConfig(**values)


def test_oauth_requires_token_endpoint_and_client_credentials() -> None:
    values = basic_config(auth_mode="oauth2_client_credentials")
    values.pop("username")
    values.pop("password")

    with pytest.raises(ValidationError, match="OAuth2"):
        SAPEWMConfig(**values)


def test_from_env_parses_security_and_retry_settings(monkeypatch) -> None:
    environment = {
        "SAP_EWM_ENABLED": "true",
        "SAP_EWM_CONNECTION_ID": "sap-ewm-test",
        "SAP_EWM_MOCK_MODE": "true",
        "SAP_EWM_BASE_URL": "http://sap-ewm-mock:8010",
        "SAP_EWM_WAREHOUSE": "EW01",
        "SAP_EWM_CLIENT": "100",
        "SAP_EWM_AUTH_MODE": "basic",
        "SAP_EWM_USERNAME": "mock-user",
        "SAP_EWM_PASSWORD": "mock-password",
        "SAP_EWM_CONNECT_TIMEOUT_SECONDS": "2.5",
        "SAP_EWM_READ_TIMEOUT_SECONDS": "8",
        "SAP_EWM_VERIFY_TLS": "false",
        "SAP_EWM_MAX_READ_ATTEMPTS": "4",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    config = SAPEWMConfig.from_env()

    assert config.enabled is True
    assert config.connection_id == "sap-ewm-test"
    assert config.auth_mode is SAPAuthMode.BASIC
    assert config.connect_timeout_seconds == 2.5
    assert config.read_timeout_seconds == 8
    assert config.verify_tls is False
    assert config.max_read_attempts == 4


def test_stock_page_serializes_decimal_without_losing_domain_fields() -> None:
    page = SAPPage[SAPStockItem](
        items=[
            SAPStockItem(
                warehouse="EW01",
                sku="TG11",
                storage_bin="T010-02-05-A",
                storage_section="S001",
                quantity=Decimal("956.5"),
                unit="EA",
                stock_item_uuid="stock-uuid-1",
            )
        ],
        next_cursor="cursor-1",
    )

    payload = page.model_dump(mode="json")
    assert payload == {
        "items": [
            {
                "warehouse": "EW01",
                "sku": "TG11",
                "storage_bin": "T010-02-05-A",
                "storage_section": "S001",
                "batch": None,
                "quantity": "956.5",
                "unit": "EA",
                "stock_item_uuid": "stock-uuid-1",
            }
        ],
        "next_cursor": "cursor-1",
    }


def test_unknown_write_outcome_is_explicit_and_not_retriable() -> None:
    error = SAPEWMError.unknown_outcome("SAP write response was not received")

    assert error.code is SAPEWMErrorCode.SAP_OUTCOME_UNKNOWN
    assert error.retriable is False
    assert error.outcome_unknown is True
    assert str(error) == "SAP write response was not received"

    result = SAPWriteResult(
        operation="assign_warehouse_order",
        entity_id="2000005003",
        status="ASSIGNED",
        outcome_confirmed_by_readback=True,
    )
    assert result.outcome_confirmed_by_readback is True
