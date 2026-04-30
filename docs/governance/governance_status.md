# Governance Status — Read-only Diagnostic

`reporting.governance_status` is a read-only diagnostic surface for the
v3.15.15.12 Claude Agent Governance & Safety Layer. It reports — never
decides, never mutates — whether the policy / hook / agent layer is
present, what the audit ledger for today looks like, and what version
and branch are checked out.

It is the first observability artefact added on top of the governance
layer (introduced in v3.15.15.13). It exists so that operators and CI
can see the state of the layer without having to read each artefact by
hand.

## What it reports

`python -m reporting.governance_status` prints a JSON snapshot with
these top-level fields:

| Field | Meaning |
|---|---|
| `schema_version` | Snapshot schema version. Currently `1`. Additive only — fields may be added; never removed or renamed without an ADR amendment. |
| `report_kind` | Always `"governance_status"`. Identifies the artefact for downstream parsers. |
| `last_evaluation_at_utc` | ISO-8601 UTC timestamp of when the snapshot was produced. The only intentionally non-deterministic field. |
| `version.file_version` | Contents of `VERSION` (or `null` if missing). |
| `git.branch`, `git.head_sha`, `git.on_main_branch` | From `git rev-parse`. `on_main_branch` is `"unknown"` when git is unavailable. |
| `policy.settings_present` | Whether `.claude/settings.json` exists. The hook layer is keyed off this file; absent ⇒ no hook policy is loaded. |
| `policy.agents_present` | Whether `.claude/agents/` exists with at least one agent definition. |
| `hooks.layer_state` | One of `installed`, `degraded`, `not_available`. Never `ok`. |
| `hooks.inventory` | Per-hook `present` / `missing` map across the expected set. |
| `autonomy.max_available_level` | Highest level marked operationally available in `docs/governance/autonomy_ladder.md`, or `"unknown"` if the doc cannot be parsed. |
| `autonomy.available_levels` | Sorted list of levels currently available, or `"unknown"`. |
| `autonomy.level_6_status` | Hard-coded `"permanently_disabled"` per ADR-015 §Doctrine 1. `"unknown"` only if the ladder doc is missing or unparseable. |
| `audit_ledger_today.status` | One of `intact`, `broken`, `unreadable`, `not_available`. Never `ok`. |
| `audit_ledger_today.first_corrupt_index` | Index of the first event that fails `verify_chain()`, or `null` if intact / not available. |
| `audit_ledger_today.{event,allowed,blocked,other}_count` | Per-outcome counts for today's UTC ledger. |
| `audit_ledger_today.last_event` | Redacted tail: `sequence_id`, `timestamp_utc`, `outcome`, `tool`, `block_reason`, `branch`, `head_sha`. **Never** carries `command_summary`, `diff_summary`, or `target_path`. |
| `autonomous_mode.status` | Always `"not_machine_enforceable"`. Whether a session is operating autonomously is a per-event runtime claim recorded in the ledger's `autonomy_level_claimed` field, not a global state. |

## What it does *not* mean

* It does **not** prove the hook layer is active. It only reports
  whether the hook *files* exist. A misconfigured `.claude/settings.json`
  could prevent the hooks from being invoked even when every file is
  present. The release-gate-agent and the `governance-lint` CI job are
  the actual checks.
* `audit_ledger_today.status == "intact"` does **not** mean previous
  days are intact. The hash chain restarts daily; older files are
  verified separately by `python -m reporting.agent_audit verify
  logs/agent_audit.<date>.jsonl`.
* `git.on_main_branch == false` does **not** mean main-branch
  protection is configured. Branch protection lives in the GitHub UI
  (see `docs/governance/branch_protection_checklist.md`); this report
  only mirrors the local working-copy branch.
* `autonomy.max_available_level == 2` does **not** authorise an agent
  to act at Level 2. Per-agent caps in `.claude/agents/*.md`
  frontmatter and reviewer discipline still apply.
* `autonomous_mode.status == "not_machine_enforceable"` does **not**
  mean autonomous execution is disabled — only that *whether* a given
  session was autonomous is a runtime claim, not a global flag.

## When operator approval is still required

Producing this snapshot does not loosen any governance constraint.
Every action that required operator approval before this diagnostic
was added still requires it:

1. Any change to `.claude/hooks/**`, `.claude/agents/**`,
   `.claude/settings.json`, `.github/CODEOWNERS`, or `VERSION` — only
   via human-authored, CODEOWNERS-reviewed `governance-bootstrap` PRs.
2. Any change to a no-touch path (see
   [`no_touch_paths.md`](no_touch_paths.md)).
3. Any merge to `main` — humans only, mediated by branch protection.
4. Any deploy of an image — humans only, by digest.
5. Any unlock of Level 4 or Level 5 — ADR amendment plus the stability
   window in ADR-015.
6. Level 6 — permanently disabled.

## Failure modes

The CLI exits 0 even when the snapshot reports degraded state. This
is intentional: a diagnostic that gates CI by its own findings is no
longer a diagnostic, it is policy. Reading the snapshot and deciding
what to do is the operator's responsibility.

If `reporting.governance_status` itself raises (for example because a
sensitive-path fragment somehow appeared in the snapshot), the
`assert_no_secrets()` self-check raises an `AssertionError` and the
CLI exits non-zero. That is a *bug*, not a governance state — file an
issue and use the previous snapshot until it is fixed.

## Where it fits

* **ADR-015 §Doctrine 5 — Audit-chain doctrine**: this report
  surfaces a daily summary of the chain. It does not replace
  `verify_chain()`.
* **Doctrine 7 — Self-protected layer**: the diagnostic deliberately
  reports presence rather than content of `.claude/settings.json` and
  `.claude/hooks/**`, so that exposing the snapshot does not create a
  side channel into protected files.
* **Doctrine 13 — Run-summary doctrine**: per-session run summaries
  remain the canonical bridge between the runtime ledger and Git
  history. This snapshot is operator-facing, not session-facing, and
  is not committed.
