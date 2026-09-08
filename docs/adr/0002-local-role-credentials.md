# ADR 0002: Use role-scoped local credentials

Status: Accepted — 2026-09-07

## Context

Anonymous mutation and caller-supplied actor names do not demonstrate meaningful
authorization. A full external identity provider would make the local lab hard
to reproduce and could imply production identity maturity.

## Decision

Use four independently generated local Bearer credentials mapped to fixed
operator, approver, auditor and administrator identities. Keep separate control,
emergency and gateway secrets. Default library/test mode remains explicitly
disabled; Compose enables API-key mode.

## Consequences

Separation of duties and least privilege are testable without an external
service. Key rotation is a local restart operation, and production OIDC, user
lifecycle management and MFA remain outside the demonstrator boundary.
