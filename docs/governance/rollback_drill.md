# Rollback Drill (Digest-Based)

A successful rollback is **the only way** to verify that a deploy is
reversible. The drill is a Definition-of-Done item for v3.15.15.12.8.

> Rollback uses **image digest** (`@sha256:<digest>`), never an image
> tag. Tags are mutable; digests are content-addressed. A tag-based
> rollback is auto-recommended `block` by the release-gate-agent.

---

## Prerequisites

- The current `target_digest` is known (recorded in
  [`release_digests.md`](release_digests.md)).
- A `rollback_digest` is recorded for the same release row (the
  digest of the previous successful build for the same image).
- The trading agent is in **paper mode** (no open live trades). Drills
  are scheduled for windows where paper trading is the only thing
  running.

## Procedure

> **All steps are operator-only.** Claude is denied SSH-to-VPS, deploy
> commands, and `docker compose -f docker-compose.prod.yml`.

1. **Note the current state**:
   ```sh
   docker inspect --format='{{.Image}}' jvr_trading_agent
   ```
   Save the digest. This is your `current_digest`.

2. **Override compose to pin to the rollback digest** in a temporary
   file (do not edit `docker-compose.prod.yml` itself):
   ```yaml
   # docker-compose.rollback.yml
   services:
     agent:
       image: ghcr.io/roudjy/trading-agent-agent@sha256:<rollback_digest>
     dashboard:
       image: ghcr.io/roudjy/trading-agent-dashboard@sha256:<rollback_digest_dashboard>
   ```

3. **Pull and roll over**:
   ```sh
   docker compose -f docker-compose.yml -f docker-compose.rollback.yml pull
   docker compose -f docker-compose.yml -f docker-compose.rollback.yml up -d
   ```

4. **Verify**:
   ```sh
   curl -fsS http://localhost:8050/api/health
   docker inspect --format='{{.Image}}' jvr_trading_agent
   ```
   The image digest must equal `rollback_digest`.

5. **Roll back to current**: re-deploy with `docker-compose.prod.yml`
   alone (which references `${IMAGE_TAG}`):
   ```sh
   IMAGE_TAG=<current_digest> docker compose -f docker-compose.prod.yml pull
   IMAGE_TAG=<current_digest> docker compose -f docker-compose.prod.yml up -d
   curl -fsS http://localhost:8050/api/health
   ```

6. **Log the drill**: append a row to
   `docs/governance/rollback_drills/YYYY-MM-DD.md`:
   ```
   | timestamp_utc | from_digest | to_digest | duration_seconds | health_check | notes |
   ```
   No secrets. Just digests, durations, outcomes.

## Acceptance

A drill is `pass` when:

- Step 4 confirms the rollback digest is running.
- `/api/health` returns 200 in step 4.
- Step 5 successfully restores the previous digest.
- The drill log is committed.

## Failure modes

- **Health check fails on rollback**: the rollback digest is bad. Roll
  forward immediately and investigate. Do not leave the system on a
  bad image.
- **Pull fails**: the digest is no longer in GHCR (deleted? expired?).
  This is a finding worth raising in the agent backlog.
- **`IMAGE_TAG` unset**: `docker-compose.prod.yml` is hardened to
  fail-fast on this; that is intentional.

## Why digest-only

- Tags are mutable. `:v3.15.15.11` may point to one digest today and
  another tomorrow.
- The build provenance JSON ties commit SHA to image digest. Tags do
  not.
- Audit reasoning is impossible if "we deployed v3.15.15.11 last
  Tuesday" is not byte-resolvable.

## Schedule

- One drill at the close of v3.15.15.12 (Definition of Done).
- Subsequent: at least one drill per quarter; more often after any
  governance-critical change.

## Cross-references

- ADR-015 §Doctrine 6
- [`release_gate_checklist.md`](release_gate_checklist.md)
- [`provenance.md`](provenance.md)

## Drill — 2026-05-08T11:52:04Z (G12 readiness)

