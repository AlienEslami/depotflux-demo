# GridTwin release and evidence checklist

No item in this checklist authorizes publishing, pushing, cloud deployment,
research disclosure or physical connection.

## Minimum evidence gate

- [x] Read the prior development handoff and inspect repository status/history.
- [x] Preserve and reuse the existing EV optimizer, API, dashboard, Docker,
  approval, telemetry and test architecture.
- [x] Add CIGRE MV AC feeder, named depot and one BESS.
- [x] Record uncontrolled, cost-only and grid-constrained measured results.
- [x] Validate the scaled feeder base case and grid-constrained result.
- [x] Add real `pymodbus` FC10/FC03 path and test it over TCP.
- [x] Add false-data injection and unauthorized set-point scenarios.
- [x] Add constraint-aware detection, denial, safe fallback and audit hash chain.
- [x] Add APIs, dashboard panel, scripts and one-command Compose path.
- [x] Add architecture, requirements/acceptance/traceability, threat/risk and
  IEC/NIST concept-mapping documents.
- [x] Record a fresh full Python regression with JUnit and coverage artifacts:
  97 passed in 188.69 seconds; 73.681% combined line/branch coverage.
- [x] Record dashboard lint, type-check and production build.
- [x] Regenerate and verify the committed OpenAPI contract.
- [x] Build/start the complete Compose environment and run the Docker command.
- [x] Run a non-disclosing high-signal secret/history scan and manually review
  all publication-claim hits.
- [x] Inventory direct dependency licences and generate npm, Python and rebuilt
  image SBOMs under `evidence/release/`.
- [x] Run npm and Python advisory checks: both reported zero known findings in
  their scanner/database scope on 2026-09-09 UTC.
- [ ] Complete the exact rebuilt-image CVE scan. Docker Scout SBOM generation
  passed, but CVE lookup required a Docker ID login that was not authorized.
- [ ] Owner selects and approves a repository licence.

## Local release-hardening record

- [x] Investigated four npm high-severity paths and traced them to transitive
  `sharp` 0.35.2 under the current Cloudflare/Miniflare dependency graph.
- [x] Applied only a tested `sharp` 0.35.4 override; no forced update,
  major-version change or Cloudflare downgrade.
- [x] Rebuilt all seven Compose services and regenerated canonical HiGHS plus
  optional local Gurobi evidence.
- [x] Recorded review scope, limitations and release blockers in
  `docs/GRIDTWIN_RELEASE_HARDENING_REPORT.md`.

## Four-week scope still not completed

- Forecasting with held-out chronological evaluation versus a seasonal naive
  baseline and MAE/RMSE.
- Public-market backtesting and P&L attribution.
- Joint EV+BESS grid-constrained optimization or AC OPF; current implementation
  retains the EV schedule and optimizes BESS against an AC-derived envelope.
- N-1/component-outage evidence.
- IEC 61850-oriented asset map and example SCL artifact.
- Replay and objective-integrity cases are retained from DepotFlux; they have not
  yet been rerun as part of a four-attack GridTwin scorecard.
- Optional PV, OpenDSS adapter, durable shared replay state, external IAM,
  authenticated service transport, signed/WORM evidence and live SIEM exercise.
- Demo video/animated walkthrough, independent review and any tested cloud path.

Public release remains **hold**. The completed local checks do not replace the
owner licence decision, image/OS CVE assessment, independent review or CI on the
exact publication candidate.
