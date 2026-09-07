# DepotFlux interview demo script

Target duration: 8–10 minutes. Use only the local synthetic lab.

## Before the interview

```powershell
./scripts/start_ot_lab.ps1
./scripts/run_ot_evidence.ps1
```

Confirm the dashboard, API docs and monitor URLs printed by the start script.
Keep `.demo/evidence` available. Do not connect a real device or claim the lab
is production-ready.

## 1. Frame the risk (60 seconds)

“An optimizer is not automatically a trusted controller. The interesting
security problem is preventing an unapproved, changed, stale, replayed or unsafe
result from crossing into an OT command path. This project is a software-only
lab around that boundary; it reports `direct_asset_control=false`.”

Show the dashboard’s decision-support boundary and the architecture diagram in
`OT_NETWORK_ARCHITECTURE.md`.

## 2. Explain the architecture (90 seconds)

Point out the operator, DMZ, supervisory, PLC and monitoring zones. Emphasize
that only the gateway shares the control network and that the PLC has no host
port. Show `compose.yaml` and the conduit matrix. Open the network-isolation
evidence: API, worker and monitor fail to resolve the PLC; gateway connection
succeeds.

## 3. Run the normal path (2 minutes)

In the dashboard:

1. Queue a registered synthetic input and wait for the worker result.
2. Review deterministic validation and approve the exact result digest.
3. Select an interval, enter the printed session-only control key, and dispatch.
4. Show the policy checks, FC10 request, response frame, measured power,
   controller state, heartbeat and correlation ID.
5. Find the same correlation in the run timeline and security-event list.

Explain that the client selected a run/interval; it did not supply the setpoint.

## 4. Demonstrate fail-closed behavior (2 minutes)

Use “Demonstrate rejection” to request an interval beyond the approved horizon.
Show the HTTP/policy rejection, null frame and persisted evidence. Then open the
Compose smoke JSON and show the invalid-key, replay and stale-command results.
Mention that digest mismatch and range tests are in the focused JUnit evidence.

## 5. Show safe state and monitoring (90 seconds)

Show the explicit distinction between regular mode 0 and emergency mode 1.
Use the safe-state API only as an authorized local drill, with the separate key
and reason. Show state `safe_state`, alarm bit and structured event. Explain that
loss of heartbeat causes a best-effort safe-state attempt, but an unreachable
device’s state remains unknown.

Open the Sigma/KQL examples and incident-response playbook. Say clearly that
these are illustrative rules, not live-SIEM validation.

## 6. Close with limitations (60 seconds)

“This demonstrates architecture, protocol implementation, policy enforcement,
negative testing and assurance evidence. It does not prove compliance,
functional safety, field readiness or real PLC control. Production work would
replace shared headers with strong identity, move replay state to durable shared
storage, use industrial network controls, sign/retain evidence, test vendor
semantics, perform safety and threat assessments, and complete authorized
integration testing.”

## Questions to invite

- Why keep the policy authority separate from the protocol gateway?
- What happens after a timeout when command state is ambiguous?
- How would replay protection work with multiple gateway replicas?
- Which evidence supports each security requirement?
- What changes before connecting a vendor controller?
