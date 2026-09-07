# Public release review gate

No commit, push, publication or remote-infrastructure change is authorized by
this checklist. A human must review and explicitly approve those actions.

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
