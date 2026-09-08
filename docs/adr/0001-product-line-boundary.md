# ADR 0001: Separate the software product line

Status: Accepted — 2026-09-07

## Context

The source repository mixed an executable demonstrator with manuscript assets,
frozen workbooks and research-only experiment automation. That obscured runtime
dependencies and complicated public review.

## Decision

Maintain a software-only product branch and preserve the research package on its
existing branch. Package and container builds use explicit runtime allowlists.

## Consequences

The public candidate is smaller and easier to operate and audit. Research
reproduction remains available separately, and cross-branch changes must be
ported intentionally.
