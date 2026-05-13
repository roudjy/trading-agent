# A18c Admission Integration — Design / Governance Source-of-Truth

> **Status:** **Implemented (default-disabled, env-gated).** This
> doc remains the design / governance source-of-truth for the
> A18c admission projector. The implementation lives at
> [`reporting/development_generated_lane_a18c.py`](../../reporting/development_generated_lane_a18c.py)
> with companion tests at
> [`tests/unit/test_development_generated_lane_a18c.py`](../../tests/unit/test_development_generated_lane_a18c.py).
> The env-gate `ADE_GENERATED_LANE_A18C_ENABLED` (enabled value:
> the exact literal string `"true"`) is **unset** in all
> environments today; runtime activation remains a strictly
> later operator-only VPS step gated by
> `GO enable A18c on VPS`.
>
> **Authority:** development-governance read-only documentation
> plus a default-disabled projector module. This doc and module
> together grant ADE **zero** new runtime authority while the
> env-gate stays unset. The module is the canonical surface; this
> doc is the design / governance source-of-truth. A17 remains
> authoritative; A18c never modifies A17 and never relaxes any
> A17 filter.
>
> **Permanent denials (re-asserted):**
>
> * `step5_implementation_allowed = false` (unchanged)
> * `STEP5_ENABLED_SUBSTAGE = "none"` (unchanged)
> * Level 6 is permanently disabled per ADR-015 §Doctrine 1.
> * No autonomous merge / deploy / trade / approval.
> * No approval can happen from a notification click alone.
> * No `gh pr merge`, no `gh pr review --approve`, no `--admin`,
>   no branch-protection bypass, no force push, no
>   `seed.jsonl` / `delegation_seed.jsonl` write, no `.claude/**`
>   edit, no `.gitleaks.toml` edit, no test weakening, no hook
>   bypass.

---

## 1. Status

* **Implemented (default-disabled, env-gated).** This document
  remains the design / governance source-of-truth for the A18c
  admission projector module. The implementation is **default-
  disabled** — when the env-gate is unset (or set to anything
  other than the exact string `"true"`), A18c returns a no-op
  envelope without reading `generated_seed.jsonl` at all.
* **A18a** dry-run / report-only projector is implemented at
  [`reporting/development_generated_lane.py`](../../reporting/development_generated_lane.py).
* **A18b** `generated_seed.jsonl` writer is implemented at
  [`reporting/development_generated_lane_writer.py`](../../reporting/development_generated_lane_writer.py).
  It is default-disabled, env-gated, and was exercised in the
  Phase 2 controlled production write smoke; one diagnostic row
  exists on disk.
* **A18c** admission projector is implemented at
  [`reporting/development_generated_lane_a18c.py`](../../reporting/development_generated_lane_a18c.py).
  Phase 4 implementation was authorised by the explicit
  operator-go phrase `GO A18c admission integration`. The
  module reads `generated_seed.jsonl` only when the env-gate
  `ADE_GENERATED_LANE_A18C_ENABLED` is set to exactly the
  literal string `"true"` (case-sensitive, no aliases). A17
  remains authoritative; A18c calls
  `a17.evaluate_promotion_record(...)` verbatim and never
  modifies A17. The A17 admission policy module
  ([`reporting/development_queue_admission_policy.py`](../../reporting/development_queue_admission_policy.py))
  is byte-identical pre- and post-Phase-4 — A18c is an
  independent projector that consumes A17's public surface.
* **No runtime authority while env-gate unset.** A18c grants
  ADE zero new capability until an operator separately exports
  the env on VPS. Setting the env is a strictly later
  operator-only step gated by `GO enable A18c on VPS`.
* **No UI action exists.** The PWA's `/agent-control/*` surface
  must not render an A18c admission button pointed at any
  endpoint.
* **Runtime activation requires the separate explicit
  operator-go phrase** `GO enable A18c on VPS`. The plan doc
  identifies it but does not request it.

The companion pin-tests in
[`tests/unit/test_development_generated_lane_a18c_plan.py`](../../tests/unit/test_development_generated_lane_a18c_plan.py)
enforce these claims.

---

## 2. Scope

### 2.1 What A18c would eventually cover (if ever approved)

