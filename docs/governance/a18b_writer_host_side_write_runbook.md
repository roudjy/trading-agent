# A18b Writer — Host-Side Write + Remount Operator Runbook

> **Status:** Operationally-pinned runbook for any A18b
> `generated_seed.jsonl` write that follows the Phase-2 controlled
> production write smoke. Codifies the EBUSY incident's root cause
> and the safe procedure.
>
> **Authority:** development-governance read-only documentation.
> This runbook grants ADE **zero** new authority. It documents the
> exact dry-run-only CLI sequence the operator runs on the VPS
> when a new A18b metadata record must be appended.
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
> * No `ADE_N5B_LIVE_EXECUTE_ENABLED=true` export is requested by
>   this runbook.
> * No A18c admission integration is performed; A18c remains
>   plan-only, gated by the explicit operator-go phrase.
> * No queue admission, no execution, no PR creation, no merge,
>   no deploy.

---

## 1. Purpose

The Phase 2 controlled production write smoke succeeded only on
the host process. The first attempt — a container-side append via
`docker compose exec dashboard python3 …` — failed with
`OSError: [Errno 16] Device or resource busy` because the writer
performs an atomic-replace at
[`reporting/development_generated_lane_writer.py:514`](../../reporting/development_generated_lane_writer.py)
(`os.replace(tmp_name, path)`), and the canonical target
`/app/generated_seed.jsonl` is a **file-level bind mount** from
the host's `/root/trading-agent/generated_seed.jsonl`. The kernel
refuses to swap the target inode across a file-level bind-mount
boundary.

This runbook documents:

* the verified Phase-2 state;
* the EBUSY root cause;
* the forbidden in-container append shape (must not be retried
  while the file-level bind mount exists);
* the safe host-side append procedure with a per-command env
  prefix;
* the required post-write dashboard remount so the container's
  bind-mount view resolves the new inode;
* the invariants every write must preserve;
* the rollback procedure for the rare case where a diagnostic
  row must be removed.

The runbook is **not** an authorisation to perform a write. A
write is a separate Phase-2-shaped operator-paced action with
its own per-write approval. This runbook codifies the procedure
the operator follows when they elect to perform one.

---

## 2. Hard constraints

This runbook, the commands it prescribes, and any caller acting
on them must not:

* perform more than one write per invocation;
* retry automatically after any failure;
* modify the proposed record and retry without explicit operator
  re-approval;
* append from inside the dashboard container while
  `/app/generated_seed.jsonl` remains a file-level bind mount;
* merge any PR;
* push to `main` or force-push any branch;
* call `gh pr merge`, `gh pr review --approve`, or any other
  GitHub mutation;
* call `git merge` against `main`, `git push`, or any equivalent
  mutating Git operation;
* mint or verify approval tokens;
* execute an approve / reject decision;
* deploy anything;
* send any real push notification;
* register a Flask blueprint or wire into
  `dashboard/dashboard.py`;
* touch `frontend/**`;
* admit any record into the A17 queue (A18c remains plan-only);
* execute any code from the admitted/written record;
* enable Step 5.1 or Step 5.2;
* flip `step5_implementation_allowed`;
* change `STEP5_ENABLED_SUBSTAGE`;
* raise Level 6 (Level 6 is permanently disabled per ADR-015 §Doctrine 1);
* change QRE behaviour;
* mutate research artifacts;
* touch live / paper / shadow / risk / broker / execution paths;
* edit `.claude/**`;
* edit `.gitleaks.toml`;
* weaken or bypass tests, hooks, gates, or pin-tests;
* export `ADE_N5B_LIVE_EXECUTE_ENABLED=true`;
* write a `seed.jsonl` or `delegation_seed.jsonl` record;
* store secrets in repo, logs, public artifacts, PR bodies,
  screenshots, test output, or chat.

---

## 3. Verified Phase-2 state at the moment this runbook landed

The Phase-2 controlled production write smoke closed green with:

* host `/root/trading-agent/generated_seed.jsonl` has **1**
  diagnostic row.
* host `/root/trading-agent/logs/development_generated_lane_writer/audit.jsonl`
  has **1** audit row.
* latest audit row `attempt_kind = "written"`,
  `stop_status = "none"`.
