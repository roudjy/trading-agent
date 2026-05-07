# Autonomous Development Release Gate (A9)

> Canonical governance document for the Release Gate introduced in
> A9. Read-only schema + closed vocabularies + reporting CLI. ADE
> core stays pure; evidence collection lives outside ADE core.

## Status

Active. Modifications to this document require operator approval.

## What this is — and is not

A9 turns Autonomous Development Operating Queue items in
`category=release` with `status=validation_needed` into a
deterministic go/no-go release-gate report. The output replaces ad-
hoc "I think it's ready" reasoning with an evidence-backed verdict
keyed by closed vocabulary.

A9 is **not**:

- an automatic merge or tag,
- a deployment trigger,
- a QRE-specific release surface,
- a substitute for the operator's judgement on architecture
  crossroads, frozen contracts, or live/capital-related work.

`go` means "evidence shows nothing blocks merge". It does **not**
mean "merge me automatically". The operator (or a future, separately
governed automation) performs the actual merge through the GitHub
PR lifecycle protocol (`docs/governance/github_pr_lifecycle.md`).

## Architectural separation: ADE core vs evidence collectors

ADE core
:   `reporting/development_release_gate.py` and
    `reporting/development_release_gate_status.py`. Stdlib +
    `reporting.execution_authority` + `reporting.approval_policy` +
    `reporting.development_work_queue` (read-only API). **No
    subprocess, no network, no `gh`, no `git`.** Pinned by
    source-text scans and AST import inspection.

Evidence collectors / adapters (out of scope for A9 core)
:   Optional, separately governed scripts that may live under
    `scripts/` or be operator-driven runbooks. Collectors **may**
    invoke `gh`, `git`, CI APIs, or read on-disk artifacts. They
    write a structured **evidence input contract** (see below). ADE
    core consumes only that contract; ADE core never imports a
    collector.

This split is permanent. The architecture explicitly preserves a
future collector path so the operator does not have to permanently
assemble release evidence by hand. Until a collector is committed,
the operator may populate the evidence input by hand following this
document — that is acceptable as a transitional state, not as the
permanent architecture.

## Evidence input contract

Default path:
```
logs/release_gate_input/latest.json
```

Schema (closed; additive only):

```json
{
  "schema_version": "1.0",
  "generated_at_utc": "<iso utc>",
  "evidence": {
    "ci_status":                    {"present": <bool>, "value": "<closed>"},
    "smoke_status":                 {"present": <bool>, "value": "<closed>"},
    "governance_lint_status":       {"present": <bool>, "value": "<closed>"},
    "frozen_hash_status":           {"present": <bool>, "value": "<closed>"},
    "no_touch_path_delta_status":   {"present": <bool>, "value": "<closed>"},
    "queue_cross_reference_status": {"present": <bool>, "value": "<closed>"}
  }
}
```

Closed value vocabularies (pinned in
`reporting.development_release_gate.EVIDENCE_VALUE_VOCAB`):

| Key | Allowed values |
|---|---|
| `ci_status` | `green`, `red`, `pending`, `unknown` |
| `smoke_status` | `passed`, `failed`, `unknown` |
| `governance_lint_status` | `ok`, `fail`, `unknown` |
| `frozen_hash_status` | `stable`, `drift`, `unknown` |
| `no_touch_path_delta_status` | `clean`, `violation`, `unknown` |
| `queue_cross_reference_status` | `consistent`, `missing_item`, `unknown` |

`present=false` always coerces `value` to `unknown` for verdict
purposes. Unknown extra keys are dropped with a `validation_warning`.

## Verdict vocabulary (closed, 5)

```
go                  — every required evidence key is present and clean
go_with_followups   — same as go, plus the queue item lists advisory
                      validation_requirements the operator should
                      complete before/after merge
no_go_blocked       — at least one hard-block evidence value is
                      observed (CI red / smoke failed / lint fail /
                      frozen drift / no-touch violation / queue
                      cross-reference inconsistent)
no_go_human_needed  — protected_surface=true, or the queue item's
                      execution_authority is NEEDS_HUMAN /
                      PERMANENTLY_DENIED. Operator decides.
not_evaluated       — evidence input absent, required evidence
                      missing/unknown, CI pending, queue artifact
                      missing, or queue item is not category=release
                      / status=validation_needed
```

## Verdict precedence (first-match)

1. Queue-item-side overrides: `protected_surface=true` ⇒
   `no_go_human_needed/protected_surface_present`.
