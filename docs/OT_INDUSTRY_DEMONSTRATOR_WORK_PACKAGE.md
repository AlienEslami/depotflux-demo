# Work package: synthetic OT dispatch assurance demonstrator

## Outcome

Turn the existing DepotFlux research workflow into an interview-ready software
demonstrator showing how an optimization result is authorized, constrained,
transported to a synthetic industrial endpoint, monitored and investigated.

The deliverable is intentionally not a field-control product. It must remain
software-only with `direct_asset_control=false` until a separately authorized,
multidisciplinary production program defines safety, identity, network,
supplier, operations and commissioning requirements.

## Target roles and value

The work package is designed to produce discussable evidence for OT/ICS
cybersecurity analyst or engineer, energy-platform security, industrial software
integration, product security, security architecture and cyber-risk/assurance
roles. It connects risk reasoning to executable controls and tests rather than
presenting standards vocabulary alone.

## Delivered scope

### WP-1 — Secure command path

- Actual Modbus/TCP client and deterministic server using FC03 and FC10.
- Defined import/export, command mode, measurement, state, alarm and heartbeat.
- Server-derived setpoint from an approved schedule; no arbitrary normal value.
- Credential, run state, approval, hash, validation, interval and capacity gates.
- Gateway freshness, future-skew, replay, range, timeout, retry and response gates.
- Explicit separately credentialed zero-power safe-state mode.

Acceptance: protocol and API integration tests pass; invalid inputs create no
frame; valid input produces matching write acknowledgement and measurement.

### WP-2 — Segmented lab deployment

- Enterprise/operator, industrial DMZ, supervisory/EMS, control/PLC and
  monitoring networks in Compose.
- Only dashboard, API and monitor on host loopback.
- PLC accepts only the fixed gateway control-network address.
- Non-root service user, dropped capabilities and no-new-privileges.

Acceptance: seven services healthy; API/worker/monitor cannot resolve the PLC;
gateway can connect; migration from empty PostgreSQL reaches revision 0007.

### WP-3 — Evidence and detection

- Accepted/rejected/failed attempts persisted with actor, digest, time, reason,
  frame, response and correlation.
- Structured API/gateway/PLC events.
- Dashboard evidence panel, audit timeline and security-event view.
- Example Sigma/KQL detections with MITRE ATT&CK for ICS mappings.
- Reproducible JUnit, Compose smoke and network-isolation artifacts.

Acceptance: the same correlation can be followed from API decision through
controller response and monitoring record; negative scenarios are deterministic.

### WP-4 — Assurance documentation

- SUC, inventory, Purdue-style placement, zones/conduits and register map.
- Threat model, ISO/IEC 27005-style risk register, security requirements and
  traceability.
- NIST SP 800-82 Rev. 3, NIST CSF 2.0 and IEC 62443 concept mappings.
- Supplier/interface requirements, incident response/recovery, test plan,
  one-page case study and interview script.
- Explicit limitations and prohibited claims.

Acceptance: every implemented security claim points to code, a test or a
generated evidence artifact; framework wording says mapped/aligned, never
certified/compliant.

## Quality gates

1. Full Python regression suite.
2. Dashboard lint, TypeScript and production build.
3. Compose rendering, image builds and all service health checks.
4. Empty-database migration rehearsal.
5. Network isolation and end-to-end scenario scripts.
6. Diff, secret and generated-artifact review.
7. Manual public-release and résumé-claim review.

## Deferred backlog

The following are not current capabilities and must remain labeled backlog:

- IEC 61850 integration or emulation;
- Microsoft Sentinel ingestion/rule validation;
- DNP3 or OPC UA adapters;
- electrical power-flow or hardware-in-the-loop simulation; and
- Kubernetes deployment, multi-replica replay storage and production HA.

## Exit condition

Technical implementation can be called “demonstrator-complete” when gates 1–5
pass. It cannot be called public-release-ready until gate 6 finds no unresolved
issue and a human explicitly authorizes publication. It cannot be described as
production-ready or standards-compliant based on this work package.
