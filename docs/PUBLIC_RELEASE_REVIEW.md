# Public release review gate

No commit, push, publication or remote-infrastructure change is authorized by
this checklist. A human must review and explicitly approve those actions.

## Automated review record — 2026-09-07

Candidate branch: `codex/industry-demonstrator`. The evidence named below is
stored under ignored `.demo/` and is not part of the release.

- The latest pushed GitHub CI run completed successfully.
- Gitleaks 8.30.1 scanned 118 commits and reported no detected secrets. A
  separate ZIP/XML scan of 91 tracked Office files found no credential or e-mail
  patterns.
- Machine-specific repository and Python paths were replaced with portable
  placeholders in nine tracked JSON manifests. Eighteen frozen result workbooks
  still contain local path strings in their provenance worksheets; changing
  those files would alter frozen research artifacts.
- `pip-audit` 2.10.1 found no known vulnerabilities in either pinned Python
  lockfile. `npm audit` found no known dashboard vulnerabilities.
- Bandit 1.9.4 reported no findings in `aggregator_demo`. The single suppressed
  URL-opening rule is guarded by explicit HTTP(S)-only URL validation and tests.
- Trivy 0.74.0 generated CycloneDX SBOMs and reported zero fixable high or
  critical vulnerabilities in the rebuilt API, dashboard and PostgreSQL images.
- The Python suite passed 235 tests. The only warning is an upstream
  Starlette/httpx test-client deprecation. The frozen-package validator passed.
- Dashboard install, audit, lint, TypeScript check and production build passed.
  The build reports a non-blocking large-chunk optimization warning.
- A clean seven-service Compose build became healthy. The approved-dispatch,
  rejection, replay and emergency-safe-state smoke flow passed. Network
  isolation passed: only the OT gateway could resolve and connect to the
  synthetic PLC.
- Browser inspection passed at the default desktop size and at 390 x 844: no
  horizontal overflow or duplicate IDs were found, exposed controls had
  accessible names, one heading/main/navigation landmark was present, keyboard
  focus reached navigation, and the browser console had no warnings or errors.
- Temporary review containers, networks, placeholder environment file and the
  synthetic PostgreSQL volume were removed after verification.

## Owner decisions still required

Release status remains **hold** until these items are decided and recorded:

1. Choose the repository's software and data/documentation licences. No licence
   is currently granted.
2. Confirm that every paper artifact, input workbook, workflow export and frozen
   result may be redistributed, including any co-author or institutional rights.
3. Choose whether the portfolio repository should retain the inherited 118-
   commit research history or be recreated from a clean, attributed snapshot.
   The inherited history includes a collaborator's public commit identity and
   older machine-specific provenance paths.
4. Decide whether the 18 frozen workbooks' machine-specific provenance strings
   should remain for audit fidelity or be rebuilt/redacted before publication.
5. Complete an independent human contrast/usability/accessibility review and
   configure a private vulnerability-reporting channel when the repository
   becomes public.

## Blocking checks

- Search current files and full Git history for API keys, credentials, e-mail
  addresses, private hostnames, tokens, licences and environment files.
- Confirm `.demo/`, `.env*`, database files, logs and evidence with synthetic
  operator identifiers are excluded from release.
- Generate an SBOM; scan Python, npm, base images and OS packages; assess every
  high/critical result and record accepted residual risk.
- Review third-party licences, paper/data rights, solver terms, screenshots and
  generated artifacts. Add an explicit repository licence only with owner input.
- Recheck that no documentation implies NIST/IEC/ISO compliance, certification,
  achieved IEC 62443 security level, field validation, functional safety,
  production readiness, live SIEM use or physical control.
- Independent reviewer traces security requirements to tests and reruns the
  exact clean migration, full suite, dashboard build, Compose smoke and network
  isolation checks.
- Threat-model review covers authentication, replay persistence, evidence
  integrity, host compromise, supply chain, denial of service and emergency use.
- Accessibility and browser review cover keyboard use, focus, contrast, errors,
  responsive layout and secret handling.
- API hardening review addresses strong identity/RBAC, rate limiting, TLS/mTLS,
  CSRF/origin behavior, secret rotation, audit authorization and safe error text.
- Operational review addresses backup/restore, retention, log volume, patching,
  rollback, monitoring ownership and incident contacts.

## Release decision record

Record reviewer names, commit digest, test/evidence artifact digests, unresolved
risks, approved wording, chosen licence, publication target, decision and UTC
date. Until that record is complete, describe the project as a local private
software demonstrator under development.