* generated_candidate_id = `a18b-phase2-smoke-2026-05-13-001`.
* dashboard container `writer_enabled = true`,
  `record_count = 1` (after the post-write remount).
* host writer status (no env prefix) reports `writer_enabled = false`,
  `record_count = 1` (the status snapshot reads the file
  regardless of env-gate state).
* `step5_implementation_allowed = false`.
* `STEP5_ENABLED_SUBSTAGE = "none"`.
* `level6_enabled = false` (Level 6 permanently disabled per
  ADR-015 §Doctrine 1).
* N5b preflight `dry_run_only = true`,
  `live_merge_implemented = false`,
  `deploy_coupled = false`,
  `candidate_count = 0`.
* `seed.jsonl` and `delegation_seed.jsonl` remain **absent** on
  both host and container.
* dashboard + nginx services running; agent service stopped.

---

## 4. EBUSY root cause

The A18b writer's `_atomic_replace_jsonl` helper performs an
atomic-replace at
[`reporting/development_generated_lane_writer.py`](../../reporting/development_generated_lane_writer.py):

```
tempfile.mkstemp(dir=str(path.parent))
...
os.replace(tmp_name, path)
```

This is the correct pattern for atomic JSONL replacement on a
single filesystem: both `tmp_name` and `path` live in
`path.parent`, so the `os.replace` is a same-directory rename
that the kernel can satisfy atomically.

The Phase-2 caveat is mount-topological, not a writer bug:

* On the **host**, the writer's `path` is
  `/root/trading-agent/generated_seed.jsonl`. The tmp file lives
  in `/root/trading-agent/` — a single regular filesystem. The
  rename succeeds.
* Inside the **dashboard container**, the writer's `path` is
  `/app/generated_seed.jsonl`. That path is a **file-level bind
  mount** whose source is the host file. The tmp file lives in
  `/app/` — a layered union filesystem distinct from the
  bind-mount target's backing filesystem. `os.replace` is asked
  to swap the target inode across a mount boundary the kernel
  marks **`EBUSY`** (`Errno 16: Device or resource busy`).

The writer surfaces this as a Python `OSError` rather than a
closed-vocab `stop_status`. The Phase-2 failed attempt left no
seed row, no audit row, no tmp residue — operator-confirmed
clean.

