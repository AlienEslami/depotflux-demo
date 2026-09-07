# DepotFlux OT assurance case

Status: demonstrator assurance argument, not an assessment report
Scope: local, synthetic, software-only system described in
`OT_NETWORK_ARCHITECTURE.md`

## Claim and evidence strategy

The narrow claim is: **DepotFlux demonstrates a testable design for preventing
an unapproved or malformed optimization result from becoming a command to a
synthetic Modbus/TCP controller, while preserving correlated evidence for both
accepted and rejected attempts.**

The claim is supported by implemented policy checks, a segmented Compose model,
real socket protocol tests, negative scenarios, schema migrations, and
structured evidence. It does not claim IEC 62443 compliance, certification,
security level achievement, NIST compliance, production readiness, functional
safety, grid-code compliance, field experience, or control of real equipment.

## Security objectives

- Authorization: only a successful, validated, human-approved result may enter
  the regular dispatch path.
- Integrity: approval is bound to the current result SHA-256 value.
- Command validity: the server derives the setpoint; interval, finite value,
  site capacity, protocol representation, freshness and uniqueness are checked.
- Segmentation: only the supervisory gateway shares the PLC network.
- Availability and safe response: exchanges have bounded timeouts/retries;
  transport ambiguity or stale heartbeat causes a best-effort safe-state action.
- Accountability: attempts preserve actor, time, result hash, reason, command ID,
  correlation ID, policy checks, request/response frames and controller state.

## Threat model

| Threat event | Security consequence | Preventive/detective control | Evidence |
|---|---|---|---|
| Stolen or guessed dispatch key | Unauthorized schedule reaches control path | Separate key, constant-time comparison, fail-closed configuration | Persisted `invalid_credential`; API test |
| Operator dispatches an unapproved/rejected run | Bypass human authority | Immutable approval gate before encoding | `immutable_operator_approval`; negative test |
| Result changes after approval | Approval applies to different bytes | Approval-result hash comparison | `approval_result_hash`; negative test |
| Crafted interval/value | Out-of-plan or unsafe power request | Server-side derivation, horizon/finite/capacity checks | Policy checks; no frame on failure |
| Replayed command | Duplicate actuation | UUID replay cache at gateway | `replayed_command`; correlated event |
| Delayed or future command | Stale operational action | Issued/expiry window and clock-skew checks | `stale_command`/`future_command` |
| Direct PLC access | Bypass policy authority | Isolated control network plus peer CIDR allowlist | Network verifier; `direct_plc_access_rejected` log |
| Register reconnaissance | Discover/manipulate unintended state | Defined read shape; broad undefined reads rejected | `register_scan_rejected` log and unit test |
| Controller or conduit outage | Unknown command state, loss of visibility | Bounded retries, explicit failure, best-effort safe-state | `controller_exchange_failed`; transport tests |
| Frozen heartbeat | Undetected controller failure | Change detector and safe-state attempt | `controller_heartbeat_lost`; frozen-heartbeat test |
| Evidence store alteration | Misleading investigation record | DB constraints and correlation; no full tamper-proofing | Known residual risk; future signed/WORM evidence |
| Compromised container host | All logical zones bypassed | Out of scope for this Compose model | Explicit residual risk |

## ISO/IEC 27005-style risk register

