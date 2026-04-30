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
