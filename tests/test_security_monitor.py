from __future__ import annotations

import pytest

from aggregator_demo.security_monitor import validate_api_url


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
