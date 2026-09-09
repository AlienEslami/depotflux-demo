# GridTwin solver comparison

Both runs use experiment `gridtwin-cigre-mv-depot-a-8-v1`, the same input
digest, a zero requested MILP gap and optimal solver termination. The portable
Docker result is the documented baseline. The Gurobi result is an optional
same-host cross-check under the owner's academic, non-commercial licence.

| Measure | Docker / HiGHS 1.15.1 | Local / Gurobi 13.0.2 |
|---|---:|---:|
| Total evidence runtime (s) | 82.879 | 33.470 |
| Cost-only combined solve time (s) | 42.708 | 2.437 |
| Grid-constrained combined solve time (s) | 42.708 | 2.442 |
| Cost-only energy cost (CAD) | 126.301 | 126.201 |
| Grid-constrained energy cost (CAD) | 126.907 | 126.907 |
| Grid-constrained peak (kW) | 1,371.545 | 1,371.545 |
| Grid-constrained feeder losses (kWh) | 2,107.347 | 2,106.414 |
| Grid-constrained voltage / thermal violation intervals | 0 / 0 | 0 / 0 |
| Grid-constrained BESS throughput (kWh) | 882.117 | 882.117 |

The retained EV MILP minimizes the fleet operator's retail charging cost, while
GridTwin also reports wholesale site-energy cost and AC feeder losses after the
solve. The model has alternate retail-optimal schedules and does not apply a
secondary tie-break objective for those post-processed measures. Consequently,
the two solvers agree on the safety-critical constrained peak, violations,
throughput and constrained cost, but select different cost-only schedules. The
0.100 CAD cost-only and 0.933 kWh constrained-loss differences are recorded,
not hidden or averaged.

Timing is descriptive rather than a controlled benchmark: HiGHS ran inside the
Docker service and Gurobi ran directly on the host. No claim of general solver
superiority is supported.

Evidence bundles:

- `evidence/gridtwin/`: canonical Docker/HiGHS result.
- `evidence/gridtwin-gurobi/`: optional local Gurobi cross-check.
