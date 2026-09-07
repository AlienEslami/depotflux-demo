# A Multi-Agentic Aggregator Design for Electric Bus Fleet Charging and Grid Flexibility Management

An energy optimizer can produce a feasible schedule and still create operational
risk if an unapproved, modified, stale, replayed or out-of-range result crosses
into an OT command path. **DepotFlux** demonstrates how to keep that boundary
human-approved, hash-bound, segmented, fail-closed and auditable.

This repository contains two related bodies of work: the DepotFlux industry
demonstrator and the frozen research package for *A Multi-Agentic Aggregator
Design for Electric Bus Fleet Charging and Grid Flexibility Management*
(TRC-26-02380).

## Industry demonstrator

DepotFlux is a local, software-only electric-fleet operations and OT security
lab around the research core. It executes registered optimization inputs,
preserves immutable operator decisions, derives a selected schedule interval,
passes it through an authenticated supervisory gateway, and exchanges real
Modbus/TCP frames with a synthetic PLC. Accepted and rejected attempts are
persisted with policy evidence and correlation IDs.

It has no physical I/O adapter and must not be aimed at live equipment.
`GET /api/v1/meta` reports `direct_asset_control=false`. The implementation does
not claim production readiness, compliance, certification, an achieved security
level, functional safety, field commissioning or live-SIEM validation.

### One-command local lab

Requirements: Windows PowerShell, Docker Desktop and Docker Compose.

```powershell
./scripts/start_ot_lab.ps1
```

The script generates local ephemeral secrets under ignored `.demo/`, builds the
seven-service lab, migrates an empty PostgreSQL database and waits for health.
It prints the dashboard key. Open `http://127.0.0.1:3000`; API documentation is
at `http://127.0.0.1:8000/docs`, and the read-only security summary is at
`http://127.0.0.1:9100/metrics/security-summary`.

Generate focused JUnit, Compose smoke and network-isolation evidence:

```powershell
./scripts/run_ot_evidence.ps1
```

### Architecture and evidence

The Compose topology separates enterprise/operator, industrial DMZ,
supervisory/EMS, control/PLC and monitoring networks. Only the dashboard, API
and monitor bind host loopback ports. The API, worker and monitor cannot resolve
the PLC; only the gateway can connect to its allowlisted control address.

The normal API never accepts an arbitrary setpoint. It derives power from the
approved result interval and enforces credential, successful-state, immutable
approval, result-digest, deterministic-validation, horizon and site-capacity
checks. The gateway adds time-window, replay, finite/range, response-validation,
timeout/retry and heartbeat controls. A separately credentialed emergency drill
uses an explicit zero-power safe-state mode.

- [Architecture, inventory, zones, conduits and register map](docs/OT_NETWORK_ARCHITECTURE.md)
- [Threat model, risk register, requirements and standards mappings](docs/OT_ASSURANCE_CASE.md)
- [Protocol specification and deterministic test matrix](docs/OT_PROTOCOL_TEST_PLAN.md)
- [Incident response and recovery playbook](docs/OT_INCIDENT_RESPONSE.md)
- [One-page portfolio case study](docs/PORTFOLIO_CASE_STUDY.md)
- [Interview demonstration script](docs/OT_DEMO_SCRIPT.md)
- [OT demonstrator work package and acceptance gates](docs/OT_INDUSTRY_DEMONSTRATOR_WORK_PACKAGE.md)
- [Public release review gate](docs/PUBLIC_RELEASE_REVIEW.md)
- [Sigma and KQL examples](detections/README.md)
- [Original demonstrator work package](docs/INDUSTRY_DEMONSTRATOR_WORK_PACKAGE.md)

The most important limitations are simplified synthetic process behavior,
shared-secret demonstrator authentication, an in-memory single-instance replay
cache, unauthenticated Modbus at the protocol layer, Docker rather than
industrial network controls, mutable database evidence, no safety engineering,
and no independent security or field testing. See the assurance case for the
full residual-risk and public-release gate.

Future backlog—not current capability: IEC 61850, a Microsoft Sentinel lab,
DNP3 or OPC UA, power-flow simulation, and Kubernetes deployment.

## Reproducing the revision (start here)

The revision experiments run natively in Python through the `agentic_workflow` package; no orchestration server is involved. The n8n exports under `workflows/` are retained as an archive of the original submission's orchestration and are not part of the reproduction path.

```powershell
git config core.autocrlf false   # frozen hashes are LF-based
python -m pip install -r requirements-dev-lock.txt
python -m pytest -q                              # expect all tests to pass
python scripts/validate_revision_package.py      # expect no failed checks
```

Per-study commands, frozen protocols and execution ceilings are in `docs/REVISION_EXPERIMENTS.md`; the current state of the revision and its remaining caveats are in `docs/REVISION_HANDOFF.md`. Published result tables and figures live under `paper_outputs/revision/` with a byte-hash manifest, and each study directory under `results/revision/` carries its own provenance manifest. The day-ahead case-study inputs are included under `data/inputs/`; the five real-time operational workbooks are excluded from version control and are available from the corresponding author on reasonable request.

