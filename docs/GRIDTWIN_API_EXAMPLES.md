# GridTwin API examples

The existing authentication mode applies. When API-key mode is enabled, replace
`$OPERATOR_KEY` with the locally generated operator key. These routes never
address a physical asset.

## Metadata

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/gridtwin/meta `
  -H "Authorization: Bearer $OPERATOR_KEY"
```

Representative response:

```json
{
  "name": "GridTwin Ops",
  "benchmark": "CIGRE MV distribution network",
  "depot_bus": "Bus 11",
  "bess_bus": "Bus 11",
  "scenarios": ["uncontrolled", "cost_optimized", "grid_constrained"],
  "attacks": ["false_data_injection", "unauthorized_setpoint"],
  "synthetic_only": true,
  "direct_asset_control": false
}
```

## Full deterministic experiment

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/gridtwin/experiments `
  -H "Authorization: Bearer $OPERATOR_KEY" `
  -H "Content-Type: application/json" `
  -d '{"input_reference":"demo/depot-a-8-v1","include_security":true}'
```

The response contains `grid`, `bess`, `scenarios`, `comparison`, `security` and
`total_runtime_seconds`. It can take roughly one minute with the open HiGHS
default because it solves the retained MILP and runs the complete AC horizon.

## Paired attack and recovery

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/gridtwin/attacks/simulate `
  -H "Authorization: Bearer $OPERATOR_KEY" `
  -H "Content-Type: application/json" `
  -d '{"attack_type":"unauthorized_setpoint"}'
```

The response reports detection/denial, whether a Modbus frame was transmitted,
the safe set-point, remaining violations and audit-chain status.
