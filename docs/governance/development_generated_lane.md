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
* A18c (A17 admission integration) remains unimplemented and
  requires its own explicit operator go-signal. A18b (writer)
  is now implemented as a separate module
  (`reporting/development_generated_lane_writer.py`); see §7.

---

## 7. A18b — generated_seed.jsonl writer (default-disabled)

> **Status:** Implemented (v3.15.16.A18b).
>
> **Module:** [`reporting/development_generated_lane_writer.py`](../../reporting/development_generated_lane_writer.py)
>
> **Authority:** development-governance read-only documentation +
> operator-gated runtime writer.
> A18b is the writer slice. It is **default-disabled** and only
> appends to `generated_seed.jsonl` when the operator has
> explicitly exported the exact-string env value:
>
>     ADE_GENERATED_LANE_WRITER_ENABLED=true
>
> Anything else (unset, `""`, `"false"`, `"1"`, `"yes"`, `"True"`,
> `"TRUE"`, `"on"`) leaves the writer in **zero-write** mode. The
> public API returns `status="skipped"` and creates no files of
> any kind — not even the audit log.
> Level 6 stays permanently disabled. The writer **registers**
> only; it does **not** admit, execute, open PRs, merge, deploy,
> or call the network.

### 7.1 Public API

The module exposes a small, explicit, deterministic API:

* `writer_enabled(env=None) -> bool` — reads the env mapping at
  *call time*, not at import time. Defaults to `os.environ`.
* `validate_record(record) -> (ok, stop_status, warnings)` —
  pure record validator against the 12-key closed schema.
* `append_generated_seed_record(record, *, generated_seed_path=None, audit_path=None, env=None, now_utc=None) -> dict` —
  main entry point. Returns the closed-shape return envelope
  documented in §7.4.

No environment is read at import time. No file is written at
import time. The module is safe to import even when the env-gate
is already set to `true` — no write happens until
`append_generated_seed_record(...)` is called explicitly.

### 7.2 Closed record schema (12 keys, exact and ordered)

```
generated_candidate_id      str, ≤ 128
source_module               str, ≤ 200
source_id                   str, ≤ 200
proposed_kind               closed vocab (A18a's PROPOSED_KINDS)
proposed_title              str, ≤ 120
proposed_summary            str, ≤ 300
evidence_hash               str, ≤ 128
admission_preview           closed vocab (WRITER_ADMISSION_PREVIEWS)
block_reason                closed vocab (WRITER_BLOCK_REASONS)
would_require_operator_go   bool
generated_at_utc            ISO 8601 string
writer_module_version       str (= "v3.15.16.A18b")
```

### 7.3 Closed vocabularies (A18b extensions of A18a, additive)

```
WRITER_ADMISSION_PREVIEWS = ("report_only_not_admitted",
                             "generated_seed_written")

WRITER_BLOCK_REASONS = ("none",
                        "writer_disabled",
                        "invalid_record_schema",
                        "duplicate_candidate_id",
                        "max_records_reached",
                        "path_refused",
                        "secret_detected",
                        "existing_file_malformed",
                        "generated_lane_writer_not_authorized")

WRITER_WARNINGS = ("duplicate_evidence_hash",)

AUDIT_ATTEMPT_KINDS = ("written",
                       "rejected_duplicate_candidate_id",
                       "rejected_existing_file_malformed",
                       "rejected_invalid_record_schema",
                       "rejected_max_records_reached",
                       "rejected_path_refused",
                       "rejected_secret_detected",
                       "skipped_writer_disabled")
```

A18a's `ADMISSION_PREVIEWS` and `BLOCK_REASONS` remain unchanged.
The two modules coexist; A18b extends additively.

### 7.4 Return envelope

Every call to `append_generated_seed_record` returns a closed
envelope:

```
status                : "written" | "skipped" | "rejected"
stop_status           : closed-vocab WRITER_BLOCK_REASONS value
generated_candidate_id: bounded string
generated_seed_path   : str (the canonical generated_seed.jsonl path)
audit_path            : str (logs/development_generated_lane_writer/audit.jsonl)
writer_enabled        : bool
warnings              : list[str] from WRITER_WARNINGS
discipline_invariants : closed 14-key dict (see §7.5)
generated_at_utc      : ISO 8601 string
```

`assert_no_secrets` runs on the envelope before it is returned.

### 7.5 Discipline invariants (exact 14-key dict)

