"""Validated configuration for SAP EWM OData V4 connections."""

from __future__ import annotations

import os
from enum import Enum
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr, model_validator


class SAPAuthMode(str, Enum):
    """Authentication modes supported by the replaceable SAP integration."""

    BASIC = "basic"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"


class SAPEWMConfig(BaseModel):
    """Security-validated SAP EWM connection settings."""

    enabled: bool = False
    connection_id: str = Field(default="sap-ewm-default", min_length=1)
    mock_mode: bool = False
    base_url: AnyHttpUrl
    warehouse: str = Field(min_length=1)
    client: str = Field(default="100", min_length=1)
    auth_mode: SAPAuthMode = SAPAuthMode.BASIC
    username: str | None = None
    password: SecretStr | None = None
    token_url: AnyHttpUrl | None = None
    client_id: str | None = None
    client_secret: SecretStr | None = None
    scope: str | None = None
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    read_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    verify_tls: bool = True
    max_read_attempts: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def validate_security(self) -> "SAPEWMConfig":
        """Reject insecure real connections and incomplete credentials."""

        scheme = urlsplit(str(self.base_url)).scheme.lower()
        if not self.mock_mode and scheme != "https":
            raise ValueError("Real SAP EWM connections require HTTPS")
        if not self.mock_mode and not self.verify_tls:
            raise ValueError("TLS verification can only be disabled in mock mode")

        if self.auth_mode is SAPAuthMode.BASIC and not (
            self.username and self.password
        ):
            raise ValueError("Basic auth requires username and password")

        if self.auth_mode is SAPAuthMode.OAUTH2_CLIENT_CREDENTIALS and not (
            self.token_url and self.client_id and self.client_secret
        ):
            raise ValueError(
                "OAuth2 requires token_url, client_id, and client_secret"
            )

        return self

    @classmethod
    def from_env(cls) -> "SAPEWMConfig":
        """Build a validated connection from the process environment."""

        return cls(
            enabled=_env_bool("SAP_EWM_ENABLED", False),
            connection_id=os.getenv(
                "SAP_EWM_CONNECTION_ID", "sap-ewm-default"
            ),
            mock_mode=_env_bool("SAP_EWM_MOCK_MODE", False),
            base_url=os.environ["SAP_EWM_BASE_URL"],
            warehouse=os.environ["SAP_EWM_WAREHOUSE"],
            client=os.getenv("SAP_EWM_CLIENT", "100"),
            auth_mode=os.getenv("SAP_EWM_AUTH_MODE", "basic"),
            username=os.getenv("SAP_EWM_USERNAME"),
            password=os.getenv("SAP_EWM_PASSWORD"),
            token_url=os.getenv("SAP_EWM_TOKEN_URL"),
            client_id=os.getenv("SAP_EWM_CLIENT_ID"),
            client_secret=os.getenv("SAP_EWM_CLIENT_SECRET"),
            scope=os.getenv("SAP_EWM_SCOPE"),
            connect_timeout_seconds=float(
                os.getenv("SAP_EWM_CONNECT_TIMEOUT_SECONDS", "5")
            ),
            read_timeout_seconds=float(
                os.getenv("SAP_EWM_READ_TIMEOUT_SECONDS", "15")
            ),
            verify_tls=_env_bool("SAP_EWM_VERIFY_TLS", True),
            max_read_attempts=int(
                os.getenv("SAP_EWM_MAX_READ_ATTEMPTS", "3")
            ),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
