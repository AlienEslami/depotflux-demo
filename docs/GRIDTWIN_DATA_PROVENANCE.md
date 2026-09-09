# GridTwin dependency and data provenance

## Runtime data

| Artifact | Source and licence context | Use in GridTwin | Integrity/provenance control |
|---|---|---|---|
| CIGRE MV benchmark | Distributed with BSD-licensed pandapower; network is attributed in pandapower documentation to CIGRE Task Force C6.04.02 benchmark report | Feeder topology and electrical parameters | Created at runtime by `create_cigre_network_mv(with_der=False)`; pandapower pinned to 3.5.4 |
| Depot A eight-bus fixture | Bundled deterministic synthetic demonstrator fixture derived from the repository's canonical eight-bus case | EV capacities, chargers, trips, tariffs and 48-interval horizon | Registry reference `demo/depot-a-8-v1`, SHA-256 `14b18bb5723f2a3c24c3ee946fc06fdbf0eaea1b27a1d605d1b0663e42d17d26` |
| Background feeder operating snapshot | GridTwin-authored synthetic assumption | Original CIGRE loads uniformly scaled to 0.55 | Configuration is code-visible and recorded in `evidence/gridtwin/results.json` |
| BESS | GridTwin-authored synthetic assumption | 500 kWh, 250 kW, 10–90% SOC, 95% charge/discharge efficiency, 0.98 power factor | Configuration is code-visible and recorded in `evidence/gridtwin/results.json` |
| Attack cases | GridTwin-authored deterministic synthetic fixtures | forged 0.99 pu voltage; unallowlisted 1,621.545 kW request | Inputs, decisions and recovery are in the hash-chained audit artifact |

No private API, customer/utility data, sponsor/collaborator material, proprietary
simulator model or research manuscript artifact is used. The experiment runs
offline after dependencies are installed.

## Key dependencies

- pandapower 3.5.4 (BSD): AC power flow and open CIGRE model.
- Pyomo 6.10.1 plus HiGHS 1.15.1 (open default): mathematical scheduling.
- Optional gurobipy 13.0.2 under the owner's local academic, non-commercial
  licence: accelerated measured run; not included in Docker.
- pymodbus 3.15.0 (BSD-3-Clause): real Modbus/TCP client path.
- FastAPI, SQLAlchemy/Alembic, PostgreSQL and the retained dashboard stack.

Top-level versions are pinned. This is provenance documentation, not a complete
transitive software bill of materials or legal opinion. Public release remains
blocked until the owner selects a repository licence and completes dependency
and data-rights review.
