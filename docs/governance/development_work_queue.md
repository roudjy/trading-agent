# Autonomous Development Operating Queue (A8)

> Canonical governance document for the Development Work Queue
> introduced in A8. Read-only schema + vocabularies + reporting CLI.

## Status correction

Earlier handoffs described the Autonomous Development Track as
"complete" after PRs #110–#116. That wording was misleading from the
operator's perspective. The corrected framing is:

- **Autonomous Development Governance Foundation: complete (A1–A7).**
  Execution Authority policy + classifier, read-only authority/
  readiness surfaces, proposal-queue cleanup, backlog discipline
  reporting, and a final readiness gate are all in place.
- **Autonomous Development Operating Queue: begins at A8.**
  This is the first concrete, repo-native foundation for the
  development operating loop. A8 is foundation only — schema +
  vocabulary + read-only reporting + tests + docs.
- **Fully autonomous code-development loop: future work.** A9
  (release-gate integration), A10 (bugfix loop), A11 (bounded
  delegation), A12 (operational digest) build on top of A8.

## What this is — and is not

This queue is the **autonomous development queue**: roadmap, build,
maintenance, governance, reporting, test, docs, CI, deployment,
release, observability, and refactor work for the repository itself.

This queue is **not**:

- the QRE research campaign queue (research execution ordering);
- the Intelligent Routing Layer queue (advisory research routing);
- `reporting.proposal_queue` (intake of roadmap proposals).

The module name, file path, and artifact path all use
`development_work_queue` so the distinction is impossible to miss.

## Canonical sources

The queue accepts items declared in the operator-authored sidecar:

- `docs/development_work_queue/seed.jsonl`

The file follows strict JSONL: each non-blank line is a single JSON
object describing one work item. The committed file is **empty** by
default — that is the correct state. Items are added by the operator
only. Blank lines are tolerated; there are no comment lines.

### Seed item schema

Each JSON object on a line provides:

| Field | Type | Notes |
|---|---|---|
| `title` | str (≤ 200) | Required |
| `source_document` | str | Canonical roadmap path or `"sidecar_seed"` |
| `source_section_or_anchor` | str | Free-text section reference |
| `roadmap_track` | str | One of `autonomous_development`, `qre_feature_build`, `sidecar_seed` |
| `category` | str | One of the 10 closed `CATEGORIES` |
| `required_agent_role` | str | One of the 16 closed `AGENT_ROLES` |
| `supporting_agent_roles` | list[str] | Subset of `AGENT_ROLES` |
| `status` | str | One of the 12 closed `STATUSES` |
| `human_needed` | bool | Explicit operator declaration |
| `human_needed_reason` | str | One of the 11 closed reasons; `"none"` iff `human_needed=false` |
| `blocked_by` | list[str] | Item-IDs |
| `priority` | int | Clamped to 1..5 |
| `risk_level` | str | One of `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` |
| `protected_surface` | bool | Whether the item touches a protected surface |
| `acceptance_criteria` | list[str] | ≤ 16 entries, ≤ 200 chars each |
| `validation_requirements` | list[str] | Same bounds |
| `notes` | str (≤ 1000) | Bounded scalar — no diffs / patches |

`item_id` is computed deterministically from `title +
source_section_or_anchor`. `execution_authority` is filled in by
the generator from `reporting.execution_authority.classify`.

A reference example is rendered in the project tests
(`tests/unit/test_development_work_queue.py::_valid_item`).

The two canonical roadmap docs remain the truth-of-record for the
roadmap itself:

- `docs/roadmap/autonomous_development.txt` (Autonomous Development Track)
- `docs/roadmap/Roadmap v6.md` (QRE Feature Build Track)

Items in the seed may name either canonical document as their
`source_document` (declaring the relevant `roadmap_track`) or use
`sidecar_seed` for items that do not yet have an upstream roadmap
anchor.

Anything under `docs/roadmap/archive/**` is historical and is
**rejected** at parse time.

## Closed vocabularies

All vocabularies are closed `Final[tuple[str, ...]]` constants in
`reporting/development_work_queue.py`. Adding a value requires a
visible code change with a matching test update.

### Agent roles (16)

The role describes who is mandated to act on the item. The 15
non-human roles correspond to the agents in `.claude/agents/*`;
`human_operator` is the explicit fallback for items the human owns.

```
product_owner            — backlog curation, one-PR-per-session discipline
strategic_advisor        — long-horizon, cross-cutting trade-offs (advise only)
quant_research_architect — research authority and ledger correctness (advise only)
planner                  — decomposes a roadmap item into ordered tasks
architecture_guardian    — enforces ADR invariants (advise only)
ci_guardian              — workflow edits in dedicated CI-hardening tasks
implementation_agent     — backend non-core implementation
frontend_agent           — React/Vite/Vitest implementation
test_agent               — test authoring within allowed scopes
determinism_guardian     — pin tests, digest recompute (advise only)
evidence_verifier        — append-only ledger / audit-chain checks
observability_guardian   — structured logging, audit events, healthchecks
deployment_safety_agent  — compose/ops/deploy review (advise only)
adversarial_reviewer     — red-team review (advise only)
release_gate_agent       — final go/no-go report per release step
human_operator           — explicit human authority
```

