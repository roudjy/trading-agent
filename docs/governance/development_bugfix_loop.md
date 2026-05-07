# Autonomous Development Bugfix Loop (A10)

> Canonical governance document for the Bugfix Loop introduced in
> A10. Read-only intake; closed vocabularies; emits proposals to
> `logs/development_bugfix_loop/latest.json` only. Operator
> promotion remains manual.

## Status

Active. Modifications to this document require operator approval.

## What this is — and is not

A10 is the **intake** layer of the autonomous bugfix loop. It
consumes a structured failure-summary contract and emits bounded
bugfix-candidate proposals so the operator can decide what to
promote into the development work queue.

A10 is **not**:

- an automatic code-change generator,
- a branch / PR / commit creator,
- a test runner,
- a writer to `seed.jsonl` or `bugfix_seed.jsonl`,
- a fuzzy log parser,
- an LLM reasoner.

`reporting.development_bugfix_loop` produces only
`logs/development_bugfix_loop/latest.json`. Promotion of any
candidate into a queue seed file (or any actual code change) is a
separate operator action gated by the Execution Authority
classifier and the GitHub PR lifecycle protocol.

## Architectural separation: ADE core vs failure collectors

ADE core
:   `reporting/development_bugfix_loop.py`. Stdlib +
    `reporting.execution_authority` + `reporting.approval_policy` +
    `reporting.development_work_queue`. **No subprocess, no network,
    no `gh`, no `git`, no test runners.** Pinned by source-text
    scans and AST import inspection.

Failure collectors / adapters (out of scope for A10 core)
:   Optional, separately governed scripts that may live under
    `scripts/` or be operator-driven runbooks. Collectors **may**
    invoke `pytest`, `ruff`, `mypy`, `gh pr checks`, etc. to
    populate the failure-input contract. ADE core consumes the
    contract; ADE core never imports a collector.

The split is permanent. The operator may populate the failure
input by hand following this document — that is acceptable as a
transitional state, not the permanent architecture.

## Failure-input contract

Default path:
```
logs/bugfix_loop_input/latest.json
```

Schema (closed; additive only):

```json
{
  "schema_version": "1.0",
  "generated_at_utc": "<iso utc>",
  "failures": [
    {
      "failure_class": "<closed: see below>",
      "target_path": "<repo-relative path>",
      "message_digest": "<bounded scalar; deterministic hash of the failure message>",
      "severity": "low | medium | high | unknown",
      "occurrence_count": <int>,
      "first_seen_utc": "<iso utc>",
      "last_seen_utc": "<iso utc>",
      "detail": "<bounded scalar, ≤ 500 chars>"
    }
  ]
}
```

### Closed `failure_class` vocabulary (10)

```
unit_test, smoke_test, regression_test,
lint, typecheck, governance_lint,
frozen_hash, hook, ci_workflow, unknown
```

`unknown` is a fail-safe bucket — collectors should classify
explicitly when possible. The module routes `unknown` to
`human_operator`.

### Closed `severity` vocabulary (4)

```
low, medium, high, unknown
```

Severity maps deterministically to risk class for the Execution
Authority classifier (`low → LOW`, `medium → MEDIUM`, `high → HIGH`,
`unknown → UNKNOWN`).

## Output: per-candidate schema

```
candidate_id                       deterministic hash of (failure_class, target_path, message_digest)
failure_class                      closed
target_path                        bounded repo-relative
target_path_category               from execution_authority classifier
bugfix_scope                       closed (see below)
suggested_status                   "proposed" | "human_needed"
suggested_required_agent_role      from A8 AGENT_ROLES (closed mapping per failure_class)
suggested_category                 from A8 CATEGORIES (closed mapping per failure_class)
human_needed                       bool
human_needed_reason                from A8 HUMAN_NEEDED_REASONS
execution_authority_decision       AUTO_ALLOWED / NEEDS_HUMAN / PERMANENTLY_DENIED
execution_authority_reason         classifier reason
repeat_count                       bounded int (≥1)
first_seen_utc / last_seen_utc     bounded scalars
severity                           closed
acceptance_criteria_template       safe template list (no test-weakening tokens)
notes                              bounded scalar
created_at_placeholder             "deterministic_seed_placeholder"
updated_at_placeholder             "deterministic_seed_placeholder"
```

