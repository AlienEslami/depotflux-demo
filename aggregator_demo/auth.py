from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from hmac import compare_digest
from typing import Mapping


class AuthMode(StrEnum):
    DISABLED = "disabled"
    API_KEY = "api_key"


class Role(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    ADMIN = "admin"


class AuthenticationError(RuntimeError):
    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role


@dataclass(frozen=True)
class ServiceAccount:
    subject: str
    role: Role
    api_key: str


_SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")
_KEY_ENVIRONMENT_NAMES = {
    Role.OPERATOR: "DEMO_OPERATOR_API_KEY",
    Role.APPROVER: "DEMO_APPROVER_API_KEY",
    Role.AUDITOR: "DEMO_AUDITOR_API_KEY",
    Role.ADMIN: "DEMO_ADMIN_API_KEY",
}
_SUBJECT_ENVIRONMENT_NAMES = {
    Role.OPERATOR: "DEMO_OPERATOR_ID",
    Role.APPROVER: "DEMO_APPROVER_ID",
    Role.AUDITOR: "DEMO_AUDITOR_ID",
    Role.ADMIN: "DEMO_ADMIN_ID",
}


@dataclass(frozen=True)
class AuthConfig:
    mode: AuthMode
    accounts: tuple[ServiceAccount, ...] = ()

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "AuthConfig":
        values = os.environ if environ is None else environ
        raw_mode = values.get("DEMO_AUTH_MODE", AuthMode.DISABLED.value).strip().lower()
        try:
            mode = AuthMode(raw_mode)
        except ValueError as exc:
            raise ValueError("DEMO_AUTH_MODE must be 'disabled' or 'api_key'") from exc
        if mode is AuthMode.DISABLED:
            return cls(mode=mode)

        accounts: list[ServiceAccount] = []
        for role in Role:
            key_name = _KEY_ENVIRONMENT_NAMES[role]
            api_key = values.get(key_name, "")
            if len(api_key) < 20:
                raise ValueError(f"{key_name} must contain at least 20 characters")
            subject = values.get(
                _SUBJECT_ENVIRONMENT_NAMES[role], f"depotflux-{role.value}"
            ).strip()
            if not _SUBJECT_PATTERN.fullmatch(subject):
                raise ValueError(
                    f"{_SUBJECT_ENVIRONMENT_NAMES[role]} must be a safe 1-128 character identifier"
                )
            accounts.append(ServiceAccount(subject=subject, role=role, api_key=api_key))

        if len({account.api_key for account in accounts}) != len(accounts):
            raise ValueError("role API keys must be unique")
        if len({account.subject for account in accounts}) != len(accounts):
            raise ValueError("role account identifiers must be unique")
        return cls(mode=mode, accounts=tuple(accounts))

    def authenticate(
        self,
        authorization: str | None,
        *,
        development_subject: str = "demo-operator",
    ) -> Principal:
        if self.mode is AuthMode.DISABLED:
            subject = development_subject.strip() or "demo-operator"
            if not _SUBJECT_PATTERN.fullmatch(subject):
                raise AuthenticationError(
                    "X-Operator-ID is not a valid identifier",
                    code="invalid_actor",
                    status_code=400,
                )
            return Principal(subject=subject, role=Role.ADMIN)

        scheme, separator, token = (authorization or "").partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise AuthenticationError(
                "A Bearer access key is required",
                code="authentication_required",
                status_code=401,
            )
        matched: ServiceAccount | None = None
        for account in self.accounts:
            if compare_digest(token, account.api_key):
                matched = account
        if matched is None:
            raise AuthenticationError(
                "The supplied access key is invalid",
                code="invalid_access_key",
                status_code=401,
            )
        return Principal(subject=matched.subject, role=matched.role)


def require_role(principal: Principal, allowed_roles: set[Role]) -> None:
    if principal.role not in allowed_roles:
        allowed = ", ".join(sorted(role.value for role in allowed_roles))
        raise AuthenticationError(
            f"Role '{principal.role.value}' is not allowed; expected one of: {allowed}",
            code="insufficient_role",
            status_code=403,
        )
