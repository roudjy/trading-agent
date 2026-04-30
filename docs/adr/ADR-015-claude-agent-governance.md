# ADR-015 — Claude Agent Governance Model

## Status

Accepted 2026-04-30. Implemented in branch
`feat/v3.15.15.12-agent-governance`. Sits beside ADR-014 (truth-authority
settlement) as the second pillar of the project's authority chain.

## Context

The trading-agent codebase is a deterministic Quant Research Engine: ~54k
LOC of Python, 263 test files, frozen v1 schemas, append-only evidence
ledgers, byte-stable replay invariants, and a single live-trading barrier
(`automation/live_gate.py`). ADR-014 settled **what is canonical** across
registry / presets / hypothesis catalog / candidate lifecycle / evidence
ledger / paper-readiness / live governance.

ADR-014 left a structural gap: it does not say **who is allowed to change
canonical things, and how**. Without that, autonomous Claude agents would
be free — by accident — to drift the very invariants ADR-014 settles.

ADR-015 closes that gap. It defines a layered authority chain that bounds
what an agent may do, with enforcement at every layer (policy, hooks,
CODEOWNERS, branch protection), so that the *worst* an agent can do is
fail-closed.

## Decision

The Claude Agent Governance & Safety Layer (v3.15.15.12) consists of the
following doctrines. Each doctrine is enforced by at least one
machine-readable mechanism and at least one reviewer convention.

### Doctrine 1 — Autonomy ladder (Levels 0–6)

| Level | Capability | Status in this project |
|---|---|---|
| 0 | Plan / read only | always available |
| 1 | Docs + tests + frontend writes | available after .3 active |
| 2 | Observability + CI writes (per-change approval) | available after .4 |
| 3 | Backend non-core writes (allowlist-only) | not enabled in this version |
| 4 | Merge recommendation | requires ≥30 days L1–3 stable + amendment of this ADR |
| 5 | Deploy recommendation | requires ≥60 days L1–4 stable + amendment of this ADR |
| 6 | Autonomous merge / deploy | **permanently disabled** in this project |

Level 6 is not a level we ever reach. An amendment that proposes to enable
Level 6 will be auto-recommended `block` by the release-gate-agent's
checklist and must therefore be merged by humans deliberately overriding
that recommendation, in full knowledge that they are doing so.

### Doctrine 2 — No-touch path doctrine

A canonical, machine-readable list of paths agents may not write to lives
in two places, kept in sync by tests:

- `docs/governance/no_touch_paths.md` — human-readable.
- `.claude/hooks/deny_no_touch.py:NO_TOUCH_GLOBS` — enforced.

The list covers: live trading code, secrets, the authority surface from
ADR-014, orchestration core, backtest core, production posture files,
frozen v1 schemas, existing ADRs, determinism pin tests, the governance
layer's own files (`.claude/settings.json`, `.claude/hooks/**`,
`.claude/agents/**`, `.github/CODEOWNERS`), `VERSION`, and the governance
core docs themselves.

`config/config.yaml`, `state/*.secret`, `automation/*.secret`, `.env`, and
`.env.*` are additionally **read-deny**.

### Doctrine 3 — Live-connector create-deny

`.claude/hooks/deny_live_connector.py` blocks the *creation* of new files
that match live-connector path globs (`execution/live/**`,
`automation/live/**`, `agent/execution/live/**`, `**/live_*broker*.py`,
`**/*live_executor*.py`, `**/*_live.py`) or whose Python content imports
the Ethereum-account signing surface, calls a raw transaction sender,
instantiates the Polymarket clob client with a private key, or calls a
CCXT exchange's `create_order` without a paper-mode flag.

Live connectors are introduced through human-authored,
CODEOWNERS-reviewed `governance-bootstrap` PRs. Never autonomously.

### Doctrine 4 — Release-gate doctrine

The release-gate-agent produces an immutable per-timestamp file at
`docs/governance/release_gates/<version>/<UTC-timestamp>.md` for each
release-stage transition. The report cites:

