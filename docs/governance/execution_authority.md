# Execution Authority Governance

> Canonical policy document for v3.15.16.10. Defines the explicit
> boundary between actions Claude may take automatically, actions
> that require operator approval, and actions that are absolutely
> prohibited. This document is the source of truth; the
> `reporting.execution_authority` classifier (v3.15.16.10 phase B,
> Claude-implementable after this doc merges) is a deterministic
> projection of these tables.

## Status

Active. Modifications to this document require operator approval

(canonical policy doc — `NEEDS_HUMAN`).

## Scope

Applies to every action Claude (the implementation agent and its

sub-agents) takes against this repository, including:

* file reads, edits, creates, deletes

* git operations (branch, commit, push, PR open / merge)

* test, lint, and protocol invocations

* artifact regeneration calls (`reporting.<module> --mode dry-run`)

Out of scope:

* operator-authored governance bootstrap PRs (operator authority,

not Claude authority)

* deployment-implementation-agent edits to `scripts/deploy*.sh`

(governed by that agent's own allowlist; this document treats

deploy-script edits as `NEEDS_HUMAN` for the *generic* agent)

## Closed vocabularies

The classifier accepts only the values listed below. Any other

value is invalid input and yields `NEEDS_HUMAN` with reason

`unknown_risk_or_target_fail_safe`.

### `action_type` (24 values, closed)

| group | value | semantics |

|---|---|---|

| Read | `file_read` | open and parse a file |

| | `test_run` | invoke `pytest` (smoke / unit / integration / resilience / functional) |

| | `governance_lint_run` | invoke `scripts/governance_lint.py` |

| | `protocol_dry_run` | invoke `reporting.roadmap_execution_protocol --plan-item --dry-run` |

| | `artifact_regenerate` | invoke `reporting.<module>` whose only side effect is `logs/<module>/latest.json` |

| Modify | `file_edit` | modify an existing tracked file |

| | `file_create` | create a new tracked file |

| | `file_delete` | delete a tracked file |

| Git | `branch_create` | create a non-main branch |

| | `commit_create` | create a commit on a non-main branch |

| | `branch_push` | push a non-main branch to origin |

| | `pr_open` | open a PR via `gh pr create` |

| | `pr_squash_merge` | squash-merge an open PR via `gh pr merge --squash` |

| Always-deny git | `pr_force_push` | force push to any branch |

| | `main_direct_push` | direct push or force push to main |

| | `branch_protection_bypass` | merge with `--admin`, skip required checks, override CODEOWNERS |

| Always-deny remote | `remote_ssh` | SSH to a production VPS |

| | `remote_curl` | HTTP/curl to a remote production endpoint |

| Always-deny live | `live_broker_call` | place / cancel / amend a real-money order |

| | `live_capital_move` | move funds, change broker account state |

| Always-deny test | `test_weaken` | reduce assertions, mark tests xfail/skip without justification |

| Always-deny frozen | `frozen_contract_mutate` | byte-modify a frozen contract |

| Operator-only | `approval_inbox_decide` | approve / reject an `approval_inbox` row |

| | `agent_allowlist_widen` | edit `.claude/agents/<agent>.md` allowed_roots frontmatter |

### `target_path_category` (15 values, closed)

| value | path predicate |

|---|---|

| `claude_governance_hook` | path starts with `.claude/` |

| `dashboard_wiring` | path equals `dashboard/dashboard.py` exactly |

| `frozen_contract` | path equals `research/research_latest.json` or `research/strategy_matrix.csv` exactly |

| `live_path` | path matches `automation/live_gate.py`, `broker/**`, `agent/risk/**`, or `agent/execution/**` |

| `branch_protection_config` | path matches `.github/branch_protection_*.yml` (or any future repo-config file controlling branch protection) |

| `deploy_script` | path matches `scripts/deploy.sh` or `scripts/deploy_vps_dashboard.sh` |

| `canonical_policy_doc` | path matches `docs/governance/execution_authority.md`, `docs/governance/no_touch_paths.md`, or `docs/governance/observability_security_hardening.md` |

