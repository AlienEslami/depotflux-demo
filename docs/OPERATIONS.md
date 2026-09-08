# Local operations guide

## Lifecycle command

Run commands from the repository root:

```powershell
./scripts/depotflux.ps1 start
./scripts/depotflux.ps1 status
./scripts/depotflux.ps1 credentials
./scripts/depotflux.ps1 seed
./scripts/depotflux.ps1 verify
./scripts/depotflux.ps1 backup
./scripts/depotflux.ps1 stop
```

`start` creates missing 128-bit local secrets under ignored `.demo/ot-lab.env`,
builds the images, applies migrations, waits for health and queues one idempotent
starter run. Re-running it preserves the existing database and credentials.

## Configuration

`python -m aggregator_demo.admin check-config` validates configuration and emits
a safe summary that never contains passwords or access keys. API-key mode
requires unique keys of at least 20 characters for every role. CORS values must
be complete HTTP(S) origins without user information, paths, queries or
fragments.

## Backup and restore

`backup` writes a timestamped JSON backup under `.demo/backups`. It contains all
application tables, schema/application versions and a SHA-256 integrity digest.
Secrets and database credentials are not included.

Restore is intentionally explicit:

```powershell
./scripts/depotflux.ps1 restore `
  -BackupPath .demo/backups/depotflux-YYYYMMDD-HHMMSS.json `
  -Force
```

The file must reside directly in the backup directory. Its schema, tables,
columns and digest are validated before current application data is replaced in
one transaction. The worker is stopped during restoration and restarted after.

## Reset and recovery

`./scripts/depotflux.ps1 reset -Force` removes only the named synthetic database
volume, rebuilds the lab and seeds it again. It does not remove source files,
backups or the local credential file.

The verification workflow restarts the API and worker, waits for readiness and
reloads a pre-existing run. This demonstrates service restart recovery; it is
not a high-availability claim.

## Performance evidence

`scripts/benchmark_api.py` runs a bounded concurrent, read-only workload against
the run-list endpoint. It records request count, errors, throughput and
minimum/mean/p50/p95/p99/maximum latency. The default acceptance gate is zero
errors and p95 no more than 500 ms on the local review host. Results are local
measurements, not general capacity guarantees.

## Troubleshooting

1. Run `./scripts/depotflux.ps1 status` and inspect health.
2. Read API and worker JSON logs with `docker compose logs api worker`.
3. Use the response `X-Correlation-ID` to follow a request.
4. Check `/metrics` and the security summary endpoint.
5. Back up data before a reset or restore operation.