## Abstract

Electric buses are becoming flexible energy assets, but their grid value depends on decisions that must adapt to service delays, battery states, electricity prices, and route-energy uncertainty. This paper proposes a multi-agentic aggregator framework that couples an optimization-based electric bus scheduling model with supervisory agents for pricing, disturbance mitigation, and schedule evaluation. The optimization core preserves bus-system operational feasibility across routes, chargers, batteries, and vehicle-to-grid exchanges, while the agentic layer determines when re-optimization is needed and how flexibility value is shared between the aggregator and the public transport operator.

## Repository Contents

```text
.
├── app.py                              # Day-ahead API and core PTO MILP model
├── app_rt.py                           # Real-time remaining-horizon optimizer API
├── generate_benchmark_files.py         # Builds day-ahead baseline and rolling RT workbooks
├── run_no_v2g_optimization.py          # Charging-only optimized baseline
├── run_dumb_charging.py                # Rule-like dumb-charging baseline
├── scripts/
│   └── reproduce_paper_results.py      # One-command deterministic reproduction runner
├── scenario_summary.py                 # Summary and reasoning-sheet metrics
├── requirements.txt                    # Python dependencies
├── data/
│   ├── inputs/                          # Canonical case-study inputs
│   └── intraday_prices/                 # RT price profiles by timestep
├── docs/
│   ├── PAPER_ABSTRACT.md
│   ├── PAPER_RESULTS.md
│   ├── REPO_AUDIT.md
│   └── REPRODUCIBILITY.md
├── paper_outputs/                     # Paper tables, RT outputs, prompt artifacts
├── workflows/
│   ├── day_ahead_workflow_prompt_analysis_baseline.json
│   ├── real_time_final.json
│   └── README.md
```

## File Usage

`data/inputs/case_study_inputs.xlsx` is the main replication workbook. Its sheets define global settings, buses, chargers, trips, prices, tariffs, and real-time fleet state. Use this file when reproducing the paper scenarios or adapting the workflow to a new fleet.

`data/inputs/spot_prices.xlsx` and `data/inputs/aggregator_tariffs.xlsx` decouple wholesale grid prices from aggregator buy/sell tariffs. Passing these files to the scripts makes the price inputs explicit and easier to audit.

`data/intraday_prices/` contains timestep-specific intraday price files used by the real-time workflow.

`results/` is used for regenerated benchmark files, JSON results, and local
reproduction summaries. Large and raw generated artifacts are ignored by Git;
the compact frozen Trigger v3 summaries and manifest are versioned for audit.

`workflows/` contains n8n exports for the agentic orchestration layer. These files preserve the workflow structure and prompts, but users must remap credentials, Google document IDs, and HTTP endpoint URLs before running them.

`paper_outputs/` contains the output workbooks and prompt artifacts used in the paper, renamed by paper section, strategy, mode, and scenario. The folder includes day-ahead Table 6 files, real-time disturbance files for Tables 7 and 9, combined-scenario files, prompt-sensitivity Table 14 files, and prompt templates.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The model is a MILP. The code attempts to use the first available solver from Gurobi, HiGHS, CBC, or GLPK. Gurobi was used during development; `highspy` is included for HiGHS-based replication where supported.

To enable Gurobi explicitly, install the optional binding and point it at a valid local license:

```bash
pip install -e ".[gurobi]"
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

On Windows PowerShell, set the license with `$env:GRB_LICENSE_FILE = "C:\path\to\gurobi.lic"` before running the workflow. Optimization outputs record `solver_name` so the selected solver is auditable.

## One-Command Reproduction

Run the deterministic Python-side reproduction package without overwriting the checked-in artifacts:

```bash
python scripts/reproduce_paper_results.py
```

This writes fresh outputs to `results/reproduction/`, including a `manifest.json`, a reproduction summary workbook, baseline JSON files, and regenerated day-ahead benchmark workbooks. The `results/` folder is ignored by git.

The revision reproduces the LLM-driven cases natively in Python; see `docs/REVISION_EXPERIMENTS.md`. The original submission's S3/S4 day-ahead cases were produced through the archived n8n workflows in `workflows/`; `docs/REPRODUCIBILITY.md` and `docs/PAPER_RESULTS.md` describe that historical path.

## Reproducing the Day-Ahead Baseline

```bash
python generate_benchmark_files.py \
  --input data/inputs/case_study_inputs.xlsx \
  --spot-prices-file data/inputs/spot_prices.xlsx \
  --tariffs-file data/inputs/aggregator_tariffs.xlsx \
  --output-dir results/day_ahead_benchmark \
  --summary-workbook results/day_ahead_local_comparison.xlsx
