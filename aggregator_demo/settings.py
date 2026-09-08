from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

from .auth import AuthConfig
from .database import DEFAULT_DATABASE_URL


def parse_boolean(value: str | None, *, default: bool, name: str) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def parse_origins(value: str) -> tuple[str, ...]:
    origins: list[str] = []
    for raw_origin in value.split(","):
        origin = raw_origin.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "DEMO_ALLOWED_ORIGINS must contain HTTP(S) origins without paths or credentials"
            )
        if origin not in origins:
            origins.append(origin)
    if not origins:
        raise ValueError("DEMO_ALLOWED_ORIGINS must contain at least one origin")
    return tuple(origins)


@dataclass(frozen=True)
class RuntimeSettings:
    database_url: str
    auto_create_schema: bool
    allowed_origins: tuple[str, ...]
    auth: AuthConfig
    environment: str
    log_level: str
    metrics_enabled: bool

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "RuntimeSettings":
        values = os.environ if environ is None else environ
        environment = values.get("DEMO_ENVIRONMENT", "development").strip().lower()
        if environment not in {"development", "test", "demo"}:
            raise ValueError("DEMO_ENVIRONMENT must be development, test, or demo")
        log_level = values.get("DEMO_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("DEMO_LOG_LEVEL is invalid")
        return cls(
            database_url=values.get("DEMO_DATABASE_URL", DEFAULT_DATABASE_URL),
            auto_create_schema=parse_boolean(
                values.get("DEMO_AUTO_CREATE_SCHEMA"),
                default=True,
                name="DEMO_AUTO_CREATE_SCHEMA",
            ),
            allowed_origins=parse_origins(
                values.get(
                    "DEMO_ALLOWED_ORIGINS",
                    "http://localhost:3000,http://127.0.0.1:3000",
                )
            ),
            auth=AuthConfig.from_environment(values),
            environment=environment,
            log_level=log_level,
            metrics_enabled=parse_boolean(
                values.get("DEMO_METRICS_ENABLED"),
                default=True,
                name="DEMO_METRICS_ENABLED",
            ),
        )

    def safe_summary(self) -> dict[str, object]:
        database_backend = self.database_url.split(":", 1)[0]
        return {
            "environment": self.environment,
            "database_backend": database_backend,
            "auto_create_schema": self.auto_create_schema,
            "allowed_origins": list(self.allowed_origins),
            "authentication_mode": self.auth.mode.value,
            "configured_roles": [account.role.value for account in self.auth.accounts],
            "log_level": self.log_level,
            "metrics_enabled": self.metrics_enabled,
        }