A bounded, default-disabled, env-gated **projector** that reads
the existing `generated_seed.jsonl` file (which A18b writes) and
projects eligible rows into the A17 admission flow as an
additional, closed-vocab admission source.

The hypothetical adapter, if ever built, would:

* read `generated_seed.jsonl` only when the env-gate is
  exactly `"true"` (default-disabled);
* project each row into A17's existing closed
  `ADMISSION_DECISIONS` and `ADMISSION_REASONS` vocabularies
  with no new decision verbs;
* never execute work;
* never mint or verify approval tokens;
* never open / merge / close a PR;
* never deploy;
* never modify `generated_seed.jsonl` (A18b writer is the only
  authority for that file);
* never modify `seed.jsonl` or `delegation_seed.jsonl`;
* never re-classify A17's existing closed vocabularies;
* never write outside its own bounded artefact path under
  `logs/development_generated_lane_a18c/` (sentinel-restricted).

A17 remains authoritative. A18c is a **source projector** that
fans into A17's existing policy — it is not a replacement for
A17 and not an alternative admission path.

### 2.2 What A18c explicitly does not cover

* **Autonomous execution.** Forbidden. A18c is read-only.
* **Autonomous PR creation.** Forbidden. PR creation is Step 5.2
  territory and remains plan-only at this stage.
* **Autonomous merge.** Forbidden. Live merge is N5b Phase 2/3/4
  territory and remains plan-only.
* **Autonomous deploy.** Forbidden. Deploy stays
  `workflow_run`-chained after Fast pre-merge gate.
* **Autonomous trading.** Forbidden. A18c is a development-lane
  surface and never touches `live/**`, `paper/**`, `shadow/**`,
  `risk/**`, `broker/**`, `execution/**`, `research/**`, or any
  agent / strategy / portfolio module.
* **Step 5 substage promotion.** Forbidden. `step5_implementation_allowed`
  remains `false` and `STEP5_ENABLED_SUBSTAGE` remains `"none"`.
* **Level 6.** Forbidden. Level 6 is permanently disabled per
  ADR-015 §Doctrine 1.
* **Seed-file mutation.** Forbidden. A18c does not write any
  `seed.jsonl`, `delegation_seed.jsonl`, or `generated_seed.jsonl`
  record.

---

## 3. Operational purpose

When (and only when) an operator separately activates the
env-gate on VPS, A18c will:

1. Read the on-disk `generated_seed.jsonl` rows at the canonical
   path `/root/trading-agent/generated_seed.jsonl` (host) or
   `/app/generated_seed.jsonl` (dashboard container — same inode
   when the file-level bind mount is in place, see §16).
2. Apply A18b's closed schema validation (12 keys, exact
   match; otherwise default-deny).
3. For each valid row, build a closed-schema admission record
   keyed in A17's existing `ADMISSION_SCHEMA_KEYS` vocabulary —
   no new keys, no new decision verbs.
4. Apply A17's existing filters verbatim. No filter is relaxed
   for the generated-lane source. No "soft" path is added.
5. Emit a closed envelope under
   `logs/development_generated_lane_a18c/latest.json` (atomic
   tmp + `os.replace`; sentinel-restricted to that prefix).

A17 remains the policy authority. A18c does not promote, admit,
or queue any record — it produces a read-only projection that an
operator (or a future operator-paced Phase-5 promotion rule)
inspects and decides about.

---

## 4. Proposed admission schema

