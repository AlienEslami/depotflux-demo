# WP-ID-02: DepotFlux Operational Replanning Loop

## Objective

Turn an approved day-ahead plan into a durable operating baseline and let a
depot operator respond to a simulated disruption entirely from the browser.
Every candidate remains decision support: deterministic validation and an
explicit human decision are required, and no command is sent to a physical
asset.

## Demonstration flow

1. Solve and approve a day-ahead plan.
2. Select a frozen late-return, charger-derating, or combined notice.
3. Preserve the source message and its deterministic structured facts.
4. Start the remaining-horizon model from the approved fleet-energy state.
5. Compare the candidate with the approved baseline.
6. Review service and SOC validation and approve or reject the candidate.
7. Reconstruct the notice, optimization, validation, and decision from the
   audit timeline.

## Delivery slices

| Slice | Deliverable | Acceptance gate | Status |
|---|---|---|---|
| 1 | Versioned notice contracts, persistence, and simulator | Only a successful approved run can become a baseline | Implemented |
| 2 | Remaining-horizon worker integration | A real solver result is linked to the notice and baseline hashes | Implemented |
| 3 | Operator notice and comparison surface | Source message, facts, rationale, and metric deltas are visible | Implemented |
| 4 | Failure and recovery coverage | Infeasible, timed-out, cancelled, and invalid candidates remain distinct and cannot be approved | Next |
| 5 | Five-minute browser acceptance journey | A first-time reviewer completes the combined disruption story without a terminal | Next |

## Current frozen scenarios

- Bus 1 returns 30 minutes late.
- Charger 1 is limited from 200 kW to 150 kW during timesteps 15–22.
- The combined scenario applies both changes at the same observation point.

These parameters are deliberately mild enough to produce a validated candidate
on the portable HiGHS solver. More severe disruptions belong in the controlled
failure demonstration rather than the nominal path.

## Remaining package work

- Add explicit timeout and cancellation handling around the real-time solver.
- Show bus-level SOC and assignment differences, not only aggregate metrics.
- Add a controlled infeasible scenario and a recoverable worker-interruption
  scenario.
- Add Playwright coverage for baseline approval, event simulation, replanning,
  validation blocking, and final decision.
- Run the five-minute demonstration on documented reference hardware and record
  latency measurements.

## Definition of done

WP-ID-02 is complete when the nominal combined disruption passes the browser
journey, invalid candidates cannot be approved, the controlled failure ends in
a clear recoverable state, and the complete chain is durable across an API page
refresh and worker restart.