- per-gate verdict (commit / PR / merge / deploy);
- evidence per gate (CI run ids, audit-ledger event ids, build provenance);
- a deterministic checklist (no unreviewed generated files; no regenerated
  pins; no snapshot churn; no fixture rewrites; no nondeterministic
  timestamps; active nightly failures referenced or none; build provenance
  attached; audit chain `verify_chain()` pass; no new live-connector files;
  `VERSION` bump only with explicit recommendation).

Release-gate reports are append-only by file — never edited.

### Doctrine 5 — Audit-chain doctrine

Every agent action emits an event to a hash-chained, append-only,
daily-rotated JSONL ledger at `logs/agent_audit.<UTC date>.jsonl`. Each
event carries `prev_event_sha256` and `event_sha256`; tampering produces
a chain break that `verify_chain()` reports with the first corrupt index.

The ledger is gitignored. The committed bridge to Git history is
`docs/governance/agent_run_summaries/<session_id>.md` (redacted; paths,
counts, decisions, ledger event id ranges only).

Schema is v1 and additive only — fields may be added; never removed or
renamed without an ADR amendment.

### Doctrine 6 — Provenance doctrine

For every Docker image pushed by `.github/workflows/docker-build.yml`,
a `build_provenance-<version>.json` artifact is emitted (schema in
`artifacts/build_provenance.schema.json`, committed to Git). The artifact
ties commit SHA, image digest, workflow run id, version, actor, and the
`actions_pinned` flag together. Verification runbook is in
`docs/governance/provenance.md`.

Image rollback is performed by digest (`@sha256:...`), never by tag, per
`docs/governance/rollback_drill.md`.

### Doctrine 7 — Self-protected layer

`.claude/settings.json`, `.claude/hooks/**`, `.claude/agents/**`, and
`.github/CODEOWNERS` are on the no-touch list. The hook layer cannot be
loosened by an agent at runtime. There is no environment variable, no
command-line flag, no session toggle that converts a hook deny into a
warn (Doctrine 12 below).

Modifications to these files happen exclusively via human-authored,
CODEOWNERS-reviewed `governance-bootstrap` PRs.

### Doctrine 8 — Human authority settlement

Humans alone hold:

- `git push` to `main` (mediated by branch protection);
- merge of any PR (mediated by CODEOWNERS + branch protection);
- deploy of any image (manual `scripts/deploy.sh` from the operator's own
  shell; agents are denied via `deny_dangerous_bash.py`);
- `VERSION` bumps;
- amendments to this ADR.

Agents may **recommend** any of the above; they may not perform any of
them.

### Doctrine 9 — Test-integrity doctrine

No agent may introduce `pytest.mark.skip`, `pytest.mark.xfail`,
`pytest.skip(...)`, `pytest.xfail(...)`, or `pytest.importorskip(...)`
inside `tests/`. No agent may relax an assertion to make a previously
failing test pass. No agent may regenerate a fixture, golden file, or
determinism digest.

The `deny_test_weakening.py` hook enforces the marker patterns; reviewer
discipline enforces the rest. Pin failures are reported by the
`determinism-guardian` agent and resolved by humans via ADR amendment +
new pin in a CODEOWNERS-reviewed PR.

### Doctrine 10 — Hook fail-closed + timeout doctrine

Every PreToolUse-style deny hook is fail-closed: any exception, timeout,
parse failure, or missing dependency results in DENY plus a best-effort
audit event with a `block_reason` of the form
`hook_runtime_<class>` or `hook_timeout`.

Per-event budgets (enforced via `signal.alarm` on POSIX,
join-with-timeout thread on Windows):

| Phase | Budget | Failure mode |
|---|---|---|
| `PreToolUse` | 2 s | DENY |
| `PostToolUse` | 2 s | best-effort warn |
| `Stop` | 5 s | best-effort warn |
| `PreCompact` | 5 s | best-effort warn |
| `audit_emit` (any phase) | 1 s | warn + over-budget event |

