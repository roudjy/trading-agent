# Build Provenance — Verification Runbook

For every Docker image pushed to GHCR by
[`.github/workflows/docker-build.yml`](../../.github/workflows/docker-build.yml),
a `build_provenance-<version>.json` artifact is emitted (and uploaded to
the workflow run with 365-day retention). The schema is
[`artifacts/build_provenance.schema.json`](../../artifacts/build_provenance.schema.json).

The provenance lets us answer two questions deterministically:

1. **Which commit is in this running image?**
2. **Was the build performed under SHA-pinned actions?**

---

## Schema (recap)

```json
{
  "schema_version": 1,
  "commit": "<40-char Git sha>",
  "image_digest": "sha256:<64-hex>",
  "image_digest_dashboard": "sha256:<64-hex>",
  "workflow_run_id": "<id>",
  "workflow_run_attempt": 1,
  "version": "<contents of VERSION>",
  "built_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "actor": "<gh handle>",
  "actions_pinned": true
}
```

## Where the values come from

- `commit` — `${{ github.sha }}` at build time.
- `image_digest` — output of `docker/build-push-action` (`needs.build-and-push.outputs.digest_agent`).
- `image_digest_dashboard` — same, for the dashboard image.
- `workflow_run_id`, `workflow_run_attempt` — `${{ github.run_id }}`, `${{ github.run_attempt }}`.
- `version` — `cat VERSION`.
- `built_at_utc` — wall-clock at the moment the emitter runs.
- `actor` — `${{ github.actor }}`.
- `actions_pinned` — true while `tests.yml`, `nightly.yml`, `docker-build.yml`
  reference all third-party actions by 40-char commit SHA. Verify via
  monthly SHA-pin review.

## Verifying that an image matches a commit

```sh
# 1. Download the provenance artifact for the version.
gh run download <run_id> --name build-provenance-<version>

# 2. Inspect the digest.
jq -r '.image_digest' build_provenance-<version>.json

# 3. Resolve the same digest from GHCR.
docker pull ghcr.io/roudjy/trading-agent-agent:<version>
docker inspect --format='{{ index .RepoDigests 0 }}' \
  ghcr.io/roudjy/trading-agent-agent:<version>

# The two digests must be byte-equal.
```

## Verifying a running container

On the VPS:

```sh
docker inspect --format='{{ index .Image }}' jvr_trading_agent
# -> sha256:<digest>
```

Compare to `image_digest` from the saved provenance file. If they
differ, the running container is not the version the provenance
asserts.

## When provenance must accompany a PR

The PR template requires:

> [ ] Build provenance attached as a workflow artifact, **or** N/A
> (non-image PR).

For PRs that produce an image (i.e. trigger `docker-build.yml`),
the release-gate report cites the provenance artifact run id.

## Rollback by digest, never by tag

See [`rollback_drill.md`](rollback_drill.md). Rollback uses
`ghcr.io/...@sha256:<rollback_digest>`, never a tag, because tags are
mutable.

## Future work

- GHCR-attached attestation via `actions/attest-build-provenance` —
  decision deferred (backlog item AB-0002). Current setup uses the
  artifact-only path.
- Cross-image attestation (e.g. cosign) — out of scope for
  v3.15.15.12.
