"""Authentication and session-bound CSRF support for the SAP EWM mock."""

from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request

from .odata import ODataRequestError


SESSION_COOKIE = "SAP_SESSIONID_MOCK"


class MockSecurity:
    """Validate Basic/Bearer credentials and issue CSRF sessions."""

    def __init__(self) -> None:
        self.username = os.getenv("SAP_EWM_MOCK_USERNAME", "mock-user")
        self.password = os.getenv("SAP_EWM_MOCK_PASSWORD", "mock-password")
        self.client_id = os.getenv("SAP_EWM_MOCK_CLIENT_ID", "mock-client")
        self.client_secret = os.getenv(
            "SAP_EWM_MOCK_CLIENT_SECRET", "mock-secret"
        )
        self._access_tokens: dict[str, datetime] = {}
        self._csrf_by_session: dict[str, str] = {}

    def reset(self) -> None:
        self._access_tokens.clear()
        self._csrf_by_session.clear()

    def authenticate(self, request: Request) -> None:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            if self._valid_basic(authorization[6:]):
                return
        elif authorization.startswith("Bearer "):
            if self._valid_bearer(authorization[7:]):
                return

        raise ODataRequestError(
            "AUTHENTICATION_REQUIRED", "Valid SAP credentials are required", 401
        )

    def issue_access_token(self, client_id: str, client_secret: str) -> str:
        if not (
            secrets.compare_digest(client_id, self.client_id)
            and secrets.compare_digest(client_secret, self.client_secret)
        ):
            raise ODataRequestError(
                "INVALID_CLIENT", "OAuth client authentication failed", 401
            )
        token = secrets.token_urlsafe(32)
        self._access_tokens[token] = datetime.now(timezone.utc) + timedelta(
            minutes=5
        )
        return token

    def issue_csrf(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(24)
        token = secrets.token_urlsafe(32)
        self._csrf_by_session[session_id] = token
        return session_id, token

    def verify_csrf(self, session_id: str | None, token: str | None) -> None:
        if not token:
            raise ODataRequestError(
                "CSRF_TOKEN_MISSING", "X-CSRF-Token is required", 403
            )
        expected = self._csrf_by_session.get(session_id or "")
        if not expected or not secrets.compare_digest(expected, token):
            raise ODataRequestError(
                "CSRF_TOKEN_INVALID", "CSRF token validation failed", 403
            )

    def _valid_basic(self, encoded: str) -> bool:
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        return secrets.compare_digest(
            username, self.username
        ) and secrets.compare_digest(password, self.password)

    def _valid_bearer(self, token: str) -> bool:
        expires_at = self._access_tokens.get(token)
        if expires_at is None:
            return False
        if expires_at <= datetime.now(timezone.utc):
            self._access_tokens.pop(token, None)
            return False
        return True
