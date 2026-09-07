# Synthetic OT incident response and recovery playbook

This playbook is for the local DepotFlux demonstrator. It is not an emergency
procedure for a real fleet, charger, PLC or utility interface. On real equipment,
follow the asset owner's authorized operating and safety procedures.

## Triggers

- repeated `invalid_credential` or `direct_plc_access_rejected`;
- `replayed_command`, `stale_command`, `unsafe_setpoint` or
  `approval_result_hash`;
- `register_scan_rejected`;
- `controller_exchange_failed` or `controller_heartbeat_lost`;
- unexpected safe-state activation or evidence gaps.

## Triage

1. Record the UTC time, operator, affected run, reason code and correlation ID.
2. Preserve `security_events`, `ot_dispatch_attempts`, API/gateway/PLC container
   logs and the generated `.demo/evidence` files. Do not edit them in place.
3. Determine whether the event was a documented drill. A drill label does not
   make an unexpected result harmless.
4. Confirm the system is still inside the synthetic boundary. If any physical
   adapter or real endpoint has been introduced, stop and escalate to the asset
   owner; this playbook is no longer sufficient.

## Containment decision tree

- Invalid/replayed/stale/hash/range event with no frame: suspend the affected
  operator session, rotate the relevant local secret, and inspect correlated
  attempts. The policy gate already prevented a command.
- Scan/direct PLC event: stop the originating container, preserve its network
  metadata, verify the control network membership, and rotate the gateway key.
- Lost heartbeat/transport failure: treat controller state as unknown even when
  a safe-state attempt is recorded. Do not infer that an unreachable device
  accepted it.
- Unexpected accepted command: stop further dispatch, preserve evidence, and
  compare run digest, approval, derived setpoint and frame decode.

The demo emergency endpoint requires a separate key and a written reason. It is
appropriate for a controlled software drill when the synthetic controller is
reachable. It is not proof of an electrical safe state.

## Eradication and recovery

1. Correct the configuration or code only after evidence capture.
2. Rebuild images from pinned files and start an empty migrated database.
3. Run the full Python tests, dashboard lint/type/build, Compose smoke, and
   network isolation verifier.
4. Verify the controller begins `ready`, heartbeat changes, normal zero dispatch
   remains `active`, and emergency mode becomes `safe_state`.
5. Re-enable the demo only after a second-person review of the triggering event
   and the evidence package.

Recovery is successful when health checks pass, the original adverse scenario
is rejected as expected, an approved synthetic dispatch succeeds, correlation
is complete, and no unintended service has joined the control network.

## Communications and lessons learned

For a portfolio demonstration, identify the incident commander, application
owner, OT/network owner and evidence custodian. Record what happened, why the
control did or did not work, residual uncertainty, corrective action and a new
test. Avoid claims that the exercise validates production incident response or
field safety.
