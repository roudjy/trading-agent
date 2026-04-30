# Pull Request

## Summary

<!-- 1–3 bullet points on what changed and why. Avoid file-by-file recap. -->

-
-

## Linked roadmap item / ADR

<!-- e.g. v3.15.15.12.5 / ADR-015 §audit-chain -->

## Autonomy claim

> The PR author claims this PR was produced at autonomy level: **Level _**
> (0 = planning only, 1 = docs/tests/frontend, 2 = observability/CI,
> 3 = backend non-core. Level 4+ is not enabled in this project.)
> See [`docs/governance/autonomy_ladder.md`](../docs/governance/autonomy_ladder.md).

## Governance checklist

A PR cannot be merged until every applicable item is checked or marked N/A.

- [ ] No no-touch path was modified, **or** a new ADR is linked above.
- [ ] Determinism-pin job is green; no pin re-pinned.
- [ ] Authority surfaces unchanged (ADR-014).
- [ ] Evidence ledger schemas unchanged or extended-only (no field removals/renames).
- [ ] No tests skipped, marked `xfail`, or assertion-relaxed; no fixtures
      regenerated; no digest pins updated.
- [ ] No new live/broker connector files created.
- [ ] `VERSION` is unchanged in this PR, **or** the bump is explicitly recommended
      by a Release Gate report linked below.
- [ ] Build provenance attached as a workflow artifact, **or** N/A (non-image PR).
- [ ] Active nightly failures referenced in PR body, **or** none active.
- [ ] Agent run summary committed, **or** N/A (no agent involvement):
      `docs/governance/agent_run_summaries/<session_id>.md`
- [ ] Release Gate report (if applicable):
      `docs/governance/release_gates/<version>/<timestamp>.md`

## Test plan

<!-- What was actually run? Paste pytest summary lines, vitest summary, ruff/mypy
output. If a test was added, name it here. -->

-
-

## Risks & rollback

<!-- One sentence per item. -->

- Risk:
- Rollback:

---

> Anything that touches `automation/live_gate.py`, `config/config.yaml`,
> `state/*.secret`, frozen v1 schemas, or production posture files
> (`docker-compose.prod.yml`, `scripts/deploy.sh`, `ops/systemd/*`) requires
> CODEOWNERS review and a linked ADR amendment. See
> [`docs/governance/no_touch_paths.md`](../docs/governance/no_touch_paths.md).
