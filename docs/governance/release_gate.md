# Release Gate Runbook

The release-gate-agent is the final governance step before any merge or
deploy. It produces an immutable, evidence-backed report and never
performs the transition itself.

This document describes how to invoke it, where reports live, and what
the operator does with the report.

---

## Invocation

```text
/release-gate
```

Spawns the `release-gate-agent` against the current branch.

## Output

A new file at:

```
docs/governance/release_gates/<version>/<YYYY-MM-DDTHH-MM-SSZ>.md
```

Reports are **append-only by file** — the agent creates a new file per
invocation; it never edits a previous report. Each report contains the
deterministic-checklist results (see
[`release_gate_checklist.md`](release_gate_checklist.md)) plus per-gate
verdicts.

## Per-gate verdicts

The release-gate-agent issues four verdicts:

| Gate | Authority | Action on `recommend yes` |
|---|---|---|
| `commit` | local | Operator may run `git commit` if not yet done. |
| `PR` | local + CI | Operator may run `gh pr create`. |
| `merge` | **humans-only** | Operator merges via GitHub UI after review. Agent never merges. |
| `deploy` | **humans-only** | Operator runs `scripts/deploy.sh` from their own shell. Agent never deploys. |

A `recommend no` on any gate halts the chain at that gate.

## Evidence per gate

For each verdict, the report cites:

- Relevant CI run id(s).
- `verify_chain()` result on today's audit ledger (and first corrupt
  index, if any).
- Build provenance JSON for the version (commit SHA, image digest,
  workflow run id).
- Active nightly failures (or `none active`).
- Audit-ledger event id range covered by the session that produced the
  PR.

## Evidence sources

- CI: `.github/workflows/{tests,nightly,docker-build}.yml` runs.
- Audit: `logs/agent_audit.<UTC date>.jsonl` + the corresponding
  `docs/governance/agent_run_summaries/<session_id>.md`.
- Provenance: `artifacts/build_provenance-<version>.json` (workflow
  artifact).
- Digests: `docs/governance/release_digests.md`.

## What the operator does

1. Read the report.
2. If `merge: recommend yes` and the operator agrees, merge via GitHub
   UI. Branch protection still requires CODEOWNERS review.
3. If `deploy: recommend yes` and the operator agrees, run
   `scripts/deploy.sh` from their own shell with `IMAGE_TAG` set to the
   digest-pinned reference (e.g.
   `IMAGE_TAG=ghcr.io/...@sha256:<digest>`). See
   [`rollback_drill.md`](rollback_drill.md) for the digest convention.
4. After deploy, append the new digest to
   [`release_digests.md`](release_digests.md).

## What the agent does NOT do

- Merge.
- Deploy.
- Edit a previous report.
- Bump `VERSION` directly.
- Recommend tag-based (non-digest) rollback.

## Review-gate failure modes

- Determinism drift → `determinism-guardian` recommends block →
  release-gate-agent emits `merge: recommend no`.
- Schema mutation → `evidence-verifier` recommends block →
  release-gate-agent emits `merge: recommend no`.
- Posture change → `deployment-safety-agent` recommends block on
  `deploy` gate.
- Adversarial-review block finding → release-gate-agent quotes
  verbatim and emits `merge: recommend revise` or `recommend no`.

## Cross-references

- ADR-015 §Doctrine 4
- [`release_gate_checklist.md`](release_gate_checklist.md)
- [`rollback_drill.md`](rollback_drill.md)
