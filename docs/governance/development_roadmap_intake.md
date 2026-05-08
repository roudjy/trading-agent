# Roadmap Intake Bridge — Step 5.0.1

> **Status:** Implemented (read-only, deterministic, dry-run).
>
> **Module:** [`reporting/development_roadmap_intake.py`](../../reporting/development_roadmap_intake.py)
> **Status reporter:** [`reporting/development_roadmap_intake_status.py`](../../reporting/development_roadmap_intake_status.py)
> **Output artifact:** `logs/development_roadmap_intake/latest.json`
> **Status artifact:** `logs/development_roadmap_intake_status/latest.json`
>
> **Authority:** development-governance read-only.
> ADE roadmap intake is **not** trading or research execution authority.

---

## 1. Purpose

ADE's autonomous-development surface (A8 work queue, A10 bugfix loop,
A11 delegation, A14 Step 5.0 dry-run planner) can plan from existing
queue / bugfix / delegation artefacts, but until now it had no
deterministic path to pick up real roadmap work straight from:

- [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — canonical QRE roadmap;
- [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md) — diagnostic-layer extension;
- [`docs/roadmap/qre_roadmap_v6_phase_prompts.md`](../roadmap/qre_roadmap_v6_phase_prompts.md) — phase prompts;
- [`docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`](../roadmap/qre_roadmap_v6_ade_operating_manual.md) — ADE operating manual.

A11 deliberately does **not** fuzzy-parse roadmap prose. The Roadmap
Intake Bridge fills the gap **without** widening A11: it reads only
explicit, machine-readable markers and emits read-only candidate
records. Operator promotion into the actual queue or delegation
pipeline remains a separate manual step.

Existing Roadmap v6 stays canonical. The Addendum is treated as an
**extension** (not a replacement). The phase-prompts and operating-
manual docs are explicit additional sources, distinguished by
`source_kind`.

---

## 2. Scope and non-scope

In scope:

- Read-only, deterministic parsing of explicit
  `<!-- ade_roadmap_intake ... -->` markers in the four canonical
  source documents.
- Per-candidate `execution_authority` classification via
  `reporting.execution_authority.classify(...)` against the marker's
  `target_path` and `risk_level`.
- Closed-vocabulary candidate records with bounded scalars only —
  no PR text, no diffs, no command summary.
- Atomic write of `logs/development_roadmap_intake/latest.json`.
- Compact status summary at
  `logs/development_roadmap_intake_status/latest.json` counting by
  `source_kind`, `candidate_kind`, `intake_status`, and
  `execution_authority_decision`.

Non-scope (hard constraints):

- **No Step 5.1, no Step 5.2.** `step5_implementation_allowed`
  remains `False`. `STEP5_ENABLED_SUBSTAGE` remains `"none"`. The
  autonomy ladder cap is unchanged. The autonomy-ladder ceiling
  permanently disables fully autonomous merge / deploy.
- No automatic promotion into
  `docs/development_work_queue/seed.jsonl` or
  `docs/development_work_queue/delegation_seed.jsonl`. Promotion is
  an explicit operator action.
- No mutation of any roadmap, addendum, phase-prompt, or operating-
  manual document.
- No edit of canonical roadmap status fields. No marking of any
  roadmap phase as complete.
- No fuzzy parsing of prose, headings, lists, or bullets. Plain
  Markdown is invisible to the parser.
- No QRE behaviour change. No research-artifact mutation. No
  Intelligent Routing change.
- No subprocess, no network, no `gh`, no `git`. No LLM calls. No
  external APIs. Stdlib + the existing ADE/reporting dependencies
  only.
- No imports of `dashboard`, `automation`, `broker`, `agent.risk`,
  `agent.execution`, `research`, `reporting.intelligent_routing`.
- No edit of `.claude/**`. No edit of trading / paper / shadow /
  risk / broker / execution surfaces.
- Diagnostics do not trade. ADE roadmap intake is development
  governance only.

---

## 3. Marker grammar (closed)

A roadmap-intake candidate is created **only** by an explicit HTML
comment marker inside one of the four canonical source documents.
The marker grammar is:

```
<!-- ade_roadmap_intake
candidate_id: <opaque-stable-id, [A-Za-z0-9_.-]+, ≤96 chars>
phase: <≤64 chars; e.g. v3.15.16, v3.15.17, addendum>
title: <≤200 chars>
category: <one of: docs | reporting | governance | observability | test>
required_agent_role: <one of A8 AGENT_ROLES>
risk_level: <LOW | MEDIUM | HIGH | UNKNOWN>
target_path: <repo-relative POSIX path, ≤300 chars>
human_needed: <true | false>
human_needed_reason: <closed reason; "none" iff human_needed=false>
acceptance_criteria:
  - <≤200 chars>
  - <…>
-->
```

Every required field must be present and pass the closed-vocab
check. Any failure drops the marker with a `validation_warning`,
never silent promotion.

Use markers sparingly. The four source documents must remain
human-readable. Markers are appropriate for explicit, approved
hand-off anchors. Bulk decomposition belongs elsewhere (the A8 / A11
sidecar seed pipelines).

---

## 4. Closed vocabularies

| Vocabulary           | Members                                                                                             |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| `intake_status`      | `proposed`, `eligible`, `blocked`, `human_needed`, `rejected`                                       |
| `source_kind`        | `roadmap_v6`, `roadmap_v6_addendum`, `phase_prompt`, `operating_manual`                             |
| `candidate_kind`     | `docs`, `reporting`, `governance`, `observability`, `test`                                          |
| `promotion_target`   | `development_delegation`, `development_work_queue`, `none`                                          |
| `risk_level`         | mirrored from `reporting.execution_authority.RISK_CLASSES`                                          |
| `required_agent_role`| mirrored from `reporting.development_work_queue.AGENT_ROLES`                                        |
| `human_needed_reason`| mirrored from `reporting.development_work_queue.HUMAN_NEEDED_REASONS`                               |

Adding a value to any of these vocabularies requires a code change
pinned by an updated unit test.

---

## 5. Per-candidate schema

Per-candidate keys are exact and ordered:

```
candidate_id
title
source_document
source_anchor
roadmap_phase
source_kind
candidate_kind
category
required_agent_role
risk_level
target_path
execution_authority_decision
execution_authority_reason
human_needed
human_needed_reason
intake_status
acceptance_criteria
validation_requirements
promotion_target
notes
```

`intake_status` is derived deterministically from
`(execution_authority_decision, human_needed)`:

| `human_needed` | `execution_authority_decision` | `intake_status` |
| -------------- | ------------------------------- | --------------- |
| `true`         | (any)                           | `human_needed`  |
| `false`        | `PERMANENTLY_DENIED`            | `blocked`       |
| `false`        | `NEEDS_HUMAN`                   | `human_needed`  |
| `false`        | `AUTO_ALLOWED`                  | `eligible`      |
| `false`        | (anything else / fail-safe)     | `proposed`      |

`promotion_target` is always `none` in this PR. Promotion into the
A8 work queue or A11 delegation pipeline is an explicit operator
action or a later, explicitly approved bridge.

---

## 6. Step 5.0 consumption

After operator promotion of a `latest.json` candidate into the A8
work queue or A11 delegation pipeline, `development_step5_loop` can
consume it like any other upstream item. The Step 5.0 loop already
selects from delegation → bugfix → queue in deterministic order;
the Roadmap Intake Bridge feeds those producers, never Step 5.0
directly.

The bridge does **not** change anything about how Step 5.0 selects
or classifies items. It only widens the input surface from "operator
sidecar seed" to "operator sidecar seed + explicit roadmap markers."

---

## 7. CLI

```sh
# Pure inspection — does not write artifacts:
python -m reporting.development_roadmap_intake --no-write
python -m reporting.development_roadmap_intake_status --no-write

# Writes logs/development_roadmap_intake[_status]/latest.json:
python -m reporting.development_roadmap_intake
python -m reporting.development_roadmap_intake_status
```

Both modules are pure-stdlib + existing ADE/reporting dependencies.
No subprocess, no network, no git/gh.

---

## 8. Determinism contract

- Per-candidate ordering: `(source_kind, candidate_id)` ascending.
- All free-text fields bounded.
- Output is `json.dumps(..., sort_keys=True, indent=2) + "\n"`.
- `generated_at_utc` is the only non-deterministic field; tests
  inject it.
- Atomic write via `os.replace(...)` from a same-directory
  `tempfile.mkstemp(...)`.

---

## 9. Authority chain

| Concern                         | Owner                                                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------- |
| Marker grammar / vocabularies   | This document + the unit tests.                                                        |
| Authority classification        | [`docs/governance/execution_authority.md`](execution_authority.md) (canonical).        |
| Step 5 sub-stage cap            | [`docs/governance/step5_design.md`](step5_design.md) §12 + ADR-017.                    |
| Roadmap canonical status        | [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) (canonical).                |
| Roadmap diagnostic extension    | [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md).        |
| Autonomy ladder                 | [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md) + ADR-015.                  |

---

## 10. Test coverage

Pinned in
[`tests/unit/test_development_roadmap_intake.py`](../../tests/unit/test_development_roadmap_intake.py)
and
[`tests/unit/test_development_roadmap_intake_status.py`](../../tests/unit/test_development_roadmap_intake_status.py):

- Plain Markdown headings produce zero candidates.
- Explicit valid marker produces exactly one candidate.
- Invalid marker fields produce a `validation_warning`, never a
  candidate.
- Archive paths under `docs/roadmap/archive/` are excluded.
- Non-canonical source paths are excluded with a warning.
- AUTO_ALLOWED `target_path` resolves to `intake_status=eligible`.
- Protected `target_path` (canonical roadmap, governance hook,
  policy doc, etc.) resolves to `human_needed` or `blocked`.
- AST scan asserts no imports of research/live/paper/shadow/risk/
  broker/execution surfaces.
- AST/source scan asserts no `subprocess` / `socket` / `urllib` /
  `http` / `requests` references and no `gh` / `git` references.
- Output is deterministic byte-for-byte with an injected
  `generated_at_utc`.
- Atomic write refuses any path outside
  `logs/development_roadmap_intake/`.
- Status summary counts by `source_kind`, `candidate_kind`,
  `intake_status`, `execution_authority_decision`.
- Roadmap v6 Addendum extension framing preserved in the doc.
