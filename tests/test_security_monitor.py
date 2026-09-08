from __future__ import annotations

import pytest

from aggregator_demo import security_monitor
from aggregator_demo.security_monitor import security_events_request, validate_api_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://api:8000/", "http://api:8000"),
        ("https://monitor.example.test/base", "https://monitor.example.test/base"),
    ],
)
def test_validate_api_url_accepts_http_origins(value: str, expected: str) -> None:
    assert validate_api_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "file:///etc/passwd",
        "ftp://example.test/events",
        "api:8000",
        "http://user:password@example.test",
    ],
)
def test_validate_api_url_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        validate_api_url(value)


def test_security_events_request_adds_configured_bearer_key(monkeypatch) -> None:
    monkeypatch.setattr(security_monitor, "API_KEY", "auditor-test-key")
    request = security_events_request()
    assert request.get_header("Authorization") == "Bearer auditor-test-key"
    assert request.full_url.endswith("/api/v1/security/events?limit=200")
