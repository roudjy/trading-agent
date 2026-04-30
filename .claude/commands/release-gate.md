---
description: Produce a release-gate report for the current branch / version.
allowed-tools: [Agent]
---

# /release-gate

Runs the release-gate-agent. Produces a new immutable file at
docs/governance/release_gates/<version>/<UTC-timestamp>.md
containing:

- Per-gate verdict (commit / PR / merge / deploy)
- Evidence per gate
- Deterministic-checklist results
- Active nightly failures referenced

Reports are append-only by file (one new file per invocation), never
edited. The report informs the operator's manual merge / deploy
decision.