| `canonical_roadmap` | path equals `docs/roadmap/qre_roadmap_v6_1.md` exactly |

| `ci_workflow` | path matches `.github/workflows/**.yml` |

| `reporting_module` | path matches `reporting/**.py` |

| `dashboard_api` | path matches `dashboard/api_*.py` (excludes `dashboard.py` exactly) |

| `frontend` | path matches `frontend/src/**` |

| `test` | path matches `tests/{smoke,unit,integration,resilience,functional}/**`; **excludes** `tests/regression/**` (ask-only) |

| `doc_non_policy` | path matches `docs/**` and is not a `canonical_policy_doc` or `canonical_roadmap` |

| `other` | catch-all for paths matching no rule above |

`tests/regression/**` is intentionally excluded from `test` and falls into `other`. Regression tests are operator-only by convention.

### `risk_class` (4 values, reused)

`LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` — closed enum from `reporting.approval_policy.RISK_CLASSES`. The classifier MUST not redefine these.

### `decision` (3 values, closed)

| value | meaning |

|---|---|

| `AUTO_ALLOWED` | Claude may take the action without operator approval; the action is audit-logged through the existing audit emission pipeline |

| `NEEDS_HUMAN` | Claude must obtain operator approval through the PWA approval inbox before proceeding |

| `PERMANENTLY_DENIED` | Absolute bar; no approval path exists in this release |

### `reason` (closed vocabulary)

| group | value |

|---|---|

| AUTO_ALLOWED | `low_risk_read_only_projection` |

| | `low_risk_frontend_read_only` |

| | `low_risk_test_addition` |

| | `low_risk_docs_non_policy` |

| | `pure_read_no_side_effect` |

| NEEDS_HUMAN | `high_risk_governance_change` |

| | `high_risk_canonical_policy_change` |

| | `high_risk_canonical_roadmap_change` |

| | `agent_allowlist_widening` |

| | `deploy_script_modification` |

| | `ci_workflow_modification` |

| | `dashboard_wiring_modification` |

| | `claude_governance_hook_modification` |

| | `approval_inbox_decision` |

| | `unknown_risk_or_target_fail_safe` |

| PERMANENTLY_DENIED | `denied_frozen_contract_mutation` |

| | `denied_live_path_modification` |

| | `denied_branch_protection_bypass` |

| | `denied_main_direct_push` |

| | `denied_pr_force_push` |

| | `denied_remote_ssh` |

| | `denied_remote_curl` |

| | `denied_live_broker_call` |

| | `denied_live_capital_move` |

| | `denied_test_weakening` |

## Classifier contract

The future module `reporting.execution_authority` MUST expose

exactly the following surface and conform to every guarantee

listed below.

### Function signature

```python

def classify(

*,

action_type: str,            # in ACTION_TYPES

target_path: str | None,     # repo-relative path; None for non-path actions

risk_class: str = "UNKNOWN", # in {LOW, MEDIUM, HIGH, UNKNOWN}

) -> ExecutionDecision: ...

```

### Output dataclass

```python

@dataclasses.dataclass(frozen=True)

class ExecutionDecision:

decision: str               # one of DECISIONS

reason: str                 # one of REASONS

target_path_category: str   # one of TARGET_PATH_CATEGORIES

evidence: dict\[str, Any]    # bounded scalars only:

# {action_type, target_path,

#  target_path_category, risk_class}

```

The `evidence` field carries scalars only. It MUST NEVER contain

PR body text, file diffs, proposed patches, commit messages, or

template payload. Pinned by the test

`test_evidence_never_carries_pr_body_proposed_patch_file_diff`.

### Hard guarantees

* Stdlib-only. No `subprocess`, no network, no `gh`, no `git`.

* No imports from `dashboard`, `automation`, `broker`,

`agent.risk`, `agent.execution`.

* Pure function. No I/O. Never reads the file at `target_path`;

uses the path string only.

