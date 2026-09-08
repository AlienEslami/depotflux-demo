# Changelog

All notable changes to DepotFlux are recorded here. The format follows Keep a
Changelog and the project intends to use semantic versioning after the first
tagged release.

## Unreleased

### Added

- Role-separated operator, approver, auditor and administrator access.
- Structured request and worker logs, correlation IDs and Prometheus metrics.
- Safe configuration inspection, deterministic seeding and lifecycle command.
- Verified application backup/restore, API benchmark and restart recovery.
- Committed OpenAPI v1 contract with a CI freshness check.

### Changed

- Established a software-only product branch and removed research-only assets
  from its working tree while preserving them on the research branch.
- Moved optimization cores under the application package.

### Security

- Replaced caller-asserted identities for privileged actions with fixed,
  role-scoped service accounts when API-key mode is enabled.
