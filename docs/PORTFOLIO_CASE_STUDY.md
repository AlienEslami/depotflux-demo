# DepotFlux: portfolio case study

## The problem

Fleet-energy optimization can produce a mathematically valid schedule, but an
OT integration must answer a different question: **what evidence justifies
allowing this exact result, at this time, to become a control-system command?**
An unapproved, stale, replayed, modified or out-of-range command can turn a
decision-support error into an operational event.

## The demonstrator

DepotFlux is a local software lab that carries a synthetic electric-bus depot
schedule from deterministic optimization through human approval and security
policy to a simulated Modbus/TCP site controller. The implementation includes a
durable API/worker/database workflow, real socket protocol exchange, five
logical network zones, a gateway-only PLC conduit, heartbeat and safe-state
behavior, structured detection events, and an operator dashboard.

The central design decision is that the browser never submits an arbitrary
normal setpoint. It selects an approved run and interval; the API derives the
value from the hash-bound result. The gateway independently rejects stale,
future, replayed, non-finite or out-of-envelope commands.

## Evidence

- Real FC10 write and FC03 readback against a deterministic TCP server.
- Import/export, measurement, command mode, controller state, alarm and
  heartbeat register model.
- Persisted accepted, rejected and failed attempts with actor, digest, reason,
  timestamps, frames and correlation ID.
- Negative tests for credentials, approval, digest mismatch, horizon, range,
  replay, staleness, direct access, register scanning and heartbeat loss.
- Compose proof that the API, worker and monitor cannot resolve the PLC while
  the supervisory gateway can connect.
- Example Sigma/KQL analytics and a correlation-driven incident playbook.
- Concept mappings to NIST SP 800-82 Rev. 3, NIST CSF 2.0, IEC 62443 and MITRE
  ATT&CK for ICS, with explicit non-compliance wording.

## Engineering tradeoffs

The project uses straightforward, inspectable controls rather than implying a
production architecture. Shared secrets stand in for identity infrastructure;
Docker bridges stand in for industrial firewalls; the replay cache is local
memory; evidence is relational rather than signed/WORM; and the PLC is a small
state model rather than hardware or a digital twin. These choices keep the lab
reproducible while making the missing production work visible.

## What this demonstrates

The project is relevant to junior/intermediate OT cybersecurity, ICS security
engineering, energy-platform security, security architecture, product security,
industrial software integration and cyber-risk/assurance roles. It shows the
ability to translate risk and standards concepts into code, network boundaries,
tests, operational evidence and appropriately limited claims.

It does not demonstrate field commissioning, plant operations, functional
safety engineering, penetration testing of an authorized industrial target,
production IAM/SIEM operation, vendor protocol certification, or real asset
control.
