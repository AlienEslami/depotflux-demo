from __future__ import annotations

import pytest

from aggregator_demo.settings import RuntimeSettings, parse_boolean, parse_origins


def test_runtime_settings_expose_only_safe_configuration() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "DEMO_DATABASE_URL": "postgresql+psycopg://user:secret@db/depotflux",
            "DEMO_AUTO_CREATE_SCHEMA": "false",
            "DEMO_ALLOWED_ORIGINS": "http://localhost:3000,https://demo.example.test/",
            "DEMO_ENVIRONMENT": "demo",
            "DEMO_LOG_LEVEL": "warning",
            "DEMO_METRICS_ENABLED": "true",
        }
    )
    summary = settings.safe_summary()
    assert summary["database_backend"] == "postgresql+psycopg"
    assert "secret" not in repr(summary)
    assert summary["allowed_origins"] == [
        "http://localhost:3000",
        "https://demo.example.test",
    ]


@pytest.mark.parametrize("value", ["*", "file:///tmp/data", "https://user:pass@test", "https://test/path"])
def test_origins_reject_non_origins(value: str) -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\) origins"):
        parse_origins(value)


def test_boolean_parser_is_strict() -> None:
    assert parse_boolean("yes", default=False, name="FLAG") is True
    assert parse_boolean(None, default=False, name="FLAG") is False
    with pytest.raises(ValueError, match="FLAG"):
        parse_boolean("sometimes", default=False, name="FLAG")