2. `execution_authority == PERMANENTLY_DENIED` ⇒
   `no_go_human_needed/execution_authority_permanently_denied`.
3. `execution_authority == NEEDS_HUMAN` ⇒
   `no_go_human_needed/execution_authority_needs_human`.
4. Evidence input absent ⇒
   `not_evaluated/evidence_input_missing`.
5. Hard-block evidence (in order):
   - frozen-hash drift,
   - no-touch path violation,
   - CI red,
   - smoke failed,
   - governance-lint fail,
   - queue cross-reference inconsistent.
6. CI pending ⇒ `not_evaluated/ci_status_pending`.
7. Required evidence absent or `unknown` ⇒
   `not_evaluated/required_evidence_absent`.
8. All evidence present and clean — if the queue item lists
   `validation_requirements`, verdict is `go_with_followups`;
   otherwise `go`.

This precedence is pinned by tests and intentionally errs on the
side of human escalation.

## Per-row schema

```
gate_id                       — deterministic hash of (queue_item_id, evidence_snapshot_id)
queue_item_id                 — A8 work-item id
title                         — bounded scalar mirror
verdict                       — closed
verdict_reason                — closed
evidence_inputs               — list of evidence keys actually evaluated
missing_evidence              — list of evidence keys absent or unknown
required_followups            — bounded list mirroring queue item's validation_requirements
human_needed                  — bool (true iff verdict == no_go_human_needed)
human_needed_reason           — closed (A8 vocabulary)
execution_authority_decision  — mirrored from A8 item
risk_level                    — mirrored from A8 item
protected_surface             — mirrored from A8 item
created_at_placeholder        — deterministic_seed_placeholder
updated_at_placeholder        — deterministic_seed_placeholder
notes                         — bounded scalar
```

## Hard guarantees (pinned by tests)

- ADE core stdlib + `reporting.execution_authority` +
  `reporting.approval_policy` + `reporting.development_work_queue`.
- No subprocess, no network, no `gh`, no `git`.
- No imports from `dashboard`, `automation`, `broker`,
  `agent.risk`, `agent.execution`, `research`, or
  `reporting.intelligent_routing` (AST-level pin).
- Atomic write only under `logs/development_release_gate/latest.json`.
- Pure scoring: same inputs (same queue artifact, same evidence
  input, same injected `generated_at_utc`) produce byte-identical
  output.
- Per-row `gate_id` is deterministic; depends on the queue item id
  and the canonical evidence snapshot id (sha256 of the normalized
  evidence dict).

## CLI surface

```
python -m reporting.development_release_gate            # writes artifact
python -m reporting.development_release_gate --no-write  # stdout only
python -m reporting.development_release_gate_status      # writes status artifact
python -m reporting.development_release_gate_status --no-write
```

## Authority and safety

- The release gate produces an **advisory** verdict. The decision to
  merge remains an `pr_squash_merge` action gated by the Execution
  Authority classifier.
- A `go` verdict on an item never overrides the classifier or branch
  protection. Both must independently allow the merge.
- Items touching protected surfaces or with non-AUTO_ALLOWED
  authority can never reach `go`; they reach at most
  `no_go_human_needed`.
- A frozen-hash drift signal always wins over any other evidence.
- Any "go" recommendation is paired with the merged PR's normal
  pre-merge verification (`docs/governance/github_pr_lifecycle.md`):
  CI green, mergeable, no protected-path delta in the diff.

## Future collector path (preserved, not implemented in A9 v0)

A future collector script is expected to:

1. Read the current branch / PR via `gh pr view <num>`.
2. Read CI status via `gh pr checks <num>`.
3. Read the diff via `git show --stat <sha>` and check for
   protected-path / frozen-contract / live-path deltas.
4. Read `logs/development_work_queue/latest.json` to confirm cross-
   reference consistency.
5. Run `python -m reporting.governance_lint` (or read its existing
   artifact) to populate `governance_lint_status`.
6. Run `python -m pytest tests/smoke -q` to populate `smoke_status`
   (or read a CI artifact).
7. Atomically write `logs/release_gate_input/latest.json` with the
   collected evidence.
8. Invoke `python -m reporting.development_release_gate` to score.

The collector is governance/process work, not ADE core. It will be
proposed in a separate, narrowly scoped PR after A9 lands and the
operator has decided which collector shape best fits the workflow.

## Modifying this document

This is governance documentation. Modifications follow the same
discipline as `docs/governance/development_work_queue.md`: scope-
bounded PR, CI green, post-merge gates, no `--admin` merge.