This register borrows the risk-identification/treatment structure associated
with [ISO/IEC 27005:2022](https://www.iso.org/standard/80585.html). It is not an
ISO risk assessment and does not reproduce normative requirements. Scores use
a project scale: likelihood (L) and impact (I) from 1–5; score is L×I.

| ID | Risk owner | Initial L×I | Treatment demonstrated | Residual L×I | Disposition / evidence |
|---|---|---:|---|---:|---|
| R-01 | OT application owner | 4×5=20 | Approval + digest + server-derived setpoint | 2×5=10 | Reduce; API negative tests |
| R-02 | Identity owner | 4×4=16 | Separate control/emergency/gateway secrets | 3×4=12 | Reduce; production IAM remains required |
| R-03 | Network owner | 3×5=15 | Five zones, unexposed PLC, gateway-only conduit | 2×5=10 | Reduce; isolation JSON evidence |
| R-04 | Gateway owner | 4×4=16 | Freshness and bounded replay cache | 2×4=8 | Reduce; replay/stale tests; durable cache remains gap |
| R-05 | Operations owner | 3×5=15 | Timeout/retry and best-effort safe state | 2×5=10 | Reduce; no functional-safety claim |
| R-06 | Monitoring owner | 4×3=12 | Correlated structured events and example detections | 2×3=6 | Reduce; no live SIEM validation |
| R-07 | Data owner | 3×4=12 | Relational persistence and migration | 3×4=12 | Accept for demo; no signatures/WORM/PITR proof |
| R-08 | Platform owner | 3×5=15 | Non-root process, dropped caps, internal networks | 2×5=10 | Reduce; host compromise remains out of scope |
| R-09 | Product owner | 4×4=16 | Visible simulation boundary and claim restrictions | 2×4=8 | Reduce; release review required |
| R-10 | Supplier owner | 3×4=12 | Pinned top-level dependencies and interface contract | 2×4=8 | Reduce; SBOM/CVE/licence review required |

Residual scores are engineering judgments for prioritization, not measured
probabilities or acceptance by a real asset owner.

## Requirements and traceability

| Requirement | Verification | Implemented evidence |
|---|---|---|
| OT-REQ-01 `direct_asset_control=false` and no physical adapter | Contract/API test and architecture review | `/api/v1/meta`; synthetic-only classes |
| OT-REQ-02 regular commands derive from an approved schedule | API integration test | `DispatchEvidenceRepository.dispatch` |
| OT-REQ-03 approval binds current result hash | Mismatch negative test | `approval_result_hash` rejection |
| OT-REQ-04 interval, finite and capacity bounds fail closed | Range/horizon tests | Policy-check array; absent frame |
| OT-REQ-05 actual Modbus/TCP request/response occurs in simulation | Loopback and Compose smoke tests | FC10 frame, response frame, FC03 snapshot |
| OT-REQ-06 import/export are mutually exclusive | Codec/controller tests | Registers 100/101 validation |
| OT-REQ-07 emergency action is explicit and separately authorized | API test | Register 102 mode and emergency endpoint |
| OT-REQ-08 stale/future/replayed commands are refused | Gateway/API tests | Rejection reason and correlation ID |
| OT-REQ-09 timeouts/retries are bounded | Constructor and unreachable transport tests | Maximum three retries; explicit failure |
| OT-REQ-10 frozen/lost heartbeat is detected and safe state attempted | Frozen-heartbeat test | Alarm/state plus structured gateway log |
| OT-REQ-11 only gateway can reach PLC | Compose isolation test | `network-isolation.json` |
| OT-REQ-12 all valid-run command outcomes are durable | API persistence tests | `ot_dispatch_attempts` migration/table |
| OT-REQ-13 security-relevant outcomes are correlated | API event test | `security_events` table and dashboard |
| OT-REQ-14 clean database creation is migration-driven | Empty PostgreSQL startup | Alembic 0001→0007 logs |
| OT-REQ-15 operator can reproduce evidence with one command | Script execution | `scripts/run_ot_evidence.ps1` |

Verification sources:

- `tests/test_modbus_tcp_gateway.py`: frame format, TCP exchange, source/scan
  rejection, replay, stale, range, zero-versus-safe semantics, heartbeat.
- `tests/test_ot_dispatch_api.py`: approval-to-controller chain and durable
  accepted/rejected/failed evidence.
- `tests/test_demonstrator_ot_security.py`: retained frame-only compatibility
  endpoint and original approval checks.
- `scripts/compose_smoke.py`: migrated PostgreSQL, worker, API, gateway and PLC.
- `scripts/verify_network_isolation.py`: conduit allow/deny assertion.

## Standards and framework concept mapping

The mappings below are design aids only. A single demonstrator control can help
explain a concept without satisfying all normative requirements.

### NIST SP 800-82 Rev. 3

[NIST SP 800-82 Rev. 3](https://doi.org/10.6028/NIST.SP.800-82r3) provides OT
security guidance that accounts for performance, reliability and safety needs.

| Demonstrator evidence | Concept-level mapping |
|---|---|
| Zones, explicit conduits, no PLC host port | Network segmentation and boundary protection |
| Inventory and register/interface definition | Asset identification and architecture documentation |
| Approval/hash/range/freshness/replay gates | Access enforcement and application integrity |
| Structured logs, correlation and example analytics | Logging, monitoring and incident investigation |
| Heartbeat, retries and safe-state action | Availability-aware response and recovery planning |

### NIST Cybersecurity Framework 2.0

[NIST CSF 2.0](https://doi.org/10.6028/NIST.CSWP.29) is used as an outcome
vocabulary, not a conformance checklist.

| Function | Demonstrator artifacts |
|---|---|
| Govern | Scope, owners, claim restrictions, supplier requirements, residual risk |
| Identify | SUC, inventory, data flow, threats and risk register |
| Protect | Approval/hash gates, separate secrets, input validation, segmentation |
| Detect | Heartbeat/scan/replay events, Sigma and KQL examples |
| Respond | Triage playbook, correlation workflow, containment decision points |
| Recover | Zero-power recovery drill, restart/retest steps, evidence retention |

### IEC 62443 concepts

The project maps to selected concepts from IEC 62443-3-2 and 62443-3-3. The
[IEC 62443-3-2 product description](https://webstore.iec.ch/en/publication/30727)
describes SUC definition, zone/conduit partitioning and risk-based target
security levels. This project defines an SUC and zones/conduits, but it has not
performed the normative process, selected or verified an SL-T, assessed every
foundational requirement, or engaged an accredited assessor. Therefore it does
not claim IEC 62443 compliance or any achieved security level.

| Project control | IEC 62443 concept (non-normative) |
|---|---|
| Separate operator, DMZ, supervisory, control and monitoring networks | Zones and conduits |
| Distinct control/emergency/gateway credentials | Identification/authentication and use control concepts |
| Setpoint validation and result-hash binding | System integrity concept |
| Event persistence and correlation | Timely response to events concept |
| Internal-only PLC and minimal service paths | Restricted data flow concept |
| Timeout/heartbeat/safe-state behavior | Resource availability concept |

### MITRE ATT&CK for ICS

These are analyst mappings, not proof that an adversary was emulated. The
project references the official [ATT&CK for ICS technique catalog](https://attack.mitre.org/techniques/ics/).

| Observed scenario | Technique mapping | Rationale |
|---|---|---|
| Unsafe/out-of-range setpoint attempt | [T0836 Modify Parameter](https://attack.mitre.org/techniques/T0836/) | Attempts to change an operational parameter outside policy |
| Broad undefined register read | [T0846 Remote System Discovery](https://attack.mitre.org/techniques/T0846/) | Reconnaissance of controller-visible resources |
| Repeated direct service probes | [T0846.001 Remote System Discovery: Network Service Scanning](https://attack.mitre.org/techniques/T0846/001/) | Port/service discovery behavior |
| Controller/conduit loss or resource exhaustion drill | [T0814 Denial of Service](https://attack.mitre.org/techniques/T0814/) | Loss of expected availability/heartbeat |

## Supplier and interface requirements

Before a real controller, charging-management system or gateway could be
considered, its supplier would need to provide and contractually support:

- authoritative register/object model, signed types, scaling, endianness,
  command atomicity, rate limits, acknowledgement semantics and error behavior;
- safe default and loss-of-communications behavior agreed with the asset owner
  and functional-safety engineering authority;
- authenticated/encrypted management path or a compensating secure gateway;
- unique device identity, credential lifecycle, least-privilege roles and
  emergency-access process;
- time synchronization source and documented clock-failure behavior;
- signed update mechanism, vulnerability disclosure, patch support period,
  component inventory/SBOM, secure configuration and backup/restore procedure;
- log schema, severity, timestamp accuracy, retention/export capability and
  event-rate limits;
- availability, redundancy and recovery requirements validated in the target
  architecture; and
- test environment and written authorization for integration and security
  testing. No live equipment should be attached to this repository as-is.

## Residual risk and release decision

The main residual risks are demonstrator identity, in-memory replay state,
unauthenticated Modbus, host-level network bypass, mutable evidence, simplified
plant behavior, absent safety analysis, absent security testing by an independent
party, and dependency/licence exposure. These are acceptable only inside the
declared local simulation boundary.

Public release requires a separate review of secrets/history, dependency and
container vulnerabilities, third-party licences and data rights, documentation
claims, generated artifacts, accessibility, threat-model completeness, and a
chosen repository licence. Passing automated tests alone is not authorization
to publish or connect physical assets.
