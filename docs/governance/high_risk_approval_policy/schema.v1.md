# High-Risk Approval Policy — schema v1

Module: `reporting.approval_policy` (v3.15.15.24)
Schema version: `1`
Stability: stable; additions are SemVer minor, removals are breaking.

This is the machine-readable description of the canonical
HIGH-risk approval policy. Every governance / lifecycle module in
the repository imports this policy and produces decisions that
match it.

## Risk classes

```
RISK_CLASSES = ["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
```

* `LOW` — routine, reversible, scoped change with full evidence.
* `MEDIUM` — routine but coarser scope (production-Python floor
  bump, mixed/unknown diff scope, observability/testing/UX gap).
* `HIGH` — protected path / frozen contract / live trading / major
  semver bump / governance / canonical roadmap / external account
  / paid tool / telemetry / CI weakening.
* `UNKNOWN` — evidence missing or malformed. NEVER treated as LOW
  or MEDIUM.

## Decision enum (closed)

```
DECISIONS = [
  "allowed_read_only",
  "allowed_low_risk_execute_safe",
  "needs_human",
  "blocked_high_risk",
  "blocked_unknown",
  "blocked_protected_path",
  "blocked_frozen_contract",
  "blocked_live_paper_shadow_risk",
  "blocked_governance_change",
  "blocked_external_secret_required",
  "blocked_telemetry_or_data_egress",
  "blocked_paid_tool",
  "blocked_ci_or_test_weakening",
  "blocked_canonical_roadmap_change"
]
```

Only `allowed_low_risk_execute_safe` carries `executable=true`.
Every other decision returns `executable=false`.

## Approval categories

`APPROVAL_CATEGORIES` is the same set of strings used by
`reporting.approval_inbox`. The policy is the single source of
truth; the inbox imports it as a peer enum.

```
APPROVAL_CATEGORIES = [
  "roadmap_adoption_required",
  "high_risk_pr",
  "protected_path_change",
  "governance_change",
  "tooling_requires_approval",
  "external_account_or_secret_required",
  "telemetry_or_data_egress_required",
  "paid_tool_required",
  "frozen_contract_risk",
  "live_paper_shadow_risk_change",
  "ci_or_test_weakening_risk",
  "unknown_state",
  "failed_automation",
  "blocked_rebase",
  "blocked_checks",
  "runtime_halt",
  "security_alert",
  "manual_route_wiring_required"
]
```

## Allowed maximum action classes

```
ACTIONS = [
  "read_only",
  "propose_only",
  "low_risk_execute_safe",
  "none"
]
```

Decision -> `allowed_max_action`:

| decision                                  | allowed_max_action       |
| ----------------------------------------- | ------------------------ |
| allowed_read_only                         | read_only                |
| allowed_low_risk_execute_safe             | low_risk_execute_safe    |
| needs_human                               | propose_only             |
| any blocked_*                             | none                     |

## PolicyInput

```
PolicyInput {
  title: string
  summary: string
  source_type: string
  affected_files: string[]
  labels: string[]
  risk_class: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN"
  requested_action: string
  requires_secret: bool
  requires_external_account: bool
  requires_paid_tool: bool
  has_telemetry_or_data_egress: bool
  touches_governance: bool
  touches_frozen_contract: bool
  touches_live_paper_shadow_risk: bool
  touches_ci_or_tests: bool
  changes_canonical_roadmap: bool
  is_dependabot: bool
  pr_author: string
  provider_state: string
  checks_state: string
  mergeability_state: string
}
```

## PolicyDecision

```
PolicyDecision {
  decision: <one of DECISIONS>
  risk_class: <one of RISK_CLASSES>
  reason: string
  approval_category: <one of APPROVAL_CATEGORIES>
  allowed_max_action: <one of ACTIONS>
  executable: bool   # true ONLY for allowed_low_risk_execute_safe
  requires_human_approval: bool
  forbidden_agent_actions: string[]
  required_evidence: string[]
}
```

## Order of evaluation (first-match wins)

1. Frozen contract change -> `blocked_frozen_contract` (HIGH)
2. Protected path change -> `blocked_protected_path` (HIGH)
3. Live / paper / shadow / risk path change -> `blocked_live_paper_shadow_risk` (HIGH)
4. CI / test path change -> `blocked_ci_or_test_weakening` (HIGH)
5. Governance change (signal in title/summary OR `touches_governance`) -> `blocked_governance_change` (HIGH)
6. Canonical roadmap adoption -> `blocked_canonical_roadmap_change` (HIGH)
7. External account / secret / API key -> `blocked_external_secret_required` (HIGH)
8. Telemetry / data egress -> `blocked_telemetry_or_data_egress` (HIGH)
9. Paid plan / hosted SaaS -> `blocked_paid_tool` (HIGH)
10. `risk_class == HIGH` upstream -> `blocked_high_risk`
11. `risk_class == UNKNOWN` upstream -> `blocked_unknown`
12. Execute-safe path:
    - Non-Dependabot -> `needs_human`
    - HIGH -> `blocked_high_risk`
    - Provider/checks/merge bad -> `blocked_unknown`
    - LOW or MEDIUM Dependabot, CLEAN, all checks passed -> `allowed_low_risk_execute_safe`
13. Default -> `allowed_read_only`

The order is the safety contract; reordering is a breaking change.

## Universal forbidden agent actions

The `forbidden_agent_actions` list always includes:

```
"git push origin main"
"git push --force"
"git push --force-with-lease"
"gh pr merge --admin"
"edit .claude/**"
"edit AGENTS.md"
"edit CLAUDE.md"
"edit frozen contracts"
"edit automation/live_gate.py"
"modify VERSION"
"execute live broker"
"place real-money order"
"arbitrary shell command"
"free-form operator command string"
"shell=True subprocess"
"free-form argv"
"branch protection bypass"
"admin merge"
```

Each blocked decision adds its own per-decision extras (e.g.
`"regenerate research/research_latest.json without operator sign-off"`
under `blocked_frozen_contract`).

## Credential-value redaction

`assert_no_credential_values(payload)` raises `AssertionError`
when any string contains:

```
sk-ant-
ghp_
github_pat_
AKIA
BEGIN PRIVATE KEY
```

Path-shaped strings (`config/config.yaml`, `research/...`, etc.)
are explicitly allowed; the guard is intentionally narrow.

## Two-layer Dependabot opt-in

The policy alone does NOT enable Dependabot execute-safe. It is a
necessary but not sufficient condition. The state-file flag and
the runtime CLI flag are still required (see
`docs/governance/recurring_maintenance.md`).