Whether an agent may implement / review / verify / advise is
recorded in the per-agent `.claude/agents/*.md` definition. The
queue uses `required_agent_role` to identify the primary owner and
`supporting_agent_roles` to list reviewers / verifiers.

### Statuses (12, Kanban)

```
proposed         — captured, not yet considered
triaged          — categorized, owner identified
planned          — has a concrete plan
ready            — fully scoped, agent may pick up
in_progress      — being executed
blocked          — waiting on a dependency in `blocked_by`
human_needed     — operator decision required (see `human_needed_reason`)
review_needed    — work delivered, awaiting review
validation_needed — work delivered, awaiting verification
done             — finished and merged
rejected         — explicitly declined
archived         — closed without resolution; preserved for audit
```

### Categories (10)

```
governance, reporting, frontend, test, docs, ci, deployment,
release, observability, refactor
```

### Risk levels (4)

Reused verbatim from `reporting.execution_authority.RISK_CLASSES`:

```
LOW, MEDIUM, HIGH, UNKNOWN
```

### Human-needed reasons (11)

```
architecture_crossroads
protected_governance_change
frozen_contract_change
risk_policy_change
capital_or_live_execution_related
destructive_or_irreversible_action
priority_conflict
ambiguous_scope
missing_acceptance_criteria
repeated_validation_failure
none
```

`none` is reserved for `human_needed: false` rows. The two-way
invariant is enforced at parse time and pinned by tests.

## When human involvement is required

`human_needed: true` is set explicitly per item. A reason from the
closed vocabulary above is required. The intent is that
`human_needed` reflects only **explicit** triggers:

- architecture crossroads (multi-option ADR-level decisions);
- protected governance / frozen-contract / risk-policy changes;
- anything live / paper / shadow / capital-related;
- destructive or irreversible actions;
- a real priority conflict;
- ambiguous scope or missing acceptance criteria;
- repeated validation failure on a previously delivered item.

Plain roadmap headings, unscoped notes, and ordinary documentation
work do **not** become `human_needed`. The default state is *not*
escalation.

## How this relates to the Execution Authority foundation

For each item, the generator runs:

```
reporting.execution_authority.classify(
    action_type="file_edit",
    target_path=item.source_document,
    risk_class=item.risk_level,
)
```

The decision (`AUTO_ALLOWED` / `NEEDS_HUMAN` / `PERMANENTLY_DENIED`)
is recorded on the item as `execution_authority`. Mismatches between
the operator-declared `human_needed` and the classifier's decision
surface as `validation_warnings` on the artifact wrapper. The
classifier never silently overrides the operator.

This is the **same** classifier that backs A1–A2. The Operating
Queue does not redefine authority — it consumes the existing
authority signal.

## What is ready for autonomous agent action

The `counts.ready_for_autonomous_action` aggregate counts items where:

- `execution_authority == "AUTO_ALLOWED"`, **and**
- `human_needed == false`, **and**
- `status in {"ready", "in_progress"}`.

`counts.requiring_human_operator` counts items where any of:

- `human_needed == true`, **or**
- `execution_authority == "NEEDS_HUMAN"`, **or**
- `status == "human_needed"`.

These counts are surfaced verbatim by
`reporting.development_work_queue_status` so the operator can see at
a glance how many items are queue-ready and how many are gated.

## A8 v0 limitations (intentional)

A8 explicitly does not deliver:

- Markdown marker parsing inside the canonical roadmap docs. The
  schema reserves `roadmap_track in {autonomous_development,
  qre_feature_build}` for that future input mode; today's only
  input is the sidecar seed.
- Wiring into `reporting.recurring_maintenance.JOB_TYPES`. The CLI
  is the explicit operator-driven invocation.
- Auto-approve, auto-merge, auto-execute behavior.
- Any LLM-driven runtime planner.
- Frontend dashboard surface (CLI-only for now).

## Future phases (sketch)

- **A9 — Agentic release-gate integration.** Wire the
  `release_gate_agent` mandate into the queue: items in
  `release` category with `status == validation_needed` produce a
  go/no-go report.
- **A10 — Agentic bugfix loop.** Bounded-scope bugfix items in the
  `refactor` / `reporting` categories may move from `ready` to
  `in_progress` without human gating when `execution_authority ==
  AUTO_ALLOWED` and a deterministic test reproduces the bug.
- **A11 — Bounded roadmap implementation delegation.** Plain roadmap
  decomposition by the `planner` agent into the seed file, with the
  decomposition itself read by a human before the items become
  `ready`.
- **A12 — Operational digest.** Aggregate the
  `development_work_queue` history over time so the operator can see
  throughput, bottlenecks, and human-needed escalation trends.

## Hard guarantees

- Stdlib + `reporting.execution_authority` + `reporting.approval_policy` only.
- No subprocess, no network, no `gh`, no `git`.
- No imports from `dashboard`, `automation`, `broker`, `agent.risk`,
  `agent.execution`, `research`.
- No mutation of research artifacts, frozen contracts, IR artifacts,
  scoring, or queue ordering.
- Atomic write under `logs/development_work_queue/latest.json` only.
- Items declare deterministic timestamp placeholders so per-item
  bytes are reproducible across runs.

## CLI surface

```
python -m reporting.development_work_queue            # writes artifact
python -m reporting.development_work_queue --no-write  # stdout only
python -m reporting.development_work_queue_status      # writes status artifact
python -m reporting.development_work_queue_status --no-write
```
