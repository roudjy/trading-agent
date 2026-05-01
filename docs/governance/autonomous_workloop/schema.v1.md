# Autonomous Workloop digest — schema v1

The autonomous workloop controller (`reporting.autonomous_workloop`,
introduced in v3.15.15.16) emits two paired digests per run:

* **Markdown digest** (committed):
  `docs/governance/autonomous_workloop/{latest.md, <UTC>.md}`
* **JSON digest** (gitignored, runtime-only):
  `logs/autonomous_workloop/{latest.json, <UTC>.json}`

> **Path note**: The JSON digest lives under `logs/` (already
> gitignored) rather than the originally-proposed
> `artifacts/autonomous_workloop/`. This keeps `.gitignore`
> untouched in v3.15.15.16 (`.gitignore` is on the project's `ask`
> path); the schema below is identical regardless of the host
> directory. v3.15.15.17 backend endpoints read from the runtime
> filesystem path; if the file is missing, the backend responds
> `{"available": false, "status": "not_available"}` — never
> `"ok"`.

## Top-level keys (every key required; `unknown` allowed but never omitted)

| key | type | meaning |
|---|---|---|
| `schema_version` | int | Always `1`. Additive only — fields may be added; never removed or renamed without an ADR. |
| `report_kind` | string | Always `"autonomous_workloop_digest"`. |
| `controller_version` | string | E.g. `"v3.15.15.16"`. |
| `generated_at_utc` | string | ISO-8601 `Z`. |
| `mode` | enum | `"plan"` \| `"dry-run"` \| `"execute-safe"` \| `"continuous"` \| `"digest"`. |
| `cycle_id` | int | 0 by default; increments per cycle in continuous mode. |
| `current_branch` | string | From `git rev-parse --abbrev-ref HEAD`. |
| `git_state` | object | `{branch, head_sha, is_clean, dirty_paths_count}`. |
| `governance_status` | object | `{lint_passed: bool, summary: string}`. |
| `audit_chain_status` | object | `{ledger_path, status, first_corrupt_index}`. `status` is one of `intact`/`broken`/`unreadable`/`not_available`. Never `ok`. |
| `frozen_contracts` | object | Map `relative_path` → `{exists, sha256}`. |
| `pr_queue` | array | Per-PR rows; see "queue item" below. |
| `dependabot_queue` | array | Per-Dependabot rows. |
| `roadmap_queue` | array | Per-source recommendation rows. |
| `actions_taken` | array | `[]` in `plan` / `dry-run`. In `execute-safe` / `continuous`, contains `{kind, target, outcome}`. |
| `merges_performed` | int | **Always `0` in v3.15.15.16.** |
| `blocked_items` | array | Subset of pr_queue + dependabot_queue with `risk_class` starting `blocked_`. |
| `needs_human` | array | Subset of all queues with decision in `{needs_human, operator_click, recommendation_only}`. |
| `next_recommended_item` | string | `item_id` of the first non-blocked PR or `"unknown"`. |
| `frontend_control_state` | object | Forward-compat anchor for v3.15.15.17. See "frontend_control_state" below. |
| `limitations` | array | The 10 final-report statements (see `agent_audit_inspection.md` and ADR-015). |

## Queue item shape (per row in pr_queue / dependabot_queue / roadmap_queue)

| key | type | meaning |
|---|---|---|
| `item_id` | string | Stable id (branch name or roadmap-source path). |
| `source` | string | `"git_remote"` / `"dependabot"` / `"roadmap_source"`. |
| `branch_or_pr` | string | The branch name or `"not_applicable"` for roadmap rows. |
| `title` | string | Short label. Never carries payload. |
| `risk_class` | enum | See "Risk classes" below. |
| `checks_status` | enum | `"not_available"` in v3.15.15.16. Becomes real in v3.15.15.19. |
| `mergeability` | enum | Same. |
| `decision` | enum | `"needs_human"` \| `"operator_click"` \| `"recommendation_only"`. |
| `reason` | string | Short explanation. |
| `confidence` | enum | `"high"` \| `"low"` \| `"unknown"`. Always `"low"` or `"unknown"` for v3.15.15.16 because no external check evidence is available. |
| `next_action` | string | Operator-facing instruction. |

## Risk classes

| class | meaning |
|---|---|
| `safe_to_merge` | **Reserved but unreachable in v3.15.15.16 local mode.** Becomes reachable when external check evidence is supplied (v3.15.15.19 / .23). |
| `waiting_for_checks` | Diff is clean but checks are not readable yet. |
| `needs_human_protected_governance` | Diff touches a no-touch path (`.claude/**`, governance core docs, ADRs, etc.). |
| `needs_human_contract_risk` | Diff touches a frozen v1 contract. |
| `needs_human_trading_or_risk` | Diff matches a live/broker/paper/shadow path glob. |
| `blocked_failing_checks` | External evidence of red checks supplied (not produced in v3.15.15.16). |
| `blocked_conflict` | `git merge-tree` reports conflict markers vs `origin/main`. |
| `dependabot_patch_safe_candidate` | Dependabot patch bump; checks unverifiable here. |
| `dependabot_minor_safe_candidate` | Dependabot minor bump; checks unverifiable here. |
| `dependabot_major_framework_risk` | Dependabot major bump for `react`, `react-dom`, `vite`, `typescript`, `@types/react`, `@types/react-dom`, or any other major. |
| `unknown` | Default — anything the classifier cannot confidently place. |

## frontend_control_state

```json
{
  "schema_anchor": "v3.15.15.17",
  "json_artifact_path": "logs/autonomous_workloop/latest.json",
  "markdown_digest_path": "docs/governance/autonomous_workloop/latest.md",
  "read_only": true,
  "operator_actions": ["dry-run", "view-digest"],
  "execute_actions_unlocked_in": "v3.15.15.21"
}
```

The dashboard endpoints (v3.15.15.17) read this object verbatim and
expose it as `/api/agent-control/status`. The frontend never parses
the markdown digest.

## Final-report statements (the 10 limitations)

1. v3.15.15.16 is not full PR automation.
2. gh / API not available — `checks_status` / `mergeability` are
   `not_available`.
3. `merges_performed`: 0.
4. Operator-click merge is still required.
5. Roadmap execution is recommendation-only.
6. Dependabot safe candidates are not safe to merge without green
   checks.
7. Writer-level subagent attribution is gated by ADR-016 bootstrap.
8. Inferred attribution is convenience-only, not source-of-truth.
9. Next technical milestone for true autonomy is GitHub-backed
   PR/check integration (v3.15.15.19).
10. Frontend should consume JSON artifacts, not markdown.