* Deterministic. Same input always returns the same output.

### Helper

`_categorize_path(target_path: str) -> str` is a pure

deterministic mapping from path string to a value in

`TARGET_PATH_CATEGORIES`. Returns `"other"` for paths matching no

rule. Pinned exhaustively by tests.

## Deterministic precedence

First-match wins. The classifier evaluates rules in this order:

1\. `PERMANENTLY_DENIED` rules (action-type-level)

2\. `PERMANENTLY_DENIED` rules (target-path-category-level for modify actions)

3\. `NEEDS_HUMAN` rules (target-path-category-level for protected-but-not-denied categories)

4\. `NEEDS_HUMAN` rules (risk-class HIGH or UNKNOWN)

5\. `NEEDS_HUMAN` rules (operator-only action types)

6\. `AUTO_ALLOWED` rules (pure reads regardless of target)

7\. `AUTO_ALLOWED` rules (LOW risk on auto categories)

8\. Default fallback â†’ `NEEDS_HUMAN` with reason `unknown_risk_or_target_fail_safe`

The default fallback is the security keystone. Anything not

explicitly auto-allowed is gated to operator approval.

## Permanently denied

### Action-type-level denies

Apply regardless of `target_path` and `risk_class`.

| `action_type` | `reason` |

|---|---|

| `pr_force_push` | `denied_pr_force_push` |

| `main_direct_push` | `denied_main_direct_push` |

| `branch_protection_bypass` | `denied_branch_protection_bypass` |

| `remote_ssh` | `denied_remote_ssh` |

| `remote_curl` | `denied_remote_curl` |

| `live_broker_call` | `denied_live_broker_call` |

| `live_capital_move` | `denied_live_capital_move` |

| `test_weaken` | `denied_test_weakening` |

| `frozen_contract_mutate` | `denied_frozen_contract_mutation` |

### Target-category-level denies (modify actions only)

| `target_path_category` | `reason` |

|---|---|

| `frozen_contract` | `denied_frozen_contract_mutation` |

| `live_path` | `denied_live_path_modification` |

| `branch_protection_config` | `denied_branch_protection_bypass` |

Read actions on these categories (`file_read`) are NOT denied — the

deny applies only to `file_edit`, `file_create`, `file_delete`.

## Needs-human

Apply after permanent-deny filters return no match.

| precondition | `reason` |

|---|---|

| `target_path_category == "claude_governance_hook"` and modify | `claude_governance_hook_modification` |

| `target_path_category == "dashboard_wiring"` and modify | `dashboard_wiring_modification` |

| `target_path_category == "canonical_policy_doc"` and modify | `high_risk_canonical_policy_change` |

| `target_path_category == "canonical_roadmap"` and modify | `high_risk_canonical_roadmap_change` |

| `target_path_category == "deploy_script"` and modify | `deploy_script_modification` |

| `target_path_category == "ci_workflow"` and modify | `ci_workflow_modification` |

| `action_type == "agent_allowlist_widen"` | `agent_allowlist_widening` |

| `action_type == "approval_inbox_decide"` | `approval_inbox_decision` |

| `risk_class == "HIGH"` (after the protected-path filter) | `high_risk_governance_change` |

| `risk_class == "UNKNOWN"` | `unknown_risk_or_target_fail_safe` |

| `target_path_category == "other"` and modify | `unknown_risk_or_target_fail_safe` |

## Auto-allowed

Apply only when no rule above matches.

| precondition | `reason` |

|---|---|

| `action_type âˆˆ {file_read, test_run, governance_lint_run, protocol_dry_run, artifact_regenerate}` (any target) | `pure_read_no_side_effect` |

| `target_path_category == "reporting_module"` and modify and `risk_class == LOW` | `low_risk_read_only_projection` |

| `target_path_category == "dashboard_api"` and modify and `risk_class == LOW` | `low_risk_read_only_projection` |

| `target_path_category == "frontend"` and modify and `risk_class == LOW` | `low_risk_frontend_read_only` |

