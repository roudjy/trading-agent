# Roadmap Progress Tracker — A19 (read-only, deterministic projector)

> **Status:** Implemented (read-only, **mutates nothing**, **never
> marks any phase complete**).
>
> **Module:** [`reporting/development_roadmap_progress.py`](../../reporting/development_roadmap_progress.py)
> **Status reporter:** [`reporting/development_roadmap_progress_status.py`](../../reporting/development_roadmap_progress_status.py)
>
> **Output artefact:** `logs/development_roadmap_progress/latest.json`
> **Status artefact:** `logs/development_roadmap_progress_status/latest.json`
>
> **Authority:** development-governance read-only.
> A19 grants no agent any new authority.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

A19 joins the existing read-only ADE artefacts and emits a per-phase
progress snapshot:

- Roadmap Intake Bridge candidates per `roadmap_phase`;
- A16a Promotion Staging rows per phase;
- A17 Queue Admission Policy rows per phase;
- Step 5.0 plan history rows resolved to a phase via candidate id.

The output answers, per phase: **what's been observed, and what
state the phase is currently in**. A19 never assigns
`complete` autonomously — that remains an operator-marked state in
the canonical roadmap.

---

## 2. Hard constraints

A19 must not:

- edit canonical roadmap status fields;
- mark any roadmap phase complete (the closed
  `phase_progress_state` value `complete` is reserved for operator
  use; A19's derivation never assigns it);
- mutate any upstream artefact;
- write to `seed.jsonl`, `delegation_seed.jsonl`, or any
  `generated_seed.jsonl`;
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- send a real push;
- mint approval tokens;
- merge or deploy.

---

## 3. Closed `phase_progress_state` (6 values)

| Value                | Meaning                                                            |
| -------------------- | ------------------------------------------------------------------ |
| `not_started`        | no signal observed in any upstream artefact for this phase         |
| `intake_only`        | intake bridge sees a candidate; no promotion / admission / Step 5  |
| `promotion_active`   | A16a promotion staging has at least one row in this phase          |
| `admission_active`   | A17 admission policy has at least one row in this phase            |
| `planning_active`    | Step 5.0 has produced a `plan_emitted` for this phase              |
| `complete`           | **operator-only**; A19 never assigns this autonomously             |

Derivation priority (first match wins): planning → admission →
promotion → intake → not_started.

---

## 4. Per-row schema (15 keys)

```
roadmap_phase
intake_candidate_count
intake_eligible_count
intake_blocked_count
intake_human_needed_count
promotion_total
promotion_eligible_count
promotion_blocked_count
admission_total
admission_admissible_count
admission_blocked_count
admission_needs_human_count
step5_planned_count
step5_halted_count
phase_progress_state
```

Every row covers exactly one `roadmap_phase` value (e.g. `v3.15.16`).

---

## 5. Discipline invariants (emitted on every artefact)

```
writes_to_seed_jsonl                       = false
writes_to_delegation_seed_jsonl            = false
writes_to_generated_seed_jsonl             = false
mutates_canonical_roadmap_status_fields    = false
marks_any_phase_complete                   = false
operator_promotion_required                = true
step5_implementation_allowed               = false
step5_enabled_substage                     = "none"
diagnostics_do_not_trade                   = true
```

---

## 6. CLI

```sh
python -m reporting.development_roadmap_progress --no-write
python -m reporting.development_roadmap_progress
python -m reporting.development_roadmap_progress_status --no-write
```

Pure stdlib + read-only ADE deps. No subprocess, no network,
no `gh`, no `git`.

---

## 7. Test coverage

Pinned in [`tests/unit/test_development_roadmap_progress.py`](../../tests/unit/test_development_roadmap_progress.py)
and [`tests/unit/test_development_roadmap_progress_status.py`](../../tests/unit/test_development_roadmap_progress_status.py):

- closed `PHASE_PROGRESS_STATES`, `PHASE_ROW_KEYS` pinned exactly;
- A19 NEVER assigns `complete` (test pins this with synthetic data
  that should otherwise look complete);
- the live A15 phase `v3.15.16` lands in `planning_active` once
  Step 5.0 has produced a plan_emitted for the candidate;
- per-row counts mirror upstream;
- atomic write refuses any path outside `logs/development_roadmap_progress/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `gh`, `git`;
- importing the module does not flip Step 5 invariants.

---

## 8. What A19 does NOT do

- A19 never marks a phase complete.
- A19 never edits canonical roadmap status fields.
- A19 never writes to any seed file.
- A19 does not change Step 5.0 logic.
- A19 does not flip `step5_implementation_allowed`.
- A19 does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- A18 / N2b-3b / N3 / N4 / N5 remain unimplemented.
- Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
