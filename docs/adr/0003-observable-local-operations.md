# ADR 0003: Prefer inspectable local operations

Status: Accepted — 2026-09-07

## Context

A convincing software demonstrator must be diagnosable and recoverable without
requiring a hosted observability or backup vendor.

## Decision

Emit structured JSON logs, UUID request correlation and bounded Prometheus text
metrics. Provide application-level, content-digested JSON backup/restore and
automated restart-recovery and read-load evidence.

## Consequences

The operational behavior is portable and reviewable. Metrics are process-local,
backups are not encrypted automatically, and the evidence does not establish
production availability or capacity.
