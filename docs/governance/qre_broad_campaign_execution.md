# QRE Broad Campaign Execution

## Purpose

`reporting.qre_broad_campaign_execution` materializes deterministic, read-only
campaign accounting from the frozen `ADE-QRE-017X` manifest and any matching
repository-backed broad-run artifacts.

## Current 017Y behavior

- Source manifest: `logs/qre_preregistered_campaign_manifest/latest.json`
- Optional historical evidence inputs:
  - `logs/qre_preregistered_multiwindow_evidence_run/latest.json`
  - `logs/qre_multiwindow_evidence_closure/latest.json`
- Every frozen manifest row is accounted for with one terminal execution status:
  - `completed`
  - `rejected`
  - `insufficient_evidence`
  - `blocked`
  - `timed_out`
  - `errored`
  - `not_executed`
- When the preregistered manifest has `0` executable cells, the report fails
  closed and records the broad campaign as a non-executable outcome rather than
  inventing execution.

## Authority boundary

- Read-only and context-only.
- Produces no campaign launch, queue mutation, or strategy generation.
- Grants no paper, shadow, live, broker, risk, or trading authority.

## Outputs

- `logs/qre_broad_campaign_execution/latest.json`
- `logs/qre_broad_campaign_execution/latest.md`

The JSON artifact includes:

- `campaign_execution_identity`
- `manifest_identity`
- `replay_identity`
- `rows`
- deterministic `status_counts`
- historical-evidence linkage where visible
- fail-closed recommendation when execution is not actually supported
