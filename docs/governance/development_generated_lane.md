# A18 — Generated Queue Lane

> **Status:** A18a (dry-run / report-only projector) implemented in
> [`reporting/development_generated_lane.py`](../../reporting/development_generated_lane.py).
> **A18b** (generated_seed.jsonl writer) and **A18c** (A17
> admission integration) **remain unimplemented** and each requires
> its own explicit operator go-signal.
>
> **Authority:** development-governance read-only.
> A18a grants ADE **zero** new write authority over the queue,
> never mints approval tokens, never opens an inbox row, never
> merges, and never deploys. Step 5.1 / Step 5.2 remain BLOCKED.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

---

## 1. Purpose

The current ADE work-queue admits items via two operator-curated
sources:

* `seed.jsonl` — read by A16a intake promotion staging + A17 queue
  admission policy;
* `delegation_seed.jsonl` — read by A11 delegation + A16a + A17.

A complete autonomous-development loop would benefit from a third,
**agent-generated** lane fed by the existing read-only A10
bugfix-loop, A11 delegation, and A13 e2e-proof artefacts. **A18a is
the report-only first slice that surfaces what such a lane would
propose, without introducing any new authority.**

A18a is purely diagnostic.
**The generated_seed.jsonl writer is not authorised** in this slice.
The future A18b writer slice — which would actually create and append
to `generated_seed.jsonl` — and the A18c admission-integration slice
— which would teach A17 to read the new file — are not authorised
and will not be implemented in this slice.

---

## 2. Hard constraints (A18a)

A18a, in this PR and at runtime, must not:

* create `generated_seed.jsonl`;
* mutate `generated_seed.jsonl`, `seed.jsonl`, or
  `delegation_seed.jsonl`;
* register itself with A17 admission as an active seed source;
* enqueue or dequeue any work item;
* mint or verify any approval token;
* send any push;
* invoke `gh`, `git`, `subprocess`, or any network call;
* mutate any upstream artefact;
* edit any roadmap status field;
* mark any roadmap phase complete;
* enable Step 5.1 or Step 5.2;
* flip `step5_implementation_allowed`;
* change `STEP5_ENABLED_SUBSTAGE`;
* introduce or change Level 6 status.

The projector ships its own AST-level forbidden-import scan and
source-text scan to enforce the relevant bullets.

---

## 3. Output

A18a writes the bounded dry-run report at
[`logs/development_generated_lane/latest.json`](../../logs/development_generated_lane/).
The path is sentinel-restricted at the atomic-write boundary; any
other target is refused (pinned by tests, including explicit refusal
of `seed.jsonl`, `delegation_seed.jsonl`, and `generated_seed.jsonl`
paths).

### Wrapper schema (closed)

```
schema_version
module_version
report_kind                     # "development_generated_lane"
generated_at_utc
step5_implementation_allowed    # always false
step5_enabled_substage          # always "none"
candidate_count
candidates                      # list of closed-schema rows, ≤ 16
sources_read                    # {bugfix_loop, delegation, e2e_proof}
validation_warnings
vocabularies
discipline_invariants
note
```

### Per-candidate schema (closed, exact, ordered)

```
generated_candidate_id          # sha256(source_module + source_id)[:16]
source_module                   # development_bugfix_loop | development_delegation | development_e2e_proof
source_id                       # bounded scalar from the upstream record
proposed_kind                   # bugfix | delegation | e2e_proof | unknown
proposed_title                  # bounded ≤ 120 chars
proposed_summary                # bounded ≤ 300 chars
evidence_hash                   # sha256(source_module + source_id + "evidence")[:16]
admission_preview               # always "report_only_not_admitted"
block_reason                    # always "generated_lane_writer_not_authorized"
would_require_operator_go       # always true
```

### Closed vocabularies

* `proposed_kinds`: `bugfix`, `delegation`, `e2e_proof`, `unknown`.
* `admission_previews`: only `report_only_not_admitted`.
* `block_reasons`: only `generated_lane_writer_not_authorized`.

No decision verb (`approve`, `reject`, `merge`, `deploy`, `trade`)
appears in any vocabulary value.

### Discipline invariants (every snapshot)

```
writes_to_seed_jsonl:                false
writes_to_delegation_seed_jsonl:     false
writes_to_generated_seed_jsonl:      false
generated_seed_writer_authorized:    false
mutates_generated_seed:              false
admits_queue_items:                  false
executes_work:                       false
mints_or_verifies_approval_tokens:   false
sends_real_push:                     false
operator_promotion_required:         true
operator_go_required_for_writer:     true
step5_implementation_allowed:        false
step5_enabled_substage:              "none"
```

---

## 4. CLI

```
python -m reporting.development_generated_lane
python -m reporting.development_generated_lane --no-write
python -m reporting.development_generated_lane --indent 0
```

`--no-write` prints the snapshot to stdout only — it writes no
file. Default mode atomic-writes
`logs/development_generated_lane/latest.json` AND prints. **In
neither mode is `generated_seed.jsonl` created.**

---

## 5. Authority chain summary

| Capability                                        | Today (post-A18a)         | After A18b (future, operator-go) | After A18c (future, operator-go) |
| ------------------------------------------------- | ------------------------- | -------------------------------- | -------------------------------- |
| Read upstream bugfix/delegation/e2e artefacts     | yes (read-only)           | yes                              | yes                              |
| Project bounded candidate rows into a report      | yes                       | yes                              | yes                              |
| Create / append `generated_seed.jsonl`            | **forbidden**             | yes (operator-authorised)        | yes                              |
| Pass through A16a intake promotion                | n/a                       | n/a                              | yes (same gates as `seed.jsonl`) |
| Pass through A17 queue admission policy           | n/a                       | n/a                              | yes (same gates as `seed.jsonl`) |
| Enter A8 work queue                               | n/a                       | n/a                              | yes (same gates as `seed.jsonl`) |
| Execute / merge / deploy                          | **forbidden**             | **forbidden**                    | **forbidden**                    |
| Autonomous approval / merge / deploy              | **forbidden, Level 6**    | unchanged (Level 6 permanently disabled) | unchanged (Level 6 permanently disabled) |

A18a grants ADE zero new write authority. A18b and A18c are
operator-gated. Level 6 stays permanently disabled across all
three.

---

## 6. What A18a does NOT do

* A18a never creates `generated_seed.jsonl`. The file remains
  absent (pinned by unit test
  `test_generated_seed_jsonl_remains_absent_in_repo`).
* A18a never writes anywhere outside its sentinel directory
  (`logs/development_generated_lane/`).
* A18a never integrates with A17 admission. A17's authoritative
  filter is unchanged.
* A18a never mints or verifies an approval token (N4 territory).
* A18a never merges or deploys (N5 / future).
* A18a never opens a mobile-inbox row (N3 territory).
* A18a never sends a Web Push (N2b-3 territory).
* A18a never executes a CLI subprocess and never calls `gh` /
  `git` / a network endpoint.
* A18a does not change Step 5.0 logic.
* A18a does not flip `step5_implementation_allowed`.
* A18a does not change `STEP5_ENABLED_SUBSTAGE`.
* Step 5.1 / Step 5.2 remain BLOCKED.
* Level 6 stays permanently disabled.
* A18b (writer) and A18c (A17 admission integration) remain
  unimplemented and **each requires its own explicit operator
  go-signal**.
