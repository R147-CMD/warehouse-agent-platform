from __future__ import annotations

from src.api.services.security.trust_labels import redact_with_report


def test_secret_redaction_removes_nested_credentials_and_reports_paths() -> None:
    redacted, report = redact_with_report(
        {
            "Authorization": "Bearer top-secret",
            "nested": {"password": "pw", "safe": "ok"},
            "items": [{"access_token": "token"}],
        }
    )

    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["items"][0]["access_token"] == "[REDACTED]"
    assert report.redacted_count == 3
    assert "nested.password" in report.paths


def test_secret_like_strings_are_redacted_before_prompt_or_trace() -> None:
    redacted, report = redact_with_report("Authorization: Bearer abc.def.ghi")

    assert "abc.def.ghi" not in redacted
    assert report.redacted_count == 1