### Closed `bugfix_scope` vocabulary (7)

```
bounded_in_repo                — safe, scoped fix in non-protected repo paths
protected_path                 — touches a protected governance/policy/wiring/branch-protection/deploy path
live_path                      — touches automation/live_gate, broker/, agent/risk/, agent/execution/
frozen_contract                — research/research_latest.json or research/strategy_matrix.csv
ci_only                        — CI workflow change required (ci_guardian)
requires_architecture_review   — `other` target category or NEEDS_HUMAN authority
out_of_scope                   — would require test weakening or other governance violation
```

## Test-weakening discipline (load-bearing)

Acceptance-criteria templates are drawn from a closed safe set per
failure class. The template strings are pinned by tests to **never**
contain any of:

```
skip
xfail
pytest.mark.skip
pytest.mark.xfail
remove pin
weaken
relax
disable
```

This is the load-bearing test-weakening invariant. Adding a new
failure class requires adding a safe template that is also
test-weakening-clean, enforced by
`tests/unit/test_development_bugfix_loop.py::test_acceptance_templates_never_contain_test_weakening_tokens`.

## Authority and safety

- Items targeting `frozen_contract` paths ⇒ always
  `human_needed=true / frozen_contract_change`.
- Items targeting `live_path` ⇒ always
  `human_needed=true / capital_or_live_execution_related`.
- Items targeting `claude_governance_hook`, `dashboard_wiring`,
  `canonical_policy_doc`, `canonical_roadmap`,
  `branch_protection_config`, `deploy_script` ⇒ always
  `human_needed=true / protected_governance_change`.
- Items targeting `ci_workflow` ⇒
  `human_needed=true / protected_governance_change` (ci_guardian
  proposes the workflow PR; not the bugfix loop).
- Items whose Execution Authority decision is `NEEDS_HUMAN` /
  `PERMANENTLY_DENIED` ⇒ always `human_needed=true`.
- Items with `repeat_count ≥ REPEATED_FAILURE_THRESHOLD` (3) ⇒
  escalated to `human_needed / repeated_validation_failure`.

A `bugfix_scope=bounded_in_repo` candidate with `human_needed=false`
is **eligible** for operator promotion into the work queue. It is
not auto-promoted. The operator decides.

## Hard guarantees (pinned by tests)

- Stdlib + `reporting.execution_authority` +
  `reporting.approval_policy` + `reporting.development_work_queue`.
- No subprocess, no network, no `gh`, no `git`.
- No imports from `dashboard`, `automation`, `broker`,
  `agent.risk`, `agent.execution`, `research`,
  `reporting.intelligent_routing`, `pytest`, `_pytest`, `unittest`
  (AST-level pin).
- Atomic write only under
  `logs/development_bugfix_loop/latest.json`. The atomic-write
  guard explicitly refuses any `seed.jsonl` / `bugfix_seed.jsonl`
  path because both lie outside `logs/`.
- Wrapper carries an explicit `discipline_invariants` block:
  ```
  writes_to_seed_jsonl: false
  writes_to_bugfix_seed_jsonl: false
  auto_creates_branches: false
  auto_opens_prs: false
  auto_modifies_code: false
  operator_promotion_required: true
  ```

## CLI surface

```
python -m reporting.development_bugfix_loop            # writes artifact
python -m reporting.development_bugfix_loop --no-write  # stdout only
```

## Future collector path (preserved, not implemented in A10 v0)

Future collector scripts (under `scripts/`, not in ADE core) will:

1. Run the failing test suite or read CI artifacts (`gh run view --log`).
2. Parse JUnit XML / ruff JSON / mypy JSON / governance-lint output.
3. Hash failure messages into a stable `message_digest`.
4. Atomically write `logs/bugfix_loop_input/latest.json`.
5. Invoke `python -m reporting.development_bugfix_loop` to score.

The collector is governance/process work, separate from ADE core.

## Modifying this document

This is governance documentation. Modifications follow the same
discipline as the rest of `docs/governance/`: scope-bounded PR, CI
green, post-merge gates, no `--admin` merge.
