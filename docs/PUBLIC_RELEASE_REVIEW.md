# Public release review gate

This checklist does not authorize a visibility change, merge, tag or public
release. Those actions require an explicit owner decision.

## Owner publication decision — 2026-09-14 UTC

The owner explicitly authorized publication of the GridTwin dynamics candidate
and selected MIT to match the retained upstream. The exact local candidate
passed 106 Python tests, OpenAPI checking, dashboard lint/type/build, the
dynamics evidence gate, Bandit, pip-audit and npm audit. Generated evidence was
rescanned after converting coverage paths to relative form; no workstation-path
or high-signal credential filename matches remained.

Known residual limitations accepted for a portfolio release: Docker was
unavailable for the exact rebuilt-image CVE lookup, GitHub CI can only be
observed after push, and no independent human usability/security review was
performed in this session. Public visibility does not imply production,
security, safety, field or standards validation.

## GridTwin local candidate review — 2026-09-09 UTC

- The full Python suite passed 97 tests in 188.69 seconds with 73.681% combined
  line/branch coverage; OpenAPI drift, dashboard lint/type-check/build and the
  Docker/HiGHS evidence gate passed.
- Four npm high-severity paths were traced to transitive `sharp` 0.35.2. A
  narrow override to patched 0.35.4 passed clean install and build checks;
  `npm audit` then reported zero known findings. No force or disruptive package
  downgrade was used.
- `pip-audit` reported zero known findings across 50 resolved Python packages.
  npm, Python and exact rebuilt-image CycloneDX inventories are committed under
  `evidence/release/`.
- The current tree and local reachable history had no matches for the reviewed
  private-key and high-signal provider-token forms. Publication-claim contexts
  were all explicit limitations on compliance, certification,
  production, field, safety, employment or physical-control claims.
- Docker Scout indexed the rebuilt API, dashboard and database images and wrote
  their SBOMs, but CVE lookup required an unapproved Docker ID login. Image/OS
  CVE assessment therefore remains open.
- The owner selected MIT on 2026-09-14, matching the retained MIT-licensed
  Agentic-Aggregator upstream. The root notice and package metadata now record
  the decision. Third-party packages retain their own terms.

Detailed results and limits are in
`docs/GRIDTWIN_RELEASE_HARDENING_REPORT.md`. Release status is **hold**.

## Candidate review record — 2026-09-07

Candidate branch: `codex/software-v0.1`. Generated evidence is stored under
ignored `.demo/` and is not part of the release.

- The product-focused Python suite passed 83 tests. The only warning is an
  upstream Starlette/httpx test-client deprecation.
- A `depotflux-0.1.0` wheel built successfully, contained only the application
  package and its synthetic fixtures, and imported from a separate installation
  directory.
- `pip-audit` 2.10.1 and `npm audit` found no known dependency
  vulnerabilities. Bandit 1.9.4 reported no findings; its five narrow
  suppressions document fixed-command execution, HTTP(S)-validated monitoring,
  and deliberate optional-solver fallback behavior.
- Dashboard lint, TypeScript checking and production build passed. The build
  reports a non-blocking large-chunk optimization warning.
- OpenAPI generation/check, Compose rendering, Python compilation, YAML parsing
  and all lifecycle PowerShell parser checks passed.
- The seven-service Compose lab rebuilt and reached its expected running and
  healthy states. Deterministic bootstrap completed successfully.
- The authenticated smoke flow passed approved dispatch, invalid credential,
  invalid interval, replay, stale command and administrator safe-state cases.
- Network isolation passed: the API, worker and monitor could not resolve the
  PLC, while the gateway connected to it.
- A 200-request, concurrency-10 authenticated read workload completed with zero
  errors, 244.923 requests/second and 69.784 ms p95 latency on the review host.
- API and worker restart recovered readiness and reloaded a persisted run.
- A content-digested backup restored 2 runs, 1 approval, 6 dispatch attempts
  and 6 security events transactionally; the lab returned to its expected
  running/healthy states.

The previous private-branch review also found no committed secrets and no
fixable high/critical findings in its image scan. Because the GridTwin candidate
changes the source and images, the exact publication commit must still pass CI
and the currently blocked image/OS CVE assessment before public release.

## Owner decisions still required

The earlier hold items and their current disposition are:

1. **Completed 2026-09-14:** choose the software and documentation licence. MIT
   was selected to match the retained upstream.
2. Publish from a clean product snapshot, or explicitly accept the inherited
   research history and verify that every historical artifact, identity and
   provenance path may be redistributed. A clean public snapshot is the safer
   default; the private research history can remain preserved separately.
3. Complete an independent human usability/accessibility review and enable a
   private vulnerability-reporting channel before changing visibility.

## Final release checks

- Pass GitHub CI on the exact candidate commit.
- Scan the exact candidate and full history chosen for publication for secrets,
  credentials, personal information and private infrastructure identifiers.
- Generate an SBOM and scan the final Python, npm, base-image and OS dependency
  set; assess every high/critical result.
- Verify third-party licences and solver redistribution terms against the
  owner's selected repository licence.
- Recheck that no documentation implies NIST/IEC/ISO compliance,
  certification, field validation, functional safety, production readiness,
  live SIEM use or physical control.
- Have an independent reviewer rerun the clean migration, full suite, dashboard
  build, Compose smoke, network isolation, backup/restore and recovery checks.
- Review authentication, replay persistence, evidence integrity, host
  compromise, supply chain, denial of service and emergency-use residual risks.
- Review keyboard use, focus, contrast, error presentation, responsive layout
  and secret handling.

## Release decision record

Record reviewer names, commit digest, CI and scan URLs, evidence digests,
unresolved risks, chosen licence, publication target, decision and UTC date.
Until that record is complete, describe DepotFlux as a local private software
demonstrator under development.