A18c's per-row projection record uses **A17's existing closed
`ADMISSION_SCHEMA_KEYS` vocabulary verbatim**. The full key set
appears in
[`reporting/development_queue_admission_policy.py`](../../reporting/development_queue_admission_policy.py)
and is reproduced here for traceability (any drift in the A17
module's key set fails the companion pin-test):

```
candidate_id                              # bounded; derived per §7
title                                     # from A18b row's proposed_title
source_document                           # canonical generated_seed.jsonl path
source_kind                               # "generated_seed_lane"
roadmap_phase                             # "" (not surfaced by A18b)
candidate_kind                            # from A18b row's proposed_kind
required_agent_role                       # "" or "operator" per §5
risk_level                                # closed A17 vocab; per §5
target_path                               # "" (not surfaced by A18b)
upstream_intake_status                    # "generated_seed_present"
upstream_decision_state                   # closed; per §5
upstream_execution_authority_decision     # closed; "needs_human" default
reclassified_execution_authority_decision # closed; mirrors upstream by default
classification_drift                      # bool; false by default
human_needed                              # bool; per §5
human_needed_reason                       # closed A17 vocab
admission_decision                        # closed A17 ADMISSION_DECISIONS
admission_reason                          # closed A17 ADMISSION_REASONS
would_target_lane                         # closed A17 PROMOTION_TARGETS
already_in_seed_jsonl                     # bool; A17 cross-check
already_in_delegation_seed                # bool; A17 cross-check
policy_version                            # A17's MODULE_VERSION
evaluated_at                              # ISO 8601 UTC, Z-terminated
```

All scalars bounded; no PR body, no diff content, no commit
message, no execution payload. The closed key set is exact; any
key drift fails admission with the closed-vocab equivalent of
A17's `invalid_record_schema`-style outcome.

---

## 5. Closed admission-decision and admission-reason mapping

A18c MUST emit only values from A17's existing closed
`ADMISSION_DECISIONS` and `ADMISSION_REASONS` tuples. No new
decision verb is introduced.

**Decision mapping (default semantics; per-row evaluation):**

| A18b row attribute | A18c default admission_decision |
|---|---|
| `would_require_operator_go = True` | `needs_human` (never `admissible`) |
| `would_require_operator_go = False` and any A17 filter fails | corresponding A17 outcome (`needs_human` / `blocked` / `duplicate_of_existing` / `not_eligible_upstream`) |
| `would_require_operator_go = False` and every A17 filter passes | `admissible` **only** if a future Phase-5-style operator-approved promotion rule explicitly authorises the row's promotion; otherwise `needs_human` |
| `evidence_hash` matches an existing seed row's hash | `duplicate_of_existing` with reason `already_in_seed_jsonl` or `already_in_delegation_seed` per A17 cross-check |
| A18b `proposed_kind` not in closed A18a `PROPOSED_KINDS` | `blocked` with reason `blocked_classification_drift_to_denied` |

**Reason mapping (canonical, partial; see A17's full
`ADMISSION_REASONS` for the closed set):**

* `would_require_operator_go = True` → `needs_human_authority_decision`.
* Protected target path detected by A17 filter → `needs_human_protected_target_path`.
* Upstream intake status non-eligible → `upstream_intake_status_not_eligible`.
* Already promoted upstream → `already_in_seed_jsonl` / `already_in_delegation_seed`.

The safety property this encodes: **A18b rows with
`would_require_operator_go=True` can never be auto-admissible.**

---

## 6. Proposed env gate

* **Name:** `ADE_GENERATED_LANE_A18C_ENABLED`
* **Enabled value:** the exact literal string `true` (case-sensitive,
  no aliases). Anything else — empty, `"false"`, `"1"`, `"yes"`,
  `"True"`, `"TRUE"`, unset — leaves A18c in zero-projection
  mode.
* **Default:** unset. The env-gate is **not** flipped by this
  plan PR. It is **not** flipped by the eventual Phase 4
  implementation PR either. Flipping it is a strictly later,
  operator-only VPS step gated by `GO enable A18c on VPS`.
* **Read at call time** (not at import time). The Phase 4
  implementation must mirror A18b's pattern: read the env
  mapping at each evaluate call, never cache, never read at
  import time.
* **Kill switch.** Unsetting the env-gate immediately returns
  A18c to zero-projection mode on the next tick. No state
  persists across the env flip. See §13.

---

## 7. Candidate id and idempotency

A18c-projected candidate ids are deterministic functions of the
underlying A18b row:

```
candidate_id_a18c = f"a18c-{generated_candidate_id_a18b}-{evidence_hash_short}"
```

where `evidence_hash_short = evidence_hash[:16]`. The full
A18b `generated_candidate_id` and full `evidence_hash` are
preserved in the A18c admission record's other fields; the
candidate-id derivation is for downstream-stable identification
only.

**Idempotency:** A18c may run repeatedly (per-tick under the
recurring-maintenance scheduler, once Phase 4 ships and is
activated). The same A18b row across N ticks yields the same
A18c candidate-id, the same closed schema, the same closed
admission decision and reason. No tick produces side effects on
the upstream `generated_seed.jsonl`.

---

## 8. Duplicate handling

* **Duplicate candidate-id within A18c's own projection** → hard
  reject the second occurrence; closed-vocab equivalent of
  A18b's `duplicate_candidate_id`. The projection envelope
  records the rejection but does not delete the prior row from
  the artefact.
* **Duplicate `evidence_hash` with a different
  `generated_candidate_id`** → soft warning (mirrors A18b's
  `duplicate_evidence_hash` pattern). The projection is still
  emitted; A17's `already_in_seed_jsonl` / `already_in_delegation_seed`
  filters fire if the duplicate evidence-hash also matches an
  existing seed-row provenance.
* **A18b row already represented in `seed.jsonl` or
  `delegation_seed.jsonl`** → `duplicate_of_existing` with the
  appropriate `already_in_*` reason. A17's existing cross-check
  is reused verbatim.

---

## 9. Evidence-hash / provenance binding

A18c surfaces the A18b row's `evidence_hash` value **verbatim**
in the admission record. It does not recompute, hash again, or
re-anchor provenance. The hash's interpretation is whatever
the operator chose at A18b write time (per the
[`a18b_writer_host_side_write_runbook.md`](a18b_writer_host_side_write_runbook.md)
the canonical shape is `hashlib.sha256(<non-secret-marker>.encode("utf-8")).hexdigest()`).

A18c does not infer execution-authority or admission-authority
from the evidence hash; the hash is a provenance marker for
forensic traceability, not an authorisation token.

---

## 10. Max caps per tick / per day

* **Per-tick cap:** `8` projections. Any A18c tick that finds
  more than 8 eligible A18b rows projects only the first 8
  (oldest-first ordering) and surfaces a closed-vocab warning;
  remaining rows are eligible on the next tick.
* **Per-day cap:** `32` projections (UTC day-boundary). Any
  A18c tick that would push the running per-day projection count
  past 32 stops emitting and surfaces a closed-vocab warning;
  remaining rows are eligible on the next UTC day.

These caps are intentionally low relative to A18b's `256` max
records and to A17's own bounds, reflecting the operator-paced
rollout posture. The caps are advisory — A17's filters remain
authoritative; A18c never bypasses an A17 filter by hitting a
cap.

The exact integer values are pinned in the companion test so
any future change is a deliberate doc + test update.

---

## 11. Stop conditions

A18c must default-deny and emit a closed-vocab failure envelope
when any of:

* `generated_seed.jsonl` is unreadable or absent;
* any line of `generated_seed.jsonl` fails A18b's closed-schema
  validation;
* the per-tick or per-day cap is reached;
* an A17 filter trips on a projected row;
* the env-gate flag value is not exactly `"true"`;
* the audit-artefact path is not within the sentinel prefix
  `logs/development_generated_lane_a18c/`;
* `assert_no_secrets` raises on the projection record or the
  envelope;
* the Phase-2 diagnostic row is encountered (see §15) — A18c
  must project it as `needs_human` regardless of other filter
  outcomes.

None of these conditions raise; A18c surfaces them as closed
envelope statuses.

---

## 12. Rollback

A18c rollback is the env-flag flip plus a single PR revert at
most:

1. **Env-flag off** (`unset ADE_GENERATED_LANE_A18C_ENABLED` or
   set to anything other than the exact string `"true"`).
2. A18c's next tick returns zero projections.
3. Existing A17 artefacts under
   `logs/development_queue_admission_policy/` remain unchanged.
4. Existing `generated_seed.jsonl` remains unchanged (A18c never
   writes to it).
5. If desired, revert the Phase 4 implementation PR; A18c's
   on-disk projection artefacts under
   `logs/development_generated_lane_a18c/` may be deleted
   manually by the operator (not by code).

No on-disk state outside `logs/development_generated_lane_a18c/`
is touched by A18c, so rollback never threatens upstream A17 or
A18a/A18b state.

---

## 13. Kill switch

The env-gate **is** the kill switch. Setting
`ADE_GENERATED_LANE_A18C_ENABLED` to anything other than the
exact string `"true"` immediately returns A18c to
zero-projection mode on the next call. The kill switch is
host-controlled (operator unsets the env in the dashboard
container) and is independent of A18b's
`ADE_GENERATED_LANE_WRITER_ENABLED` flag — disabling A18c does
not disable A18b's writer, and vice versa.

---

## 14. Malformed `generated_seed.jsonl` — default-deny

If any line of `generated_seed.jsonl` fails A18b's closed-schema
validation (12 keys exact, type/bound checks), A18c does NOT
crash and does NOT skip the malformed line silently. It:

* halts that tick's projection;
* surfaces a closed-vocab warning (mirroring A18b's
  `existing_file_malformed` pattern);
* emits zero admission projections for that tick;
* logs the event in its own bounded audit artefact;
* does not modify the upstream `generated_seed.jsonl`.

Default-deny is a hard invariant. A18c never makes a "best
effort" projection on partial data.

---

## 15. Phase-2 diagnostic row handling

The Phase-2 controlled production write smoke wrote exactly one
diagnostic row to `generated_seed.jsonl`:

* `generated_candidate_id`: `a18b-phase2-smoke-2026-05-13-001`
* `source_module`: `operator_phase2_smoke`
* `proposed_kind`: `e2e_proof`
* `admission_preview`: `generated_seed_written`
* `would_require_operator_go`: `true`
* `proposed_summary` explicitly forbids admission, execution,
  promotion, merge, deploy.

**Mandatory A18c behaviour:** this diagnostic row must NEVER
become auto-admissible, NEVER become executable, and NEVER
become a queue-execution candidate. The decision-mapping table
in §5 already enforces this via the
`would_require_operator_go = True → needs_human` rule. The
plan additionally pins:

* A18c's evaluation of the diagnostic row produces
  `admission_decision = "needs_human"` with reason
  `needs_human_authority_decision` regardless of any other
  attribute matching the auto-admissible filter set.
* The row may be re-classified `blocked` if a future filter
  detects a protected-target-path attempt or a
  classification-drift signal, but never `admissible`.
* The row may only become `admissible` if a future
  Phase-5-style operator-approved promotion rule explicitly
  authorises this exact `generated_candidate_id`. Without such
  an explicit promotion rule, the row remains diagnostic /
  blocked indefinitely.

The companion pin-test asserts the plan doc contains the exact
`generated_candidate_id` string and the safety-property
language verbatim.

---

## 16. A18b writer topology decision

The A18b writer performs an atomic-replace
(`os.replace(tmp, target)`); the canonical seed path on VPS is
currently a **file-level bind mount**
`/root/trading-agent/generated_seed.jsonl → /app/generated_seed.jsonl`.
The Phase 2 incident proved that container-side
`os.replace` against the bind-mount target produces
`OSError: [Errno 16] Device or resource busy`. The
operationally-pinned procedure is captured in
[`a18b_writer_host_side_write_runbook.md`](a18b_writer_host_side_write_runbook.md):

* **Option α — currently operationally pinned.** Host-side
  write under a per-command env prefix, followed by a dashboard
  recreate so the container's bind-mount view resolves the new
  inode. This is what the Phase 2 smoke used. Sufficient for
  operator-paced writes (Phase 2, future Phase 5b/5c
  operator-promotions).
* **Option β2 — future decision, not implemented here.**
  Migrate `generated_seed.jsonl` to a dedicated subdirectory
  (e.g. `/root/trading-agent/var/generated_lane/`) and add a
  directory-level bind mount of that subdirectory to the
  dashboard container. The writer's `os.replace` would then
  succeed in-container because both `tmp` and `target` would
  live inside the same bind-mounted directory. The writer
  module's `GENERATED_SEED_PATH` constant would need to move; a
  small code PR plus a compose change would be required.

A18c implementation (Phase 4) does NOT depend on Option β2 in
the simple case: A18c is a **reader** of `generated_seed.jsonl`,
and reads work fine through the existing file-level bind mount.
The Option β2 question becomes a real correctness issue only if
a future write-then-read-within-same-process pattern emerges
(e.g. a Phase-5b operator-promotion that writes from inside the
dashboard process and immediately admits via A18c without a
container recreate). In that scenario, Option β2 is the
principled fix and the Phase 4 implementation PR or a
subsequent Phase 5 PR may include it.

**This plan-only PR does not implement Option β2.** The plan
records it as an explicit future decision point that the
operator may raise between Phase 4 implementation merge and
`GO enable A18c on VPS`.

---

## 17. Explicit hard denials

A18c, in this plan and in any future implementation, must not:

* execute work;
* open / merge / close a PR;
* trigger a deploy workflow;
* trigger a trade, broker, risk, execution, or research path;
* mint or verify approval tokens;
* enable Step 5.0 / 5.1 / 5.2;
* flip `step5_implementation_allowed`;
* change `STEP5_ENABLED_SUBSTAGE`;
* enable Level 6 (permanently disabled per ADR-015);
* write `seed.jsonl` or `delegation_seed.jsonl`;
* mutate `generated_seed.jsonl` (A18b writer is the only
  authority);
* bypass any A17 filter;
* introduce a new admission decision or reason value;
* re-classify an A17 closed-vocab value;
* send any push notification;
* register a Flask blueprint;
* touch `dashboard/dashboard.py` (no-touch hook applies);
* touch `frontend/**`;
* touch `.claude/**`, `.gitleaks.toml`, `research/**`,
  `live/**`, `paper/**`, `shadow/**`, `risk/**`, `broker/**`,
  `execution/**`;
* store secrets in repo, logs, public artifacts, PR bodies, or
  test output.

The companion pin-test scans the plan doc's executable surface
(its fenced code blocks) for the imperative shapes of each
denial above and refuses any future drift.

---

## 18. Step 5 and Level 6 invariants

Level 6 is **permanently disabled** per ADR-015 §Doctrine 1 and
is **never** raised by this plan. The six invariants below are
re-asserted on every line of this plan:

```
step5_implementation_allowed = false
STEP5_ENABLED_SUBSTAGE        = "none"
level6_enabled                = false
dry_run_only                  = true
live_merge_implemented        = false
deploy_coupled                = false
```

A18c emits these literal values into its `discipline_invariants`
dict on every projection envelope when (and only when) the
Phase 4 implementation lands. Until then no envelope is
emitted.

---

## 19. Cross-references

* [`docs/governance/development_generated_lane.md`](development_generated_lane.md)
  — A18a / A18b governance and writer contract.
* [`docs/governance/a18b_writer_host_side_write_runbook.md`](a18b_writer_host_side_write_runbook.md)
  — Phase-2 follow-up runbook codifying Option α host-side
  write + remount; referenced by §16 above.
* [`docs/governance/autonomous_development_baseline_observation.md`](autonomous_development_baseline_observation.md)
  — Phase 0 baseline observation chain; the rest state every
  A18c projection must converge to before and after.
* [`docs/governance/queue_admission_policy.md`](queue_admission_policy.md)
  — A17 admission policy governance doc; A18c projects through
  A17's existing closed vocabularies.
* [`reporting/development_queue_admission_policy.py`](../../reporting/development_queue_admission_policy.py)
  — A17 implementation; A18c's projection schema mirrors A17's
  `ADMISSION_SCHEMA_KEYS` verbatim.
* [`reporting/development_generated_lane_writer.py`](../../reporting/development_generated_lane_writer.py)
  — A18b implementation; A18c reads the file A18b writes.
* [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — N5b governance / plan-only doc; reasserts the live-merge
  invariants A18c also preserves.
* [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — authority doctrine.
* [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — Level 6 permanently-disabled doctrine.
* [`docs/governance/execution_authority.md`](execution_authority.md)
  — per-action authority decisions.
* [`docs/governance/no_touch_paths.md`](no_touch_paths.md) —
  the protected paths.
* [`reporting/development_generated_lane_promotion_report.py`](../../reporting/development_generated_lane_promotion_report.py)
  — read-only promotion-readiness report consumer (Phase 5a).
  Reports on what *would* be required for operator-promote;
  never promotes. Hard-pinned `promotion_allowed=false` on every
  row.