```

This appends summary rows to `results/day_ahead_local_comparison.xlsx` and regenerates the rolling benchmark workbooks.

## Reproducing Baseline Comparisons

Optimized charging without V2G:

```bash
python run_no_v2g_optimization.py \
  --input data/inputs/case_study_inputs.xlsx \
  --spot-prices-file data/inputs/spot_prices.xlsx \
  --output results/no_v2g_optimization_result.json \
  --summary-workbook results/day_ahead_local_comparison.xlsx
```

Dumb-charging benchmark:

```bash
python run_dumb_charging.py \
  --input data/inputs/case_study_inputs.xlsx \
  --spot-prices-file data/inputs/spot_prices.xlsx \
  --output results/dumb_charging_result.json \
  --summary-workbook results/day_ahead_local_comparison.xlsx
```

## Running the APIs

Day-ahead/core optimization API:

```bash
python app.py
```

Real-time optimization API:

```bash
python app_rt.py
```

Both services default to port `5002` unless `PORT` is set. The `/optimize` endpoints expect structured JSON input arrays for buses, chargers, trips, prices, tariffs, and real-time state. The n8n workflows are the intended bridge from Google Sheets/Drive or workbook-derived data to those API payloads.

## Running the real-time workflow without n8n

The standalone `agentic_workflow` package reproduces the real-time orchestration
locally from Excel workbooks and ZIP archives. It supports the original OpenAI
agents, a deterministic test backend, direct optimizer integration, optional
HTTP compatibility, checkpoints, and auditable Excel outputs.

See [`docs/PYTHON_WORKFLOW.md`](docs/PYTHON_WORKFLOW.md) for installation,
commands, input mapping, scenarios, and validation details.

The focused reviewer-response implementation is documented in
[`docs/REVISION_EXPERIMENTS.md`](docs/REVISION_EXPERIMENTS.md). It adds
standards-inspired service/charger notices, manual/rule/LLM information paths,
same-optimizer deterministic and agentic configurations, role-level ablations,
raw structured-output/retry logging, charger fault/derating updates, and a
controlled 192-decision uncertainty/chat benchmark with clean notices, single
messages, fragmented driver chats, and noisy/conflicting chats under
`inputs/revision/`. It includes frozen scenario-level development/test splits,
ranges, provisional values, corrections, conditional warnings, irrelevant
messages, and a deterministic uncertainty-to-optimizer policy. Isolated oracle,
numerical-only, stateful rule-text, and Agent-trigger-only configurations keep
pricing, evaluation, and optimization fixed for the causal Trigger comparison.
The earlier 120-decision v2 notice set is retained for sensitivity analysis.
The frozen held-out Trigger v3 results and their interpretation limits are in
[`docs/TRIGGER_V3_RESULTS.md`](docs/TRIGGER_V3_RESULTS.md).

Paired operational comparisons use a hidden common physical-event layer and
causal interval settlement: interval `t` is settled first, so a decision made
at `t` can affect only intervals `t+1` onward. The three decision-sensitive cases are (i) an
advance driver report of a late return, (ii) an advance maintenance chat for a
charger-bank isolation, and (iii) a fragmented combined late-return/charger
restriction with a later correction. Report time, physical onset, and first
sensor-detection time are separate. Future charger restrictions apply only to
their stated windows and late returns extend only trip return times. The cases are rebuilt
with `python scripts/build_closed_loop_notice_cases.py` and compared with
`python scripts/run_closed_loop_trigger_comparison.py`. Generated Excel
workbooks stay in ignored `results/` and are not committed.

## Workflow Replication

Import these n8n workflows:

- `workflows/day_ahead_workflow_prompt_analysis_baseline.json`
- `workflows/real_time_final.json`

After import, update:

- Google Sheets and Google Drive credentials
- Google document and folder IDs
- OpenAI credentials
- HTTP request URLs for the local or deployed API
- Sheet names if your replicated data source differs from `data/inputs/case_study_inputs.xlsx`

See `workflows/README.md` and `docs/REPRODUCIBILITY.md` for details.

## Model Summary

The optimization assigns buses to required trips, charging sessions, and optional V2G discharge sessions over discrete timesteps. It tracks battery energy for each bus, charger exclusivity, site charging limits, state-of-charge bounds, trip service requirements, end-of-day reserve, and tariff-based costs/revenues.

The day-ahead objective minimizes:

```text
sum_t S_buy[t] * w_buy[t] - sum_t S_sell[t] * w_sell[t]
```

where `S_buy` is the tariff paid by the public transport operator, `S_sell` is the V2G revenue tariff, `w_buy` is grid energy purchased, and `w_sell` is energy sold through V2G. The real-time optimizer adds service continuity, interruption, switching, and SOC-shortfall penalties for remaining-horizon rescheduling.

## Citation and License

Add the final paper citation and license before public release. If you want others to reuse the code, choose an explicit license such as MIT, Apache-2.0, or BSD-3-Clause.