```
default_disabled                : True
writes_only_generated_seed_jsonl: True
writes_seed_jsonl               : False
writes_delegation_seed_jsonl    : False
admits_queue_items              : False
executes_work                   : False
creates_branches                : False
opens_prs                       : False
merges_prs                      : False
deploys                         : False
calls_network                   : False
uses_subprocess                 : False
touches_step5_flags             : False
level6_enabled                  : False
```

### 7.6 Hard write boundaries

* The single canonical write target is
  `<repo>/generated_seed.jsonl`. The path-sentinel verifies
  the basename equals exactly `generated_seed.jsonl` AND the
  parent directory equals `REPO_ROOT`. Any other path is
  rejected with `path_refused`.
* The filenames `seed.jsonl` and `delegation_seed.jsonl` are
  listed in `_FORBIDDEN_SEED_BASENAMES`. The path-sentinel
  refuses those targets explicitly — even when a caller
  overrides the kwarg.
* The audit log lives only under
  `logs/development_generated_lane_writer/audit.jsonl`. Audit
  paths outside that prefix are refused.
* No function in the writer module opens, writes, appends, or
  atomically replaces any path other than the canonical seed
  file and the audit file. The companion AST-level pin-test
  enforces this invariant.

### 7.7 Duplicate handling

* **Hard reject** on duplicate `generated_candidate_id` — the
  writer returns `rejected` / `duplicate_candidate_id` and does
  NOT append the seed row. An audit row IS appended to record
  the rejection attempt (bounded fields only: candidate id,
  timestamp, `stop_status`, `attempt_kind`; no record body is
  leaked).
* **Soft warning** on duplicate `evidence_hash` with a *different*
  `generated_candidate_id` — the record is appended and the
  envelope carries `warnings=["duplicate_evidence_hash"]`.

### 7.8 Cap

`MAX_GENERATED_SEED_RECORDS = 256`. The 257th append attempt is
rejected with `max_records_reached`.

### 7.9 Existing-file-malformed default-deny

If any line in the existing `generated_seed.jsonl` is not
parseable JSON, the writer refuses to append and returns
`rejected` / `existing_file_malformed`. The seed file is
untouched; the operator must clean it manually. An audit row
records the refusal.

### 7.10 .gitignore

`generated_seed.jsonl` is listed in the repo's `.gitignore`.
The file may exist on disk during operator-enabled testing but
must NEVER be committed. A companion pin-test asserts the
`.gitignore` membership.

### 7.11 A18a invariance (per the operator's correction)

A18b imports A18a only to consume its read-only closed
vocabularies (`PROPOSED_KINDS`, scalar-length constants). A18a
itself remains unchanged:

* A18a source file is not modified by this PR (verifiable via
  the PR's diff scope).
* `python -m reporting.development_generated_lane --no-write`
  continues to work.
* A18a continues to emit `admission_preview="report_only_not_admitted"`
  for every candidate.
* Importing A18b — even with `ADE_GENERATED_LANE_WRITER_ENABLED=true`
  set — does not create any file and does not mutate A18a's
  output.
* A18a remains report-only.

### 7.12 What A18b does NOT do

* A18b never writes to `seed.jsonl` or `delegation_seed.jsonl`.
  The basenames appear in the module only inside the
  `_FORBIDDEN_SEED_BASENAMES` blocklist constant.
* A18b never admits a queue item — A17 admission rules remain
  authoritative.
* A18b never executes work.
* A18b never opens / merges / closes a PR.
* A18b never deploys.
* A18b never mints or verifies an approval token (N4 territory).
* A18b never opens an inbox row (N3 territory).
* A18b never sends a Web Push (N2b-3 territory).
* A18b never executes a CLI subprocess and never calls `gh` /
  `git` / a network endpoint.
* A18b does not flip Step 5 flags.
* Level 6 stays permanently disabled.
* A18c (A17 admission integration) remains **not implemented**
  and requires its own explicit operator go-signal.

> For the operational caveat that A18b writes must run host-side
> while the canonical seed file is a file-level bind mount, see
> [`a18b_writer_host_side_write_runbook.md`](a18b_writer_host_side_write_runbook.md).
> For the A18c admission-integration design / governance
> source-of-truth (implemented default-disabled; not yet
> activated on VPS), see
> [`development_generated_lane_a18c_plan.md`](development_generated_lane_a18c_plan.md).
