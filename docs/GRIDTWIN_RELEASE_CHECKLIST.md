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
  97 passed; 73.681% combined line/branch coverage.
- [x] Record dashboard lint, type-check and production build.
- [x] Regenerate and verify the committed OpenAPI contract.
- [x] Build/start the complete Compose environment and run the Docker command.
- [ ] Run secret/history, dependency licence, SBOM/CVE and publication-claim
  reviews before any public release.
- [ ] Owner selects and approves a repository licence.

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
