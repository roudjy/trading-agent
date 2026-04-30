# Release Digests

Append-only registry of (version → image digest) pairs and the
matching `rollback_digest` (the previous successful release's digest
for the same image, used by the digest-based rollback drill).

> **Append-only.** Existing rows are never edited. A correction goes
> in as a new row with a `note` referencing the row it supersedes.

---

## Format

```
| version | image | image_digest | rollback_digest | built_at_utc | provenance_artifact_run_id | note |
```

- `version` — contents of the `VERSION` file at build time.
- `image` — `agent` or `dashboard`.
- `image_digest` — the `@sha256:...` of this version's image.
- `rollback_digest` — the prior successful build for the same `image`
  in the same lineage. Empty for the very first row.
- `built_at_utc` — from the build provenance JSON.
- `provenance_artifact_run_id` — GitHub Actions run id for retrieving
  the provenance JSON.
- `note` — optional, e.g. `supersedes row X` or `manual entry`.

---

## Log

| version | image | image_digest | rollback_digest | built_at_utc | provenance_artifact_run_id | note |
|---|---|---|---|---|---|---|
| (no rows yet — populated by the first docker-build run after this PR) | | | | | | |

---

## Rules

1. The release-gate-agent appends rows after a successful build; humans
   may also append manually for backfilled releases.
2. A row added here is the source of truth for `rollback_drill.md`.
3. Never reference an image by tag here. Digests only.
