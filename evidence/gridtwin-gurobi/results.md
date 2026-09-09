# GridTwin measured results

Generated: `2026-09-09T00:01:34.337176+00:00`

Synthetic, software-only evidence; no physical asset was controlled.

| Scenario | Cost (CAD) | Export revenue (CAD) | Peak site (kW) | Losses (kWh) | Voltage violation intervals | Thermal violation intervals | BESS throughput (kWh) | Solve time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Uncontrolled charging | 160.070 | 0.000 | 1600.0 | 2105.033 | 2 | 0 | 0.000 | 0.000 |
| DepotFlux cost-optimized EV + BESS | 126.201 | 55.962 | 1600.0 | 2115.335 | 2 | 0 | 801.053 | 1.641 |
| DepotFlux EV + grid-constrained BESS | 126.907 | 55.962 | 1371.5 | 2106.414 | 0 | 0 | 882.117 | 1.647 |

## Security evidence

- False-data injection detected: `True`.
- Unauthorized/unsafe set-point denied by gateway policy: `True` (`gateway_authentication_failed`).
- Observed Modbus write/read attempts after denial: `0` / `0`; frame transmitted: `False`.
- Precision/recall/F1: `1.000` / `1.000` / `1.000` on 4 deterministic paired samples.
- False-positive rate: `0.000`.
- Mean/max synchronous detection delay: `83.643 ms` / `167.285 ms`.
- Remaining post-recovery violations: `0`.
- Recovery objective loss: `0.705 CAD`.
- Audit hash chain valid: `True`.
- Local GridTwin metadata API p50/p95 (30 requests): `5.781 ms` / `7.503 ms`.

## Baseline and limitations

The feeder is pandapower's open CIGRE MV benchmark with existing loads scaled to 0.55. The EV depot and 500 kWh / 250 kW BESS are connected at Bus 11. The BESS inverter follows a fixed 0.98 power factor. Results are deterministic fixtures, not utility measurements, field validation, or standards compliance evidence.