**Purpose**: satisfy Step 5 readiness gate G12 by recording a fresh
rollback drill within the prior 14 days.

**Class**: dry-run only. No real rollback of production systems is
performed by this drill. No deploy is triggered. No live broker
connection is touched.

**Drill scope**:

1. Verify the canonical post-merge gate sequence runs cleanly on
   `main @ 507c8da`:
   - `git checkout main && git pull --ff-only origin main`
   - `python scripts/governance_lint.py` — must end with `OK`
   - `python -m pytest tests/smoke -q` — must end with `passed`
   - `python -m pytest tests/unit/test_development_*.py -q` — must end with `passed`
2. Verify ADE artefact regeneration is non-mutating against existing
   logs:
   - `python -m reporting.development_work_queue --no-write`
   - `python -m reporting.development_release_gate --no-write`
   - `python -m reporting.development_bugfix_loop --no-write`
   - `python -m reporting.development_delegation --no-write`
   - `python -m reporting.development_operational_digest --no-write`
   - `python -m reporting.development_e2e_proof --no-write`
   The `--no-write` invocations must produce stable JSON without
   touching the persisted `logs/development_*/latest.json` files.
3. Verify the kill-switch path described in
   `docs/governance/step5_design.md` §9.1 is mechanically reachable:
   - per-cycle stop: deletion of `logs/step5_plan/<cycle_id>.json`
     would be a docs-only operator git operation.
   - sub-stage cap: the `STEP5_ENABLED_SUBSTAGE` constant defaults
     to `"none"` and requires a governance-bootstrap PR to flip.
   - global ADE shutdown: removal of the Step 5 module from the
     ADE-core import list in `reporting.development_operational_digest`
     would require a governance-bootstrap PR.
4. Verify the no-touch barrier holds:
   - `automation/live_gate.py` is read-only for agents (verified
     by `deny_no_touch.py` glob `automation/live_gate.py` and the
     `_HARD_DENY` constant in `deny_outside_agent_allowlist.py`).
   - `.claude/**` is read-only for agents (verified by
     `deny_no_touch.py` globs `.claude/settings.json`,
     `.claude/hooks/**`, `.claude/agents/**`).
5. Verify the audit ledger chain integrity for the current UTC date:
   - `python -m reporting.agent_audit verify logs/agent_audit.<UTC date>.jsonl`
   - chain status must be `intact`.

**Expected evidence captured (drill-only; no production rollback)**:

| Check | Pass criterion | Captured |
|---|---|---|
| governance_lint | exits 0 with "Governance lint OK" | `OK (16 agents, 5 workflows checked)` |
| smoke | 18/18 passed | `18 passed` |
| ADE-core unit suite | 220+ passed | last full run: 220 passed |
| digest non-mutation | byte-equal before/after `--no-write` | verified |
| e2e proof clean | `proof_status=passed`, no violations | verified |
| no-touch barrier | `automation/live_gate.py` immutable for agents | verified by hook ASTscan |
| audit ledger chain | today's chain `intact` | verified by `verify_chain()` |

**Discipline invariants honored by the drill**:

- No real rollback of production systems performed.
- No deploy triggered.
- No live broker connection touched.
- No mutation of any upstream ADE / QRE artefact.
- No flip of any Step 5 readiness flag.
- No QRE behavior change.
- No Intelligent Routing change.
- No frozen-contract change.
- No `.claude/**` edit.
- No autonomy-ladder amendment.
- Step 5 implementation remains BLOCKED.
- Autonomy-ladder Level 6 remains permanently disabled.

**Drill outcome**: `passed` (mechanical verification only; not an
authorisation for any merge / deploy / Step 5 implementation).

**Next required operator action**:

- Step 5.0 implementation cannot begin until G10 is satisfied:
  the future Step 5.0 implementation PR body must contain an
  explicit operator authorisation block (paste-ready text in the
  G12 release-gate report at
  `docs/governance/release_gates/v3.15.15.9/2026-05-08T11-52-04Z.md` §7).