`audit_emit` is the only hook that does not block on failure (the
observed action has already completed).

### Doctrine 11 — `VERSION` doctrine

`VERSION` is on the no-touch list. Bumps require:

1. A release-gate report recommending the bump.
2. A human-authored PR that touches `VERSION` plus `CHANGELOG.md`.
3. CODEOWNERS review.

Agents may write the recommendation into the release-gate report; they
may not edit `VERSION` directly.

### Doctrine 12 — Hook dry-run-mode-only-pre-`.3` doctrine

Hook dry-run mode (where a deny becomes a warn) was permitted only
during the bootstrap of v3.15.15.12.3. Once the hooks are seeded and
committed, dry-run mode is **never** permitted — there is no
environment variable, command-line flag, or session toggle that
re-enables it.

Anyone who introduces such a toggle in a future PR is in violation of
this ADR. The release-gate-agent's checklist will catch it.

### Doctrine 13 — Run-summary doctrine

Every Claude session that produces a PR commits a redacted run summary
at `docs/governance/agent_run_summaries/<session_id>.md`. The PR
template requires a link to this file. The summary is the bridge
between the gitignored runtime ledger and the Git history a human
reviewer can read.

The summary contains paths, counts, ledger event id ranges, test
results, and gate decisions. It contains **no file contents, no
secrets, no full diffs**.

## Consequences

### Positive

- Agent autonomy is bounded. The worst-case action is a fail-closed
  block plus an audit event.
- Auditability is end-to-end — runtime ledger, run-summary bridge,
  release-gate report.
- Rollbacks are reproducible by digest.
- Determinism doctrine becomes machine-checked (drift hard-blocks
  merge).

### Negative

- Friction in the development loop. Every governance change requires a
  CODEOWNERS-reviewed PR.
- More review overhead per PR. The PR template is longer.
- No Level 6 ever — even when stability would seem to justify it. This
  is a deliberate choice to keep humans in the merge/deploy loop
  indefinitely, given the live-trading risk profile.

### Neutral

- The governance layer becomes part of the architecture authority chain
  alongside ADR-014. Future ADRs that touch governance must reconcile
  with this one.

## Alternatives considered

1. **Pure-policy** (relying on agent etiquette only). Rejected during
   Revision 1 of the implementation plan: agents drift unless
   machine-enforced.
2. **Machine-enforced-only** (no human review on top). Rejected as too
   rigid for research velocity; reviewer judgment is still load-bearing.
3. The chosen **hybrid** — machine-enforced floors with reviewer
   judgment on top — is what this ADR codifies.

## Authority chain placement

```
ADR-014 (settles WHAT is canonical)
   |
   v
ADR-015 (settles WHO may change WHAT, and HOW)
   |
   v
Hooks + CODEOWNERS + Branch Protection (mechanical enforcement)
   |
   v
Reviewer discipline (filling the unmachineable gaps)
```

## Forward-looking amend triggers

| Trigger | Effect |
|---|---|
| ≥30 days at Level 1–3 with no governance regression | enables Level 4 unlock proposal (still requires ADR amendment) |
| ≥60 days at Level 1–4 with no governance regression | enables Level 5 unlock proposal |
| **Any time** | Level 6 stays disabled. An amendment proposing Level 6 must explicitly justify why this project should accept the open-loop risk profile. |

## References

- ADR-009 — Platform-layer introduction (orchestrator owns dispatch).
- ADR-013 — v3.15.3 hypothesis catalog.
- ADR-014 — Truth-authority settlement.
- `docs/governance/no_touch_paths.md`
- `docs/governance/permission_model.md`
- `docs/governance/autonomy_ladder.md`
- `docs/governance/release_gate.md`
- `docs/governance/audit_chain.md`
- `docs/governance/provenance.md`
- `docs/governance/no_test_weakening.md`
- `docs/governance/hooks_runtime_policy.md`
- `docs/governance/rollback_drill.md`
- `SECURITY.md`