**Implication.** A container-side append is forbidden while the
file-level bind mount remains in place. Any future appends must
run on the **host** process (which performs the atomic-replace
on a regular filesystem) followed by a dashboard remount (so the
container's bind-mount view resolves the new inode).

A future operator may decide to migrate to a directory-level
bind-mount strategy (e.g. relocate the seed file under
`/root/trading-agent/var/generated_lane/` and bind-mount the
directory). That migration is a **separate** operator-paced
action with its own scope proposal; until it lands, this runbook
is the operationally-pinned path.

---

## 5. Forbidden shape (must not be attempted)

Do **NOT** run the following while the file-level bind mount
remains in place. Each shape will trigger `EBUSY` (or worse —
silent partial state — if the writer's tmp-cleanup ever
regressed):

* any `docker compose -p trading-agent exec dashboard python3 -m
  reporting.development_generated_lane_writer` invocation that
  attempts to write (the CLI is status-only, but the negative
  pin defends against future drift);
* any `docker compose -p trading-agent exec dashboard python3`
  invocation that imports
  `reporting.development_generated_lane_writer` and calls
  `append_generated_seed_record(...)`;
* any in-container shell-out that constructs and pipes a record
  body into the writer's public API.

The runbook's pin-tests enforce that the executable surface of
this document (its fenced code blocks) contains no such shape.

---

## 6. Safe host-side append procedure

Run this on the **VPS host** (not inside the dashboard
container). The per-command env prefix scopes the writer-enable
flag only to the single Python child process — no global env
mutation, no compose change.

### 6.1 Preflight (read-only)

```bash
test -f /root/trading-agent/generated_seed.jsonl \
   && wc -l /root/trading-agent/generated_seed.jsonl \
   || echo "host_seed_absent"
```

```bash
cd /root/trading-agent
ADE_GENERATED_LANE_WRITER_ENABLED=true \
   python3 -m reporting.development_generated_lane_writer --no-write
```

**Expected.** Snapshot reports `writer_enabled=true` (because of
the per-command prefix), current `record_count`, and the
canonical paths. Step 5 / Level 6 invariants intact (Level 6 stays permanently disabled per ADR-015).

### 6.2 The append — exactly one attempt

Substitute the operator-chosen bounded values for the record
fields. None of the placeholder values below may contain a
secret. The marker passed to `hashlib.sha256(...)` must be a
non-secret bounded synthetic string.

```bash
cd /root/trading-agent
ADE_GENERATED_LANE_WRITER_ENABLED=true python3 - <<'PY'
import hashlib
import json

from reporting import development_generated_lane_writer as w

marker = "<operator-chosen-non-secret-marker>"
evidence_hash = hashlib.sha256(marker.encode("utf-8")).hexdigest()

now = w._utcnow()
record = {
    "generated_candidate_id": "<operator-chosen-bounded-id>",
    "source_module": "operator_paced_smoke",
    "source_id": "<operator-chosen-bounded-id>",
    "proposed_kind": "<one of: bugfix | delegation | e2e_proof | unknown>",
    "proposed_title": "<bounded, diagnostic title>",
    "proposed_summary": (
        "<bounded summary; must NOT contain a decision verb; "
        "must NOT instruct admission/execution/promotion/merge/deploy>"
    ),
    "evidence_hash": evidence_hash,
    "admission_preview": "generated_seed_written",
    "block_reason": "none",
    "would_require_operator_go": True,
    "generated_at_utc": now,
    "writer_module_version": w.MODULE_VERSION,
}

envelope = w.append_generated_seed_record(record)
print(json.dumps(envelope, indent=2, sort_keys=True))
PY
```

**Required envelope shape.** The printed envelope must satisfy:

* `status = "written"`
* `stop_status = "none"`
* `writer_enabled = true`
* `generated_candidate_id = <the operator-chosen id>`
* `generated_seed_path = "/root/trading-agent/generated_seed.jsonl"`
* `audit_path` ends in `logs/development_generated_lane_writer/audit.jsonl`
* `warnings = []`
* every `discipline_invariants.*` value matches the closed
  defaults of the writer module (`default_disabled=true`,
  `admits_queue_items=false`, `executes_work=false`,
  `creates_branches=false`, `opens_prs=false`,
  `merges_prs=false`, `deploys=false`, `calls_network=false`,
  `uses_subprocess=false`, `touches_step5_flags=false`,
  `level6_enabled=false`, `writes_seed_jsonl=false`,
  `writes_delegation_seed_jsonl=false`,
  `writes_only_generated_seed_jsonl=true`).

**Stop conditions.** Any deviation from the table above triggers
a hard stop. Do **NOT**:

* retry the heredoc with the same record;
* modify the record body and retry;
* attempt a container-side fallback.

Instead: paste the envelope back to the operator's review
channel; classify the failure mode against the writer's closed
`WRITER_BLOCK_REASONS` and `AUDIT_ATTEMPT_KINDS` vocabularies;
decide next steps separately.

### 6.3 Confirm the per-command env prefix did not leak

```bash
echo "post_command_env=${ADE_GENERATED_LANE_WRITER_ENABLED-unset}"
```

**Expected.** Exactly `post_command_env=unset`. Anything else
means the per-command prefix leaked into the shell session;
`unset ADE_GENERATED_LANE_WRITER_ENABLED` before any further
command.

---

## 7. Required post-write remount

After the host-side atomic-replace, the **inode** that backs
`/root/trading-agent/generated_seed.jsonl` is **new** (the
writer's atomic-replace produced a fresh inode and renamed it
into place). The container's file-level bind mount still
remembers the **old** inode (now unlinked from the host
directory entry but kept alive by the open mount reference).
The container will see a stale 0-line view until the dashboard
is recreated.

### 7.1 Recreate the dashboard service

```bash
cd /root/trading-agent
docker compose -p trading-agent up -d --force-recreate dashboard
```

**Expected.** The dashboard service restarts cleanly. Other
services (nginx, agent) are not recreated by this command.

### 7.2 Verify host + container convergence

```bash
wc -l /root/trading-agent/generated_seed.jsonl
docker compose -p trading-agent exec dashboard \
   wc -l /app/generated_seed.jsonl
```

**Expected.** Identical line counts on both sides.

```bash
stat --printf 'host inode=%i device=%d size=%s path=%n\n' \
   /root/trading-agent/generated_seed.jsonl
docker compose -p trading-agent exec dashboard \
   stat --printf 'ctr  inode=%i device=%d size=%s path=%n\n' \
   /app/generated_seed.jsonl
```

**Expected.** Identical `inode` and `device` values. (After the
remount the bind mount resolves the new inode; the two `stat`
lines should agree byte-for-byte except the path string.)

### 7.3 Verify dashboard writer status matches the host

```bash
docker compose -p trading-agent exec dashboard \
   python3 -m reporting.development_generated_lane_writer --no-write \
   | grep -E '"(writer_enabled|record_count|step5_implementation_allowed|step5_enabled_substage|level6_enabled)"'
```

**Expected.** `writer_enabled=true`, `record_count` equal to the
host's line count, Step 5 / Level 6 invariants intact (Level 6 stays permanently disabled per ADR-015).

### 7.4 Confirm invariants unchanged after write + remount

```bash
python3 -m reporting.development_step5_loop --no-write \
   | grep -E '"(step5_implementation_allowed|step5_enabled_substage)"'
python3 -m reporting.development_operational_digest --no-write \
   | grep -E '"step5_implementation_allowed"'
python3 -m reporting.development_merge_preflight --no-write \
   | grep -E '"(dry_run_only|live_merge_implemented|deploy_coupled|level6_enabled|step5_implementation_allowed|step5_enabled_substage|candidate_count)"'
```

**Expected.** Every closed-vocab value matches the rest-state
values documented in
[`autonomous_development_baseline_observation.md`](autonomous_development_baseline_observation.md).
No invariant flipped by the write or by the remount.

### 7.5 Confirm forbidden seed files remain absent

```bash
ls -la /root/trading-agent/seed.jsonl 2>&1 | head -3
ls -la /root/trading-agent/delegation_seed.jsonl 2>&1 | head -3
docker compose -p trading-agent exec dashboard \
   sh -c 'ls -la /app/seed.jsonl 2>&1; ls -la /app/delegation_seed.jsonl 2>&1' \
   | head -10
```

**Expected.** Every path reports `No such file or directory`.

---

## 8. Required invariants every write must preserve

The runbook's safe procedure is operationally green only when
every closed-vocab assertion below holds **before and after**
the write + remount:

```
step5_implementation_allowed = false
STEP5_ENABLED_SUBSTAGE        = "none"
level6_enabled                = false
dry_run_only                  = true
live_merge_implemented        = false
deploy_coupled                = false
```

Plus:

* `generated_seed.jsonl` line count advanced by exactly **one**
  row (the just-appended record) or remained the same on
  failure.
* `audit.jsonl` line count advanced by exactly **one** row (the
  closed-vocab `attempt_kind` for the outcome) regardless of
  success or failure mode.
* `seed.jsonl` and `delegation_seed.jsonl` remain absent.
* No queue admission row was created in any A17 / proposal /
  queue artefact.
* No execution surface fired.
* No PR / branch / merge / deploy / push / `gh` invocation
  fired.
* No env-flag enable / disable other than the per-command env
  prefix on the single writer-Python process.

If any invariant fails, the writer's path-sentinel and
default-deny behaviour already refused or rolled back the write;
the operator must still verify the closed-vocab values above
before treating the write as complete.

---

## 9. Rollback — operator-only, manual

The runbook does **not** authorise any agent code to remove a
diagnostic row from `generated_seed.jsonl`. The writer module
exposes **no** delete API; the file's append-only forensic
posture is a hard invariant.

If the operator determines that a diagnostic row must be
removed (e.g. it was written with a wrong synthetic field and
will confuse a future A18c projector), the only authorised path
is:

1. **Stop the dashboard service** so the bind mount is released:
   `docker compose -p trading-agent stop dashboard`.
2. **Inspect the existing file** and confirm the exact row to
   remove: `cat /root/trading-agent/generated_seed.jsonl`.
3. **Truncate** the file manually with a single redirect:
   `: > /root/trading-agent/generated_seed.jsonl` (or use any
   text editor to remove the single line).
4. **Append a human-readable audit-trail note** to the audit log
   marking the operator-paced rollback:
   ```bash
   ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   printf '%s\n' '{"attempt_kind":"operator_manual_truncation_note","stop_status":"none","generated_candidate_id":"<id>","operator_note":"manual truncation per a18b_writer_host_side_write_runbook §9","generated_at_utc":"'"$ts"'"}' \
      >> /root/trading-agent/logs/development_generated_lane_writer/audit.jsonl
   ```
   (The audit append above is a **plain text JSON line** the
   operator hand-writes; it is not produced by the writer module.
   The writer module's audit schema does not include an
   `operator_manual_truncation_note` `attempt_kind` — the manual
   note documents the rollback for forensic purposes but is
   intentionally outside the writer's closed-vocab list. A
   future A18c admission projector, if/when implemented, will
   ignore audit rows whose `attempt_kind` is not in the writer
   module's `AUDIT_ATTEMPT_KINDS` tuple.)
5. **Recreate the dashboard** so the bind mount resolves the
   truncated file:
   `docker compose -p trading-agent up -d --force-recreate dashboard`.
6. **Verify** convergence via §7.2 / §7.3 / §7.4. The host and
   container line counts should both be zero (or the post-removal
   row count); writer `record_count=0` (or the post-removal
   count); Step 5 / Level 6 invariants intact (Level 6 stays permanently disabled per ADR-015).

The runbook does **not** authorise any agent action under §9. A
truncation is an operator decision; the agent participates only
by documenting the procedure here.

---

## 10. Step 5 and Level 6 invariants

Level 6 is **permanently disabled** per ADR-015 §Doctrine 1 and
is **never** raised by this runbook. The six invariants below
are re-asserted on every line of this runbook:

```
step5_implementation_allowed = false
STEP5_ENABLED_SUBSTAGE        = "none"
level6_enabled                = false
dry_run_only                  = true
live_merge_implemented        = false
deploy_coupled                = false
```

The writer module emits these literal values into its
`_DISCIPLINE_INVARIANTS` dict on every envelope. This runbook
does not authorise the operator to flip any of them. Any future
change requires a separate operator-authored ADR and a separate
PR.

---

## 11. What this runbook does NOT do

* Does **not** authorise any agent code to perform a write. The
  write is a separate Phase-2-shaped operator-paced action.
* Does **not** modify the writer module, its constants, its
  schema, its env-gate, its sentinels, or its closed
  vocabularies.
* Does **not** modify `docker-compose.yml`,
  `docker-compose.override.yml`, or the established file-level
  bind mount. Any migration to a directory-level bind mount
  (Option β2 of the post-Phase-2 design notes) is a **separate**
  operator-paced action with its own scope proposal.
* Does **not** activate A18c. A18c remains plan-only, gated by
  the explicit operator-go phrase `GO A18c plan-only`.
* Does **not** plan, implement, or activate any Step 5 substage.
* Does **not** introduce N5b Phase 2 token-bound dry-run, Phase
  3 sacrificial-repo live merge, or Phase 4 production merge.
* Does **not** grant ADE permission to merge any PR, push to
  `main`, force-push, deploy, mint an approval token, verify an
  approval token, send a real push notification, or open / close
  / comment on any PR.
* Does **not** mark any roadmap status field complete or
  advance any phase counter.

---

## 12. Cross-references

* [`docs/governance/development_generated_lane.md`](development_generated_lane.md)
  — A18a / A18b governance and writer contract. Cross-references
  back to this runbook for the operational caveat.
* [`docs/governance/autonomous_development_baseline_observation.md`](autonomous_development_baseline_observation.md)
  — Phase 0 baseline observation chain; the rest state to which
  every A18b write must return.
* [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — N5b governance / plan-only doc; reasserts the live-merge
  invariants this runbook also preserves.
* [`docs/governance/n5b_merge_preflight_runbook.md`](n5b_merge_preflight_runbook.md)
  — sister runbook for the N5b Phase 1 dry-run preflight refresh
  chain.
* [`docs/governance/n4b_runtime_activation.md`](n4b_runtime_activation.md)
  — N4b Phase B runtime activation runbook (already complete).
* [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — authority doctrine.
* [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — Level 6 permanently-disabled doctrine.
* [`docs/governance/execution_authority.md`](execution_authority.md)
  — per-action authority decisions.
* [`docs/governance/no_touch_paths.md`](no_touch_paths.md) — the
  protected paths.
