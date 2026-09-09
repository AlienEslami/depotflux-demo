# GridTwin threat model and risk register

Status: educational model for a synthetic lab. Method: asset/trust-boundary
review plus threat-event analysis. This is not a penetration test or operational
risk acceptance.

## Assets and trust boundaries

Protected assets are schedule integrity, BESS/EV operating envelopes, telemetry
integrity and freshness, approval/result binding, service continuity, role
credentials and audit evidence. Trust boundaries are the dashboard-to-API
boundary, API-to-supervisory gateway conduit, gateway-to-controller conduit,
and the model/telemetry boundary between pandapower predictions and reported
measurements. The architecture diagram defines five IEC 62443-style educational
zones: enterprise, industrial DMZ, supervisory, control and monitoring.

## Threat events

| ID | Event | Effect | Implemented prevention/detection | Recovery/evidence |
|---|---|---|---|---|
| T-01 | False voltage telemetry masks undervoltage | Unsafe candidate appears healthy | Residual against trusted AC estimate plus limit-state disagreement | Reject reading; use validated schedule; hash-chained record |
| T-02 | Unauthorized set-point exceeds envelope | Voltage violation or equipment stress | Role/allowlist gate and pre-dispatch AC constraint validation | No frame; retain 1,371.545 kW safe set-point |
| T-03 | Replay of valid command | Duplicate actuation | Existing command UUID replay cache and freshness window | Reject and correlate security event |
| T-04 | Optimization result changed after approval | Different objective/set-point inherits approval | Existing approval-to-result SHA-256 binding | Deny dispatch and require new approval |
| T-05 | Objective/price input changed | Economic manipulation | Registered input digest and deterministic fixture | Reject changed fixture; rerun from trusted input |
| T-06 | Controller or conduit loss | Unknown command state | Bounded retry, heartbeat change check | Best-effort explicit safe state; failure evidence |
| T-07 | Broad Modbus register scan | Process discovery/manipulation | Defined read shape and PLC peer allowlist | Exception response, alarm and event |
| T-08 | Audit record alteration | Misleading investigation | Hash-chain verification | Detect tampering; preserve original artifact externally |
| T-09 | Compromised Docker host | Logical zones bypassed | Outside the demonstrated control boundary | Stop lab; rebuild trusted host; residual risk |

## Risk register

Likelihood and impact use a project-only 1–5 ordinal scale; score is L×I. These
are engineering prioritization judgments, not measured probabilities.

| Risk | Owner | Initial | Treatment demonstrated | Residual | Disposition / gap |
|---|---|---:|---|---:|---|
| R-01 forged telemetry | Grid analytics owner | 4×5=20 | physics residual + constraint disagreement | 2×5=10 | Reduce; estimator uses the same model family |
| R-02 unauthorized command | OT application owner | 4×5=20 | separated role, allowlist, envelope, no-frame denial | 2×5=10 | Reduce; demo shared secrets are not production IAM |
| R-03 replay/stale command | Gateway owner | 4×4=16 | UUID cache and time window | 2×4=8 | Reduce; replay state is process-local |
| R-04 approval/result mismatch | Operations owner | 3×5=15 | immutable approval digest binding | 1×5=5 | Reduce; database is not WORM |
| R-05 unsafe optimizer output | Optimization owner | 3×5=15 | result validation + AC post-check + explicit failure | 2×5=10 | Reduce; linear BESS envelope is snapshot-specific |
| R-06 controller loss | Operations owner | 3×5=15 | bounded retries, heartbeat, best-effort safe state | 2×5=10 | Reduce; no safety PLC or HIL proof |
| R-07 evidence tampering | Evidence owner | 3×4=12 | SHA-256 chain | 2×4=8 | Reduce; hashes are not signed or externally anchored |
| R-08 dependency compromise | Product owner | 3×4=12 | pinned top-level versions and CI audit | 2×4=8 | Reduce; transitive lock/SBOM review remains |
| R-09 host/network bypass | Platform owner | 3×5=15 | non-root containers and internal networks | 3×5=15 | Accept for local demo only |
| R-10 misleading public claim | Project owner | 4×4=16 | explicit claim boundary and release gate | 2×4=8 | Reduce; owner review required before publication |

## Measured attack/recovery result

The current deterministic run includes two attack samples and two paired clean
samples. It measured precision=1.0, recall=1.0, F1=1.0 and false-positive
rate=0.0 on this four-sample fixture only. The FDI residual was 0.044285 pu. The
actual gateway credential gate denied the unauthorized 1,621.545 kW request,
and the integration probe observed zero Modbus requests for both unauthorized
and unsafe cases. Recovery used the validated 1,371.545 kW schedule, left zero
voltage/thermal violation intervals and increased modeled operating cost by
0.606 CAD in the canonical Docker/HiGHS result. This tiny sample is test
evidence, not a general detector-performance claim.
