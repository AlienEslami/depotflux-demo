# GridTwin requirements, acceptance criteria and traceability

Status: minimum evidence sprint. `Pass` means automated local evidence exists;
it is not a field, safety, certification or compliance assessment.

## Stakeholders and user stories

- As a fleet operator, I need economic schedules evaluated against feeder limits
  before approval so that a lower-cost schedule is not silently treated as
  electrically acceptable.
- As an OT defender, I need reported telemetry compared with a trusted physical
  estimate so that plausible-but-false voltage values can be rejected.
- As an approver, I need every accepted and rejected set-point tied to a result
  digest, actor, reason and recovery outcome.
- As a reviewer, I need a credential-free offline experiment, exact inputs,
  measured baselines and tests so that portfolio claims can be reproduced.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion | Status |
|---|---|---|---|
| GT-F-001 | Use an open distribution feeder | CIGRE MV network loads and topology build through pandapower 3.5.4 | Pass |
| GT-F-002 | Connect the existing EV depot and one BESS | Named EV import/V2G and 500 kWh/250 kW storage exist at Bus 11 | Pass |
| GT-F-003 | Compare three dispatch cases | Uncontrolled, cost-optimized and grid-constrained cases cover the same 48×30-minute horizon | Pass |
| GT-F-004 | Enforce grid limits | Grid-constrained result has zero 0.95–1.05 pu and >100% thermal violation intervals | Pass |
| GT-F-005 | Report operating/economic evidence | Cost, revenue, peaks, losses, violations, throughput and solve time are present in JSON and Markdown | Pass |
| GT-F-006 | Preserve service feasibility | Retained EV MILP validation passes and reported unserved energy remains zero | Pass |
| GT-OT-001 | Use a real `pymodbus` TCP path | Library client completes FC10 write and FC03 read against the loopback PLC simulator | Pass |
| GT-SEC-001 | Detect false-data injection | 0.99 pu forged value is flagged against the 0.945715 pu trusted estimate | Pass |
| GT-SEC-002 | Deny unauthorized unsafe set-point | Real gateway credential/range gates reject the 1,621.545 kW case and the TCP-backed integration probe observes zero Modbus requests | Pass |
| GT-SEC-003 | Recover to a validated state | Safe set-point is 1,371.545 kW with zero remaining grid violations | Pass |
| GT-SEC-004 | Preserve auditable evidence | Canonical records form a verified SHA-256 previous-record chain | Pass |
| GT-API-001 | Expose grid and attack workflows | Metadata, experiment and paired-attack API routes are in the versioned OpenAPI contract | Pass |
| GT-DEP-001 | Provide one-command local execution | `./scripts/depotflux.ps1 gridtwin` builds/starts Compose and creates evidence | Pass |
| GT-NF-001 | Run offline without private data | Bundled deterministic synthetic fixture and packaged benchmark need no credentials or external API | Pass |
| GT-NF-002 | Preserve claim boundaries | UI/docs state software-only, synthetic, no direct asset control, no compliance | Pass |
| GT-NF-003 | Preserve existing behavior | Pre-change 83-test baseline and post-change full regression must pass | Pass: 106 tests |
| GT-DYN-001 | Connect the retained schedule to a transparent electrical dynamic model | Highest-import EV/BESS interval drives a source, feeder R-L, PCC capacitance, charger and BESS averaged dq model | Pass |
| GT-DYN-002 | Exercise required disturbances | Load change, source sag, cleared three-phase fault and inverter trip produce deterministic V/I/f/P/Q traces | Pass |
| GT-DYN-003 | Apply explicit response criteria | Each scenario records recovery and voltage/current/frequency pass/fail checks plus violation durations | Pass |
| GT-DYN-004 | Establish numerical credibility | Analytical two-bus check passes and the selected 25 µs step matches a 6.25 µs reference within declared tolerances | Pass |
| GT-DYN-005 | Return violations to replanning | Failed BESS-trip planning screen emits the existing per-charger derating structured-facts contract | Pass |
| GT-DYN-006 | Generate a reviewable report | One command writes JSON, Markdown, parameter/results tables and SVG response/sensitivity plots | Pass |

## Requirements-to-test traceability

| Requirement | Automated verification | Evidence artifact |
|---|---|---|
| GT-F-001, GT-F-002 | `tests/test_gridtwin_feeder.py::test_cigre_feeder_contains_named_depot_and_bess` | `evidence/gridtwin/results.json` → `grid` |
| GT-F-004 | `test_hosting_limit_separates_unsafe_and_conservative_imports`; full integration test | `evidence/gridtwin/results.md` scenario table |
| GT-F-003, GT-F-005, GT-F-006 | `tests/test_gridtwin_integration.py` | `evidence/gridtwin/results.json` → `scenarios` |
| GT-OT-001 | `tests/test_pymodbus_path.py` | request/readback test output |
| GT-SEC-001–003 | `tests/test_gridtwin_security.py`; `tests/test_pymodbus_path.py::test_gateway_rejects_unauthorized_and_unsafe_setpoints_without_modbus_transmission`; full evidence integration test | `evidence/gridtwin/results.json.security` |
| GT-SEC-004 | `test_audit_chain_detects_tampering` | `evidence/gridtwin/audit.jsonl` |
| GT-API-001 | `tests/test_gridtwin_api.py`; `test_openapi_contract.py` | `openapi/depotflux-v1.json` |
| GT-DEP-001 | Compose config, image build and `depotflux.ps1 gridtwin` | `evidence/gridtwin/results.json`; seven running services after execution |
| GT-NF-001, GT-NF-002 | integration assertions and public-release review | source fixture digest; claim-boundary document |
| GT-NF-003 | `scripts/verify_gridtwin.ps1` | `evidence/verification/test-results.xml`, `coverage.json`, `coverage.xml` |
| GT-DYN-001–003 | `tests/test_gridtwin_dynamics.py::test_required_dynamic_scenarios_are_stable_and_meet_declared_criteria` | `evidence/grid-dynamics/results.json` → `scenarios` |
| GT-DYN-004 | `test_operating_point_matches_closed_form_two_bus_baseline`; `test_selected_solver_step_and_finer_steps_match_reference` | `results.json` → `validation` and `step-sensitivity.svg` |
| GT-DYN-005 | `test_contingency_violation_returns_bounded_reschedule_feedback` | `results.json` → `schedule_feedback.replanning_structured_facts` |
| GT-DYN-006 | `tests/test_grid_dynamics_evidence_script.py` | `evidence/grid-dynamics/technical-report.md` and both SVG plots |

## Minimum gate decision

The implementation gate requires: all three scenarios complete; retained EV
optimizer used; grid-constrained AC result has no limit violations; both attacks
produce expected detection/denial and recovery; audit chain validates; all
Python/dashboard/OpenAPI checks pass; and the Docker path is exercised. The gate
passed on 2026-09-08: 97 Python tests passed, the OpenAPI drift check was current,
dashboard lint/type-check/production build passed, and the Docker/HiGHS command
generated the canonical evidence bundle. The one warning is an upstream
Starlette TestClient deprecation; the dashboard build also reports a non-blocking
large-chunk advisory.

The averaged dynamics extension gate passed on 2026-09-14: all four response
criteria sets, the analytical baseline, the selected-step/finer-step comparisons,
the report generator and the full 106-test Python regression passed. The 50
microsecond coarse sensitivity failures remain visible in the generated report
and do not satisfy the documented selected-step rule.
