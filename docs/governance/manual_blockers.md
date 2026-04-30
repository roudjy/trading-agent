# Manual Blockers

Items that **must** be performed by a human, outside Claude, before the
matching governance step is complete. Agents may suggest these actions but
must never attempt to execute them.

Each item has a status field that is updated by the human operator after
completion.

---

## Branch protection on `main`

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.2 |
| Status | **PENDING** — scheduled for the morning after this PR exists |
| Procedure | See [`branch_protection_checklist.md`](branch_protection_checklist.md) |

This cannot be configured from repo files. It is a GitHub UI / API operation.

---

## External credential rotation

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.0 |
| Status | **DEFERRED** — live trading disabled, Polymarket wallet has no funds |
| Re-evaluate | Before any live-trading step is enabled (v3.16+). |
| Procedure | See [`SECURITY.md`](../../SECURITY.md) §"Credential inventory & rotation order" |

Repository-side containment is in place: `config/config.yaml` is removed from
the Git index, `.gitignore` excludes it, `.dockerignore` excludes it from any
future Docker build. The leak is closed at the boundary that matters most for
agent-driven code changes.

---

## History rewrite (Git filter-repo)

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.0 |
| Status | **DEFERRED** — no current need; runbook documented |
| Procedure | See [`SECURITY.md`](../../SECURITY.md) §"History rewrite" |

This is a destructive operation. The hook layer will deny `git filter-*` and
`git push --force*` from any Claude session.

---

## VPS-side configuration update

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.0 |
| Status | **NOT REQUIRED** under current decision — VPS continues with existing keys until the rotation runbook fires |
| Procedure | When rotation occurs: copy the updated `config.yaml` to `/root/trading-agent/config/config.yaml` via the operator's own SSH session. **Never** via Claude — `ssh root@*` and `scp root@*` are denied at the hook layer. |

---

## GHCR image cleanup

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.0 |
| Status | **OPEN** — pre-v3.15.15.12 image tags considered suspect (no `.dockerignore` existed before this version) |
| Procedure | Manual GHCR step — delete or keep? Decision is at operator discretion. Do not delete tags referenced by `docs/governance/release_digests.md` until a digest-pinned rollback path exists for that release. |

---

## Pre-commit installation

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.1 |
| Status | **PENDING** after this PR exists |
| Procedure | `pip install pre-commit && pre-commit install` (locally only). The repo ships `.pre-commit-config.yaml` and `.secrets.baseline`. |

---

## SHA-pin monthly review

| Field | Value |
|---|---|
| Owner | Joery (initially); later optional recurring agent |
| Sub-item | v3.15.15.12.2 / .8 |
| Status | **OPEN** — first review after this PR is merged |
| Procedure | See [`sha_pin_review.md`](sha_pin_review.md) |

---

## Rollback drill

| Field | Value |
|---|---|
| Owner | Joery |
| Sub-item | v3.15.15.12.8 |
| Status | **PENDING** — first drill scheduled when window without open trades is available |
| Procedure | See [`rollback_drill.md`](rollback_drill.md). Uses image **digest**, never tag. |

---

This file is the single source for items that are not yet machine-enforceable.
Update the Status fields here as items close.
