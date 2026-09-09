# GridTwin measured results

Generated: `2026-09-09T00:00:36.131899+00:00`

Synthetic, software-only evidence; no physical asset was controlled.

| Scenario | Cost (CAD) | Export revenue (CAD) | Peak site (kW) | Losses (kWh) | Voltage violation intervals | Thermal violation intervals | BESS throughput (kWh) | Solve time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Uncontrolled charging | 160.070 | 0.000 | 1600.0 | 2105.033 | 2 | 0 | 0.000 | 0.000 |
| DepotFlux cost-optimized EV + BESS | 126.301 | 55.962 | 1600.0 | 2112.639 | 2 | 0 | 801.053 | 44.904 |
| DepotFlux EV + grid-constrained BESS | 126.907 | 55.962 | 1371.5 | 2107.347 | 0 | 0 | 882.117 | 44.887 |

## Security evidence

- False-data injection detected: `True`.
- Unauthorized/unsafe set-point denied by gateway policy: `True` (`gateway_authentication_failed`).
- Observed Modbus write/read attempts after denial: `0` / `0`; frame transmitted: `False`.
- Precision/recall/F1: `1.000` / `1.000` / `1.000` on 4 deterministic paired samples.
- False-positive rate: `0.000`.
- Mean/max synchronous detection delay: `77.608 ms` / `155.214 ms`.
- Remaining post-recovery violations: `0`.
- Recovery objective loss: `0.606 CAD`.
- Audit hash chain valid: `True`.
- Local GridTwin metadata API p50/p95 (30 requests): `4.094 ms` / `5.676 ms`.

## Baseline and limitations

The feeder is pandapower's open CIGRE MV benchmark with existing loads scaled to 0.55. The EV depot and 500 kWh / 250 kW BESS are connected at Bus 11. The BESS inverter follows a fixed 0.98 power factor. Results are deterministic fixtures, not utility measurements, field validation, or standards compliance evidence.
