# Release Gate — Deterministic Checklist

The release-gate-agent runs this checklist for every report. Each item
must be `pass` or explicitly justified as `n/a` with a reason.

> **No item may be silently skipped.** A missing line in the report is
> equivalent to `block`.

---

## Checklist

- [ ] **No unreviewed generated files.** No `dist/`, `build/`,
      `*.egg-info`, `__pycache__/`, or auto-regenerated snapshot files
      committed without an explicit reviewer comment in the PR.
- [ ] **No regenerated determinism pins.** `tests/regression/test_v3_*pin*.py`
      and friends are unchanged in the diff (or, if changed, an ADR
      amendment is linked in the same PR).
- [ ] **No snapshot churn.** Files matching `*_latest.v1.json` /
      `*_latest.v1.jsonl` are unchanged (or covered by ADR amendment).
- [ ] **No fixture rewrites.** Files under `tests/**/fixtures/**` and
      `tests/**/golden/**` are unchanged (or explicitly justified).
- [ ] **No nondeterministic timestamps in committed artifacts.** A
      regex sweep (`\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}`) on the
      diff finds no matches inside committed JSON / JSONL artifacts —
      ledger events are the exception (those carry intentional
      timestamps).
- [ ] **Active nightly failures referenced.** Either the report cites
      every open nightly-failure issue with a link, or `none active`
      is asserted with a link to the most recent green nightly run.
- [ ] **Build provenance attached.** For PRs that produce a Docker
      image: the `build_provenance-<version>.json` artifact exists,
      its `image_digest` matches the PR's image digest, and
      `actions_pinned` is `true`. For non-image PRs: `n/a`.
- [ ] **Audit chain intact.** `python -m reporting.agent_audit verify
      <today's ledger>` returns OK. For `block`: cite the first corrupt
      index.
- [ ] **No new live/broker connector files.** No new file in the diff
      matches `execution/live/**`, `automation/live/**`,
      `agent/execution/live/**`, `**/live_*broker*.py`,
      `**/*live_executor*.py`, or `**/*_live.py`. (The
      `deny_live_connector` hook should have already prevented this;
      this checklist item is a belt-and-suspenders verification.)
- [ ] **`VERSION` bump justified.** If `VERSION` is changed in this
      PR, this report explicitly recommends the bump and cites the
      release rationale. Otherwise `n/a`.
- [ ] **Agent run summary committed.** A file at
      `docs/governance/agent_run_summaries/<session_id>.md` exists,
      is non-empty, and is referenced from the PR body.
- [ ] **CODEOWNERS review present.** Branch-protection enforces this
      for merge; the report cross-checks at PR-gate so the operator is
      not surprised.

## Per-gate verdict matrix

For each gate (`commit`, `PR`, `merge`, `deploy`), the agent records:

| Gate | Decision | Required-yes items | Authority |
|---|---|---|---|
| `commit` | recommend yes / no | Items 1–9 above | local; operator |
| `PR` | recommend yes / no | Items 1–11 + CI fast-gate green | local; operator |
| `merge` | recommend yes / no | All items + CODEOWNERS review present | **humans-only** |
| `deploy` | recommend yes / no | All items + recent rollback drill log + digest in `release_digests.md` | **humans-only** |

## What `block` means

A `block` recommendation on any gate halts the chain. The operator may
override with explicit knowledge — branch protection still requires
CODEOWNERS review and the override is auditable from the PR body.

## What `revise` means

Some items are revisable in the same PR (e.g. `agent run summary
missing` → write the summary file). Others require a new PR (e.g.
`pin re-pinned without ADR` → create the ADR amendment first). The
report distinguishes them.