| `target_path_category == "test"` and modify and `risk_class == LOW` | `low_risk_test_addition` |

| `target_path_category == "doc_non_policy"` and modify and `risk_class == LOW` | `low_risk_docs_non_policy` |

| `action_type âˆˆ {branch_create, commit_create, branch_push, pr_open, pr_squash_merge}` and every touched path in the PR has an AUTO_ALLOWED file-level decision | `low_risk_read_only_projection` (composite) |

## Protected paths summary

| path predicate | classification | enforcement |

|---|---|---|

| `.claude/**` | `claude_governance_hook` â†’ `NEEDS_HUMAN` (modify) | classifier + existing `deny_outside_agent_allowlist` and `deny_no_touch` hooks |

| `dashboard/dashboard.py` (exact) | `dashboard_wiring` â†’ `NEEDS_HUMAN` (modify) | classifier + existing `deny_no_touch` hook; governance-bootstrap PR pattern (PR #87, #104) |

| `research/research_latest.json` (exact) | `frozen_contract` â†’ `PERMANENTLY_DENIED` | classifier + `deny_no_touch` hook + CI `frozen-hash check` |

| `research/strategy_matrix.csv` (exact) | `frozen_contract` â†’ `PERMANENTLY_DENIED` | classifier + `deny_no_touch` hook + CI `frozen-hash check` |

| `automation/live_gate.py`, `broker/**`, `agent/risk/**`, `agent/execution/**` | `live_path` â†’ `PERMANENTLY_DENIED` (modify) | classifier + `deny_live_connector` hook |

| `.github/branch_protection_*.yml` | `branch_protection_config` â†’ `PERMANENTLY_DENIED` (modify) | classifier + GitHub repo settings |

| `scripts/deploy*.sh` | `deploy_script` â†’ `NEEDS_HUMAN` (modify) | classifier + deployment-implementation-agent allowlist |

| `docs/governance/execution_authority.md` | `canonical_policy_doc` â†’ `NEEDS_HUMAN` (modify) | this document; modifications require operator-authored PR |

| `docs/governance/no_touch_paths.md`, `docs/governance/observability_security_hardening.md` | `canonical_policy_doc` â†’ `NEEDS_HUMAN` (modify) | governance-bootstrap PR pattern |

| `docs/roadmap/qre_roadmap_v6_1.md` (exact) | `canonical_roadmap` â†’ `NEEDS_HUMAN` (modify) | operator-authored or operator-approved-Claude PR |

| `.github/workflows/**` | `ci_workflow` â†’ `NEEDS_HUMAN` (modify) | classifier + ci-guardian agent ownership |

## Operator-only boundaries

The following are operator authority and never `AUTO_ALLOWED`:

* Modifying any `canonical_policy_doc`, including this file

* Modifying `canonical_roadmap`

* Modifying `claude_governance_hook` (any file under `.claude/`)

* Modifying `dashboard_wiring` (`dashboard/dashboard.py`)

* Widening any agent's allowlist (`agent_allowlist_widen`)

* Deciding approval-inbox rows (`approval_inbox_decide`)

* Modifying `deploy_script` files (deployment-implementation-agent

may have additional authority via its own allowlist; the

generic agent is `NEEDS_HUMAN`)

* Modifying `ci_workflow` files (ci-guardian may have additional

authority via its own allowlist; the generic agent is

`NEEDS_HUMAN`)

* Any HIGH-risk action on any category

* Any UNKNOWN-risk action on any category

## Permanently denied actions (no approval path)

* `live_broker_call`, `live_capital_move` — no live trading

authorization in this release.

* `live_path` modifications — `automation/live_gate.py`,

`broker/**`, `agent/risk/**`, `agent/execution/**` MUST stay

byte-stable until a future explicitly governed phase adds an

authority for them. v3.15.16.10 does not introduce that

authority. v3.15.16.11 (Execution Engine Phase 1) is MEDIUM

risk and operates above the live_path; it is gated by this

classifier and does NOT modify live_path content.

* `frozen_contract_mutate` — `research/research_latest.json` and

`research/strategy_matrix.csv` are byte-frozen.

* `branch_protection_bypass` — branch protection is a CI-level

invariant. No `--admin` merges, no skip-required-checks, no

CODEOWNERS overrides.

* `main_direct_push`, `pr_force_push` — main is protected; force

pushes are denied on every branch to preserve audit trails.

* `remote_ssh`, `remote_curl` — Claude does not reach the

production VPS or any remote production endpoint. Operators

retain manual SSH access.

* `test_weaken` — test reductions, xfail / skip additions

without justification, and any pin removal in `tests/regression/`

are forbidden.

## v3.15.16.10 explicit non-goals

* No execution engine in this release. The classifier defines the

*policy ground*; the engine that consumes the classifier ships

in v3.15.16.11 (MEDIUM, Claude-implementable, operator-gated by

the classifier output).

* No widening of any agent's existing allowlist.

* No new mutation routes on Agent Control. Agent Control remains

GET-only and read-only.

* No edits to `.claude/`, `dashboard/dashboard.py`, frozen

contracts, or live paths.

* No live / paper / shadow / risk / trading behavior changes.

* No deploy-script changes. The deployment-implementation-agent

may ship a separate force-refresh fix in a later PR; out of

scope here.

* No direct push to main; no force push; no branch protection

bypass.

## Test matrix expectations

The test file `tests/unit/test_execution_authority.py` MUST pin

every cell of the policy matrix below. Cardinality target:

70â€“90 individual test functions; runtime budget under 1 second.

### Tier 1 — vocabulary integrity

| test | pins |

|---|---|

| `test_action_types_pinned` | `set(ACTION_TYPES)` equals the 24-value enum above |

| `test_target_path_categories_pinned` | `set(TARGET_PATH_CATEGORIES)` equals the 15-value enum above |

| `test_decisions_pinned` | `set(DECISIONS) == {AUTO_ALLOWED, NEEDS_HUMAN, PERMANENTLY_DENIED}` |

| `test_reasons_pinned` | `set(REASONS)` equals the closed reason vocabulary above |

| `test_risk_classes_match_approval_policy` | `RISK_CLASSES == reporting.approval_policy.RISK_CLASSES` |

### Tier 2 — path categorization (one assert per row of the path-predicate table)

Mandatory cases:

| input | expected category |

|---|---|

| `.claude/hooks/foo.py` | `claude_governance_hook` |

| `.claude/agents/foo.md` | `claude_governance_hook` |

| `dashboard/dashboard.py` | `dashboard_wiring` |

| `dashboard/api_agent_control.py` | `dashboard_api` |

| `research/research_latest.json` | `frozen_contract` |

| `research/strategy_matrix.csv` | `frozen_contract` |

| `automation/live_gate.py` | `live_path` |

| `broker/whatever.py` | `live_path` |

| `agent/risk/policy.py` | `live_path` |

| `agent/execution/runner.py` | `live_path` |

| `scripts/deploy_vps_dashboard.sh` | `deploy_script` |

| `scripts/deploy.sh` | `deploy_script` |

| `docs/governance/execution_authority.md` | `canonical_policy_doc` |

| `docs/governance/no_touch_paths.md` | `canonical_policy_doc` |

| `docs/roadmap/qre_roadmap_v6_1.md` | `canonical_roadmap` |

| `.github/workflows/tests.yml` | `ci_workflow` |

| `reporting/proposal_queue.py` | `reporting_module` |

| `tests/unit/foo.py` | `test` |

| `tests/regression/foo.py` | `other` |

| `docs/operator/getting_started.md` | `doc_non_policy` |

| `random/path.py` | `other` |

### Tier 3 — permanent-deny pinning

For each action_type in the always-deny list, parametrize the

decision call across every `target_path_category` and every

`risk_class`. Assert `decision == PERMANENTLY_DENIED` for all.

For each modify action_type (`file_edit`, `file_create`,

`file_delete`), parametrize across every category in the

target-category-level deny list. Assert `decision ==

PERMANENTLY_DENIED` for all.

### Tier 4 — needs-human pinning

One test per row of the needs-human table. Each test constructs

the precondition and asserts `decision == NEEDS_HUMAN` with the

documented reason.

### Tier 5 — auto-allowed pinning

One test per row of the auto-allowed table. Each test constructs

the precondition and asserts `decision == AUTO_ALLOWED` with the

documented reason.

### Tier 6 — precedence pinning

| test | scenario |

|---|---|

| `test_permanent_deny_overrides_risk_class` | `pr_force_push` with `risk_class=LOW` is `PERMANENTLY_DENIED` |

| `test_protected_path_overrides_low_risk_auto_allow` | `file_edit` on a `live_path` target with `risk_class=LOW` is `PERMANENTLY_DENIED` |

| `test_high_risk_overrides_low_risk_auto_categories` | `file_edit` on `reporting_module` with `risk_class=HIGH` is `NEEDS_HUMAN` |

| `test_unknown_risk_always_needs_human` | `risk_class=UNKNOWN` on any auto category is `NEEDS_HUMAN` |

| `test_default_fallback_is_needs_human_not_auto_allowed` | unknown action / category combination is `NEEDS_HUMAN` |

| `test_file_read_on_protected_path_still_auto_allowed` | reading any path is `AUTO_ALLOWED`; only modify is gated |

### Tier 7 — module invariants

| test | pins |

|---|---|

| `test_classify_is_deterministic` | 10 calls with identical input return identical output |

| `test_no_subprocess_in_module` | source-text scan: `import subprocess` and `from subprocess` are absent |

| `test_no_network_in_module` | source-text scan: `socket`, `http.client`, `urllib`, `requests` are absent |

| `test_no_dashboard_py_import` | source-text scan: no import of `dashboard` |

| `test_no_live_path_import` | source-text scan: no import of `automation.live_gate`, `broker`, `agent.risk`, `agent.execution` |

| `test_evidence_dict_contains_only_bounded_scalars` | constructed evidence has no list / dict body content |

| `test_evidence_never_carries_pr_body_proposed_patch_file_diff` | forbidden-token scan on a synthetic call |

## Authoring split

This release is split into two phases.

### Phase A — operator-authored (this PR)

| file | role |

|---|---|

| `docs/governance/execution_authority.md` | this document |

| `docs/roadmap/qre_roadmap_v6_1.md` | new `### v3.15.16.10 — Execution Authority Governance` entry under `## v3.15.16.x — â€¦` |

Risk class: HIGH (canonical policy doc). Operator authors and

merges. Claude does not open this PR.

### Phase B — Claude-implementable (follow-up PR after A merges)

| file | role |

|---|---|

| `reporting/execution_authority.py` | the deterministic stdlib-only classifier implementing the tables in this document |

| `tests/unit/test_execution_authority.py` | the exhaustive test matrix pinning every rule in this document |

Risk class: LOW (`reporting_read_only`). Protocol gate clears

auto-execute. Claude opens the PR after Phase A merges.

After Phase B merges, v3.15.16.11 (Execution Engine Phase 1,

MEDIUM, Claude-implementable, operator-gated by

`reporting.execution_authority.classify`) becomes plannable.

## Modifying this document

This document is a `canonical_policy_doc`. The classifier

classifies any modification as `NEEDS_HUMAN` with reason

`high_risk_canonical_policy_change`. Procedure:

1\. Operator opens a PR modifying `docs/governance/execution_authority.md`.

2\. The same PR updates `tests/unit/test_execution_authority.py`

to reflect the policy change. Tests must remain exhaustive.

3\. CI runs the full unit + smoke + governance_lint suite.

4\. Operator squash-merges after green CI.

5\. Auto-deploy refreshes downstream artifacts.

Direct edits to `reporting/execution_authority.py` without a

matching `docs/governance/execution_authority.md` change are

prohibited — the doc is the source of truth.




