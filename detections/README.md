# Detection examples

These rules target the structured JSON fields emitted by the DepotFlux API,
supervisory gateway and synthetic PLC. They are examples for portfolio review;
they have not been deployed to or validated in a live SIEM. Field names may
need normalization for a real collector.

Expected common fields are `timestamp`/`occurred_at`, `event_type`, `severity`,
`correlation_id`, `actor`, `source_zone`, `destination`, `outcome`,
`reason_code`, `command_id`, and `simulated_only=true`.

- `sigma/depotflux_ot_anomalies.yml` contains portable rule concepts.
- `kql/depotflux_ot_anomalies.kql` assumes a custom table named
  `DepotFluxSecurity_CL` and documents the required field substitutions.

MITRE ATT&CK for ICS tags are analyst mappings for the simulated scenarios, not
claims of adversary emulation or detection coverage.
