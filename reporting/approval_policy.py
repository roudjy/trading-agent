"""Shared HIGH-risk approval policy (v3.15.15.24).

A pure, deterministic, stdlib-only module that encodes ONE canonical
decision function for every other governance / lifecycle module to
import. It does not import Flask, the frontend, GitHub, or the
network. It does not perform I/O.

The goal is to remove drift between the duplicated risk-classification
blocks in:

* reporting.proposal_queue
* reporting.approval_inbox
* reporting.github_pr_lifecycle
* reporting.execute_safe_controls
* reporting.workloop_runtime
* reporting.recurring_maintenance

Each of those modules continues to own its own decision flow, but the
HIGH / UNKNOWN / protected / canonical / governance / live / risk /
secret / external / paid / telemetry / ci / frozen-contract verdict
is now produced by ONE function here. If a module diverges from this
verdict, a unit test in tests/unit/test_approval_policy.py will fail.

Hard guarantees
---------------

The decision function MUST satisfy the following invariants. They
are enforced by tests in
``tests/unit/test_approval_policy.py``:

* ``UNKNOWN`` never executes.
* ``HIGH`` never executes.
* Protected path overrides LOW / MEDIUM.
* Frozen contract change overrides LOW / MEDIUM.
* Live / paper / shadow / risk change overrides LOW / MEDIUM.
* CI / test weakening overrides LOW / MEDIUM.
* External account / secret / telemetry / paid -> needs_human or
  blocked.
* Canonical roadmap adoption -> needs_human.
* Malformed provider output -> UNKNOWN / blocked.
* Pending / failing / unknown checks block.
* Non-Dependabot execute-safe is blocked.
* Dependabot LOW / MEDIUM execute-safe is policy-allowed only when
  ALL evidence is present (mergeable, CLEAN, all checks passed,
  baseline ok, two-layer opt-in confirmed elsewhere).
* No decision returns ``executable=true`` for HIGH / UNKNOWN /
  needs_human / blocked_*.
* The output never contains credential-shaped values.

Stdlib-only.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import fnmatch
import re
from collections.abc import Iterable, Mapping
from typing import Any, Final


MODULE_VERSION: Final[str] = "v3.15.15.24"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Risk classes
# ---------------------------------------------------------------------------

RISK_LOW: Final[str] = "LOW"
RISK_MEDIUM: Final[str] = "MEDIUM"
RISK_HIGH: Final[str] = "HIGH"
RISK_UNKNOWN: Final[str] = "UNKNOWN"

RISK_CLASSES: Final[tuple[str, ...]] = (
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    RISK_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Decision classes (the closed set the policy emits)
# ---------------------------------------------------------------------------

DECISION_ALLOWED_READ_ONLY: Final[str] = "allowed_read_only"
DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE: Final[str] = "allowed_low_risk_execute_safe"
DECISION_NEEDS_HUMAN: Final[str] = "needs_human"
DECISION_BLOCKED_HIGH_RISK: Final[str] = "blocked_high_risk"
DECISION_BLOCKED_UNKNOWN: Final[str] = "blocked_unknown"
DECISION_BLOCKED_PROTECTED_PATH: Final[str] = "blocked_protected_path"
DECISION_BLOCKED_FROZEN_CONTRACT: Final[str] = "blocked_frozen_contract"
DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK: Final[str] = "blocked_live_paper_shadow_risk"
DECISION_BLOCKED_GOVERNANCE_CHANGE: Final[str] = "blocked_governance_change"
DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED: Final[str] = "blocked_external_secret_required"
DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS: Final[str] = "blocked_telemetry_or_data_egress"
DECISION_BLOCKED_PAID_TOOL: Final[str] = "blocked_paid_tool"
DECISION_BLOCKED_CI_OR_TEST_WEAKENING: Final[str] = "blocked_ci_or_test_weakening"
DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE: Final[str] = "blocked_canonical_roadmap_change"


DECISIONS: Final[tuple[str, ...]] = (
    DECISION_ALLOWED_READ_ONLY,
    DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE,
    DECISION_NEEDS_HUMAN,
    DECISION_BLOCKED_HIGH_RISK,
    DECISION_BLOCKED_UNKNOWN,
    DECISION_BLOCKED_PROTECTED_PATH,
    DECISION_BLOCKED_FROZEN_CONTRACT,
    DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK,
    DECISION_BLOCKED_GOVERNANCE_CHANGE,
    DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED,
    DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS,
    DECISION_BLOCKED_PAID_TOOL,
    DECISION_BLOCKED_CI_OR_TEST_WEAKENING,
    DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE,
)


# Approval categories — superset of approval_inbox CATEGORIES, kept
# as a pure mirror so downstream modules can map decision -> category
# without duplicating the enum.
APPROVAL_CATEGORIES: Final[tuple[str, ...]] = (
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
    "manual_route_wiring_required",
)


# ---------------------------------------------------------------------------
# Action classes
# ---------------------------------------------------------------------------

ACTION_READ_ONLY: Final[str] = "read_only"
ACTION_PROPOSE_ONLY: Final[str] = "propose_only"
ACTION_LOW_RISK_EXECUTE_SAFE: Final[str] = "low_risk_execute_safe"
ACTION_NONE: Final[str] = "none"

ACTIONS: Final[tuple[str, ...]] = (
    ACTION_READ_ONLY,
    ACTION_PROPOSE_ONLY,
    ACTION_LOW_RISK_EXECUTE_SAFE,
    ACTION_NONE,
)


# ---------------------------------------------------------------------------
# Forbidden / protected glob lists
# ---------------------------------------------------------------------------

# Frozen research contracts — byte-identity must be preserved.
FROZEN_CONTRACTS: Final[tuple[str, ...]] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


# Protected (no-touch) globs — mirror of
# ``docs/governance/no_touch_paths.md``.
PROTECTED_GLOBS: Final[tuple[str, ...]] = (
    ".claude/settings.json",
    ".claude/hooks/*",
    ".claude/hooks/**",
    ".claude/agents/*",
    ".claude/agents/**",
    ".claude/commands/*",
    ".claude/commands/**",
    "AGENTS.md",
    "CLAUDE.md",
    ".github/CODEOWNERS",
    "VERSION",
    "automation/live_gate.py",
    "automation/*.secret",
    "state/*.secret",
    "config/config.yaml",
    ".env",
    ".env.*",
    "*_latest.v1.json",
    "*_latest.v1.jsonl",
    "**/*_latest.v1.json",
    "**/*_latest.v1.jsonl",
    "docker-compose.prod.yml",
    "scripts/deploy.sh",
    "Dockerfile",
    "Dockerfile.*",
)


# Live / paper / shadow / trading / risk-bearing globs.
LIVE_PATH_GLOBS: Final[tuple[str, ...]] = (
    "execution/live/**",
    "automation/live/**",
    "agent/execution/live/**",
    "**/live_*broker*.py",
    "**/*live*broker*.py",
    "**/*live_executor*.py",
    "**/*live*executor*.py",
    "**/*_live.py",
    "automation/live_gate.py",
    "automation/**",
    "execution/**",
    "strategies/**",
    "agent/risk/**",
    "agent/execution/**",
    "**/paper/**",
    "**/shadow/**",
)


# CI / test / governance weakening globs. Anything under these paths
# always escalates to ``blocked_ci_or_test_weakening`` unless
# ``touches_ci_or_tests`` is explicitly False (which only the
# ci-guardian may set).
CI_OR_TESTS_GLOBS: Final[tuple[str, ...]] = (
    ".github/workflows/**",
    ".github/actions/**",
    "tests/regression/**",
    "scripts/governance_lint.py",
    "scripts/release_gate.py",
)


# Tokens that strongly suggest an external-account / secret / API-key
# requirement.
EXTERNAL_SECRET_TOKENS: Final[tuple[str, ...]] = (
    "api key",
    "api-key",
    "api_key",
    "auth token",
    "access token",
    "bearer token",
    "oauth",
    "signup",
    "sign-up",
    "create an account",
    "create account",
    "service account",
    "client secret",
    "client_secret",
    "private key",
    "ssh key",
)


# Tokens that strongly suggest telemetry / data egress.
TELEMETRY_TOKENS: Final[tuple[str, ...]] = (
    "telemetry",
    "datadog",
    "sentry",
    "segment.io",
    "google-analytics",
    "googletagmanager",
    "data egress",
    "pii export",
)


# Tokens that strongly suggest a paid plan / hosted SaaS.
PAID_TOOL_TOKENS: Final[tuple[str, ...]] = (
    "paid plan",
    "paid tier",
    "subscription",
    "saas",
    "hosted service",
    "hosted plan",
)


# Tokens that strongly suggest canonical roadmap adoption.
CANONICAL_ROADMAP_TOKENS: Final[tuple[str, ...]] = (
    "canonical roadmap",
    "new roadmap",
    "roadmap adoption",
    "rewrite roadmap",
    "supersede roadmap",
    "v4 roadmap",
    "post-v3.15",
)


# Negation prefixes — strip ``no <token>`` / ``no-<token>`` before
# matching tokens so "no telemetry" does not trigger telemetry.
_NEGATION_RE = re.compile(r"\bno[- ]\w[-\w ]*")


# Universal forbidden agent actions — surfaced on every blocked /
# needs_human decision regardless of category.
UNIVERSAL_FORBIDDEN_AGENT_ACTIONS: Final[tuple[str, ...]] = (
    "git push origin main",
    "git push --force",
    "git push --force-with-lease",
    "gh pr merge --admin",
    "edit .claude/**",
    "edit AGENTS.md",
    "edit CLAUDE.md",
    "edit frozen contracts",
    "edit automation/live_gate.py",
    "modify VERSION",
    "execute live broker",
    "place real-money order",
    "arbitrary shell command",
    "free-form operator command string",
    "shell=True subprocess",
    "free-form argv",
    "branch protection bypass",
    "admin merge",
)


# Decision -> additional forbidden actions. The universal list is
# always emitted; the per-decision list extends it.
_DECISION_FORBIDDEN_EXTRA: Final[Mapping[str, tuple[str, ...]]] = {
    DECISION_BLOCKED_PROTECTED_PATH: (
        "modify any path under .claude/**",
        "modify CODEOWNERS",
        "modify VERSION",
        "modify Dockerfile / Dockerfile.*",
        "modify docker-compose.prod.yml",
        "modify scripts/deploy.sh",
    ),
    DECISION_BLOCKED_FROZEN_CONTRACT: (
        "regenerate research/research_latest.json without operator sign-off",
        "regenerate research/strategy_matrix.csv without operator sign-off",
    ),
    DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK: (
        "modify execution/** or automation/** without operator approval",
        "modify agent/risk/** without operator approval",
        "modify paper/shadow trading flow without operator approval",
    ),
    DECISION_BLOCKED_GOVERNANCE_CHANGE: (
        "weaken hook layer",
        "weaken governance_lint",
        "modify .claude/agents/** without operator approval",
        "modify .claude/hooks/** without operator approval",
    ),
    DECISION_BLOCKED_CI_OR_TEST_WEAKENING: (
        "remove or skip required CI checks",
        "downgrade SHA pins",
        "disable required tests",
        "soften governance_lint",
    ),
    DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED: (
        "request or store API keys",
        "perform OAuth / SSO flow",
        "create accounts on third-party services",
        "linking the agent to any external account",
    ),
    DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS: (
        "send telemetry to a third-party service",
        "export PII",
        "open an outbound network egress for analytics",
    ),
    DECISION_BLOCKED_PAID_TOOL: (
        "subscribe to a paid plan",
        "exceed free tier without operator approval",
    ),
    DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE: (
        "rewrite or adopt a canonical roadmap autonomously",
        "supersede an existing roadmap autonomously",
    ),
    DECISION_BLOCKED_HIGH_RISK: (
        "auto-merge a HIGH PR",
        "auto-execute a HIGH action",
    ),
    DECISION_BLOCKED_UNKNOWN: (
        "act on UNKNOWN evidence",
        "treat malformed provider output as safe",
    ),
}


# Decision -> required evidence fields. The decision is reported but
# downstream consumers can use this list to surface what the operator
# should look at. None of the values are credentials.
_DECISION_REQUIRED_EVIDENCE: Final[Mapping[str, tuple[str, ...]]] = {
    DECISION_BLOCKED_PROTECTED_PATH: ("affected_files", "matched_protected_glob"),
    DECISION_BLOCKED_FROZEN_CONTRACT: ("affected_files", "matched_frozen_contract"),
    DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK: (
        "affected_files",
        "matched_live_glob",
    ),
    DECISION_BLOCKED_GOVERNANCE_CHANGE: ("touches_governance", "title", "summary"),
    DECISION_BLOCKED_CI_OR_TEST_WEAKENING: (
        "touches_ci_or_tests",
        "affected_files",
    ),
    DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED: (
        "requires_secret",
        "requires_external_account",
        "matched_secret_token",
    ),
    DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS: (
        "has_telemetry_or_data_egress",
        "matched_telemetry_token",
    ),
    DECISION_BLOCKED_PAID_TOOL: ("requires_paid_tool", "matched_paid_token"),
    DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE: (
        "changes_canonical_roadmap",
        "title",
        "summary",
    ),
    DECISION_BLOCKED_HIGH_RISK: ("risk_class", "title", "summary"),
    DECISION_BLOCKED_UNKNOWN: ("provider_state", "checks_state", "mergeability_state"),
    DECISION_NEEDS_HUMAN: ("title", "summary"),
    DECISION_ALLOWED_READ_ONLY: (),
    DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE: (
        "is_dependabot",
        "checks_state",
        "mergeability_state",
        "risk_class",
    ),
}


# Decision -> approval inbox category. The mapping is intentionally
# many-to-one: e.g. both the dedicated frozen-contract decision and
# the protected-path decision can ultimately ask the operator for
# guidance, but the approval surface keeps them distinct.
_DECISION_TO_CATEGORY: Final[Mapping[str, str]] = {
    DECISION_BLOCKED_PROTECTED_PATH: "protected_path_change",
    DECISION_BLOCKED_FROZEN_CONTRACT: "frozen_contract_risk",
    DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK: "live_paper_shadow_risk_change",
    DECISION_BLOCKED_GOVERNANCE_CHANGE: "governance_change",
    DECISION_BLOCKED_CI_OR_TEST_WEAKENING: "ci_or_test_weakening_risk",
    DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED: "external_account_or_secret_required",
    DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS: "telemetry_or_data_egress_required",
    DECISION_BLOCKED_PAID_TOOL: "paid_tool_required",
    DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE: "roadmap_adoption_required",
    DECISION_BLOCKED_HIGH_RISK: "high_risk_pr",
    DECISION_BLOCKED_UNKNOWN: "unknown_state",
    DECISION_NEEDS_HUMAN: "tooling_requires_approval",
}


# ---------------------------------------------------------------------------
# Glob / token helpers
# ---------------------------------------------------------------------------


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _matches_any(path: str, globs: Iterable[str]) -> str | None:
    n = _norm(path)
    for g in globs:
        if fnmatch.fnmatchcase(n, g):
            return g
    return None


def diff_touches_frozen(files: Iterable[str]) -> tuple[bool, str | None]:
    """First match wins; returns ``(True, frozen_path)`` or
    ``(False, None)``."""
    for f in files:
        n = _norm(f)
        if n in FROZEN_CONTRACTS:
            return (True, n)
    return (False, None)


def diff_touches_protected(files: Iterable[str]) -> tuple[bool, str | None]:
    """``frozen ⊂ protected`` semantically — but a dedicated check is
    still needed so a caller can distinguish ``frozen_contract_risk``
    from a generic ``protected_path_change``."""
    for f in files:
        n = _norm(f)
        if n in FROZEN_CONTRACTS:
            return (True, n)
    for f in files:
        match = _matches_any(f, PROTECTED_GLOBS)
        if match:
            return (True, _norm(f))
    return (False, None)


def diff_touches_live(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        match = _matches_any(f, LIVE_PATH_GLOBS)
        if match:
            return (True, _norm(f))
    return (False, None)


def diff_touches_ci_or_tests(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        match = _matches_any(f, CI_OR_TESTS_GLOBS)
        if match:
            return (True, _norm(f))
    return (False, None)


def _scrub_negations(text: str) -> str:
    """Strip ``no <token>`` / ``no-<token>`` so explicit negations
    cannot trigger HIGH-token rules. Lower-cased input."""
    return _NEGATION_RE.sub(" ", text)


def _matched_token(text: str, tokens: Iterable[str]) -> str | None:
    """Return the first matching token in ``text`` after negation
    scrub, or ``None``. ``text`` is expected lower-cased already."""
    scrubbed = _scrub_negations(text)
    for t in tokens:
        if t in scrubbed:
            return t
    return None


# ---------------------------------------------------------------------------
# PolicyInput / PolicyDecision dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PolicyInput:
    """All inputs the policy considers. Optional fields default to
    ``None`` / ``False`` / ``""`` so callers can supply only what they
    know — missing evidence routes to UNKNOWN, never to LOW."""

    title: str = ""
    summary: str = ""
    source_type: str = ""
    affected_files: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    risk_class: str = RISK_UNKNOWN
    requested_action: str = ""
    requires_secret: bool = False
    requires_external_account: bool = False
    requires_paid_tool: bool = False
    has_telemetry_or_data_egress: bool = False
    touches_governance: bool = False
    touches_frozen_contract: bool = False
    touches_live_paper_shadow_risk: bool = False
    touches_ci_or_tests: bool = False
    changes_canonical_roadmap: bool = False
    is_dependabot: bool = False
    pr_author: str = ""
    provider_state: str = ""
    checks_state: str = ""
    mergeability_state: str = ""

    @staticmethod
    def from_mapping(d: Mapping[str, Any]) -> "PolicyInput":
        """Lift a plain dict into a ``PolicyInput``. Unknown keys are
        ignored; missing keys take their dataclass defaults. Tuples
        are normalised from any iterable."""
        def _tup(v: Any) -> tuple[str, ...]:
            if v is None:
                return ()
            if isinstance(v, (list, tuple)):
                return tuple(str(x) for x in v)
            return (str(v),)

        def _str(v: Any) -> str:
            if v is None:
                return ""
            return str(v)

        def _bool(v: Any) -> bool:
            return bool(v) if v is not None else False

        rc = _str(d.get("risk_class")) or RISK_UNKNOWN
        if rc not in RISK_CLASSES:
            rc = RISK_UNKNOWN
        return PolicyInput(
            title=_str(d.get("title")),
            summary=_str(d.get("summary")),
            source_type=_str(d.get("source_type")),
            affected_files=_tup(d.get("affected_files")),
            labels=_tup(d.get("labels")),
            risk_class=rc,
            requested_action=_str(d.get("requested_action")),
            requires_secret=_bool(d.get("requires_secret")),
            requires_external_account=_bool(d.get("requires_external_account")),
            requires_paid_tool=_bool(d.get("requires_paid_tool")),
            has_telemetry_or_data_egress=_bool(
                d.get("has_telemetry_or_data_egress")
            ),
            touches_governance=_bool(d.get("touches_governance")),
            touches_frozen_contract=_bool(d.get("touches_frozen_contract")),
            touches_live_paper_shadow_risk=_bool(
                d.get("touches_live_paper_shadow_risk")
            ),
            touches_ci_or_tests=_bool(d.get("touches_ci_or_tests")),
            changes_canonical_roadmap=_bool(d.get("changes_canonical_roadmap")),
            is_dependabot=_bool(d.get("is_dependabot")),
            pr_author=_str(d.get("pr_author")),
            provider_state=_str(d.get("provider_state")),
            checks_state=_str(d.get("checks_state")),
            mergeability_state=_str(d.get("mergeability_state")),
        )


@dataclasses.dataclass(frozen=True)
class PolicyDecision:
    """The pure output of ``decide()``.

    Invariants:

    * ``executable`` is True only for
      ``allowed_low_risk_execute_safe``. ``allowed_read_only`` is
      reading-only; the caller must not interpret it as
      ``executable``.
    * ``decision`` is always in ``DECISIONS``.
    * ``risk_class`` is always in ``RISK_CLASSES``.
    """

    decision: str
    risk_class: str
    reason: str
    approval_category: str
    allowed_max_action: str
    executable: bool
    requires_human_approval: bool
    forbidden_agent_actions: tuple[str, ...]
    required_evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "risk_class": self.risk_class,
            "reason": self.reason,
            "approval_category": self.approval_category,
            "allowed_max_action": self.allowed_max_action,
            "executable": self.executable,
            "requires_human_approval": self.requires_human_approval,
            "forbidden_agent_actions": list(self.forbidden_agent_actions),
            "required_evidence": list(self.required_evidence),
        }


def _build_decision(
    *,
    decision: str,
    risk_class: str,
    reason: str,
) -> PolicyDecision:
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision!r}")
    if risk_class not in RISK_CLASSES:
        raise ValueError(f"unknown risk_class: {risk_class!r}")
    executable = decision == DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE
    requires_human_approval = decision in (
        DECISION_NEEDS_HUMAN,
        DECISION_BLOCKED_HIGH_RISK,
        DECISION_BLOCKED_UNKNOWN,
        DECISION_BLOCKED_PROTECTED_PATH,
        DECISION_BLOCKED_FROZEN_CONTRACT,
        DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK,
        DECISION_BLOCKED_GOVERNANCE_CHANGE,
        DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED,
        DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS,
        DECISION_BLOCKED_PAID_TOOL,
        DECISION_BLOCKED_CI_OR_TEST_WEAKENING,
        DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE,
    )
    if decision == DECISION_ALLOWED_READ_ONLY:
        allowed_max_action = ACTION_READ_ONLY
    elif decision == DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE:
        allowed_max_action = ACTION_LOW_RISK_EXECUTE_SAFE
    elif decision == DECISION_NEEDS_HUMAN:
        allowed_max_action = ACTION_PROPOSE_ONLY
    else:
        allowed_max_action = ACTION_NONE
    forbidden = list(UNIVERSAL_FORBIDDEN_AGENT_ACTIONS)
    forbidden.extend(_DECISION_FORBIDDEN_EXTRA.get(decision, ()))
    # De-duplicate while preserving order.
    seen: set[str] = set()
    forbidden_unique: list[str] = []
    for f in forbidden:
        if f not in seen:
            seen.add(f)
            forbidden_unique.append(f)
    required = tuple(_DECISION_REQUIRED_EVIDENCE.get(decision, ()))
    return PolicyDecision(
        decision=decision,
        risk_class=risk_class,
        reason=reason,
        approval_category=_DECISION_TO_CATEGORY.get(decision, "tooling_requires_approval"),
        allowed_max_action=allowed_max_action,
        executable=executable,
        requires_human_approval=requires_human_approval,
        forbidden_agent_actions=tuple(forbidden_unique),
        required_evidence=required,
    )


# ---------------------------------------------------------------------------
# decide() — the canonical decision function
# ---------------------------------------------------------------------------


def decide(p: PolicyInput | Mapping[str, Any]) -> PolicyDecision:
    """The single source of truth for HIGH-risk approval decisions.

    Order of evaluation — first match wins. The order is the
    governing safety contract; do NOT reorder without updating
    ``tests/unit/test_approval_policy.py``.
    """
    pi = p if isinstance(p, PolicyInput) else PolicyInput.from_mapping(p)
    title_l = pi.title.lower()
    summary_l = pi.summary.lower()
    text_l = f"{title_l}\n{summary_l}"
    files = list(pi.affected_files)

    # 1. Frozen contract (most specific protected path).
    frozen_hit, frozen_path = diff_touches_frozen(files)
    if frozen_hit or pi.touches_frozen_contract:
        return _build_decision(
            decision=DECISION_BLOCKED_FROZEN_CONTRACT,
            risk_class=RISK_HIGH,
            reason=(
                f"frozen contract change: {frozen_path}"
                if frozen_path
                else "input flag touches_frozen_contract is true"
            ),
        )

    # 2. Protected path (no-touch / .claude/** / AGENTS.md / ...).
    prot_hit, prot_path = diff_touches_protected(files)
    if prot_hit:
        return _build_decision(
            decision=DECISION_BLOCKED_PROTECTED_PATH,
            risk_class=RISK_HIGH,
            reason=f"protected path change: {prot_path}",
        )

    # 3. Live / paper / shadow / risk path.
    live_hit, live_path = diff_touches_live(files)
    if live_hit or pi.touches_live_paper_shadow_risk:
        return _build_decision(
            decision=DECISION_BLOCKED_LIVE_PAPER_SHADOW_RISK,
            risk_class=RISK_HIGH,
            reason=(
                f"live/paper/shadow/risk path change: {live_path}"
                if live_path
                else "input flag touches_live_paper_shadow_risk is true"
            ),
        )

    # 4. CI / test weakening.
    ci_hit, ci_path = diff_touches_ci_or_tests(files)
    if ci_hit or pi.touches_ci_or_tests:
        return _build_decision(
            decision=DECISION_BLOCKED_CI_OR_TEST_WEAKENING,
            risk_class=RISK_HIGH,
            reason=(
                f"CI/test path change: {ci_path}"
                if ci_path
                else "input flag touches_ci_or_tests is true"
            ),
        )

    # 5. Governance change (signal in summary OR explicit flag).
    if pi.touches_governance or any(
        t in text_l
        for t in (
            ".claude/",
            "agents.md",
            "claude.md",
            "branch protection",
            "codeowners",
            "no_touch_paths",
            "agent governance",
            "release gate",
            "autonomy ladder",
        )
    ):
        return _build_decision(
            decision=DECISION_BLOCKED_GOVERNANCE_CHANGE,
            risk_class=RISK_HIGH,
            reason="touches governance surface",
        )

    # 6. Canonical roadmap adoption.
    if pi.changes_canonical_roadmap or _matched_token(
        text_l, CANONICAL_ROADMAP_TOKENS
    ):
        return _build_decision(
            decision=DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE,
            risk_class=RISK_HIGH,
            reason="canonical roadmap adoption requires human approval",
        )

    # 7. External account / secret.
    secret_token = _matched_token(text_l, EXTERNAL_SECRET_TOKENS)
    if pi.requires_secret or pi.requires_external_account or secret_token:
        return _build_decision(
            decision=DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED,
            risk_class=RISK_HIGH,
            reason=(
                f"external secret/account: token {secret_token!r}"
                if secret_token
                else "input flag requires_secret/requires_external_account is true"
            ),
        )

    # 8. Telemetry / data egress.
    telemetry_token = _matched_token(text_l, TELEMETRY_TOKENS)
    if pi.has_telemetry_or_data_egress or telemetry_token:
        return _build_decision(
            decision=DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS,
            risk_class=RISK_HIGH,
            reason=(
                f"telemetry/data egress: token {telemetry_token!r}"
                if telemetry_token
                else "input flag has_telemetry_or_data_egress is true"
            ),
        )

    # 9. Paid tool.
    paid_token = _matched_token(text_l, PAID_TOOL_TOKENS)
    if pi.requires_paid_tool or paid_token:
        return _build_decision(
            decision=DECISION_BLOCKED_PAID_TOOL,
            risk_class=RISK_HIGH,
            reason=(
                f"paid plan: token {paid_token!r}"
                if paid_token
                else "input flag requires_paid_tool is true"
            ),
        )

    # 10. HIGH risk class declared upstream.
    if pi.risk_class == RISK_HIGH:
        return _build_decision(
            decision=DECISION_BLOCKED_HIGH_RISK,
            risk_class=RISK_HIGH,
            reason="upstream classified the input as HIGH",
        )

    # 11. UNKNOWN risk class OR malformed provider/check/merge state.
    if pi.risk_class == RISK_UNKNOWN:
        return _build_decision(
            decision=DECISION_BLOCKED_UNKNOWN,
            risk_class=RISK_UNKNOWN,
            reason="risk_class is UNKNOWN",
        )
    bad_provider = pi.provider_state in ("malformed", "unknown")
    bad_checks = pi.checks_state in ("failed", "pending", "unknown")
    bad_merge = pi.mergeability_state in ("dirty", "behind", "unknown", "")
    if pi.requested_action == "execute_safe" and (bad_provider or bad_checks):
        return _build_decision(
            decision=DECISION_BLOCKED_UNKNOWN,
            risk_class=RISK_UNKNOWN,
            reason=(
                f"execute_safe blocked on provider_state={pi.provider_state!r}, "
                f"checks_state={pi.checks_state!r}, "
                f"mergeability_state={pi.mergeability_state!r}"
            ),
        )

    # 12. Execute-safe path — the ONLY decision that returns
    # executable=True. Both layers of opt-in (state-file + CLI flag)
    # are checked in the recurring_maintenance / execute_safe modules
    # themselves; this function only gates on the per-PR evidence.
    if pi.requested_action == "execute_safe":
        if not pi.is_dependabot:
            return _build_decision(
                decision=DECISION_NEEDS_HUMAN,
                risk_class=pi.risk_class,
                reason=(
                    "execute_safe is restricted to Dependabot PRs; "
                    f"author={pi.pr_author!r}"
                ),
            )
        if pi.risk_class not in (RISK_LOW, RISK_MEDIUM):
            return _build_decision(
                decision=DECISION_BLOCKED_HIGH_RISK,
                risk_class=pi.risk_class,
                reason=(
                    "execute_safe requires LOW or MEDIUM risk; "
                    f"got {pi.risk_class!r}"
                ),
            )
        if bad_merge or pi.checks_state != "passed":
            return _build_decision(
                decision=DECISION_BLOCKED_UNKNOWN,
                risk_class=RISK_UNKNOWN,
                reason=(
                    "execute_safe requires CLEAN mergeability and passed checks; "
                    f"checks_state={pi.checks_state!r}, "
                    f"mergeability_state={pi.mergeability_state!r}"
                ),
            )
        return _build_decision(
            decision=DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE,
            risk_class=pi.risk_class,
            reason="LOW/MEDIUM Dependabot PR with CLEAN merge + passed checks",
        )

    # 13. Default — read-only is always allowed when nothing above
    # matched. The caller decides whether to surface the row.
    return _build_decision(
        decision=DECISION_ALLOWED_READ_ONLY,
        risk_class=pi.risk_class if pi.risk_class != RISK_UNKNOWN else RISK_LOW,
        reason="no high-risk gate matched; read-only surfacing allowed",
    )


# ---------------------------------------------------------------------------
# Convenience helpers for downstream modules
# ---------------------------------------------------------------------------


def decision_to_category(decision: str) -> str:
    """Map a decision name to an approval-inbox category. Defaults to
    ``tooling_requires_approval`` for unmapped decisions."""
    return _DECISION_TO_CATEGORY.get(decision, "tooling_requires_approval")


def is_executable_decision(decision: str) -> bool:
    """The single canonical answer to "may this auto-execute?"."""
    return decision == DECISION_ALLOWED_LOW_RISK_EXECUTE_SAFE


def universal_forbidden_actions() -> tuple[str, ...]:
    return UNIVERSAL_FORBIDDEN_AGENT_ACTIONS


def policy_summary() -> dict[str, Any]:
    """A read-only, deterministic summary of the policy. Suitable for
    surfacing on status endpoints. Does not include credential-shaped
    values."""
    return {
        "module_version": MODULE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utcnow(),
        "risk_classes": list(RISK_CLASSES),
        "decisions": list(DECISIONS),
        "approval_categories": list(APPROVAL_CATEGORIES),
        "allowed_max_actions": list(ACTIONS),
        "forbidden_agent_actions_universal": list(UNIVERSAL_FORBIDDEN_AGENT_ACTIONS),
        "frozen_contracts": list(FROZEN_CONTRACTS),
        "protected_globs_count": len(PROTECTED_GLOBS),
        "live_globs_count": len(LIVE_PATH_GLOBS),
        "ci_or_tests_globs_count": len(CI_OR_TESTS_GLOBS),
        "external_secret_tokens_count": len(EXTERNAL_SECRET_TOKENS),
        "telemetry_tokens_count": len(TELEMETRY_TOKENS),
        "paid_tool_tokens_count": len(PAID_TOOL_TOKENS),
        "canonical_roadmap_tokens_count": len(CANONICAL_ROADMAP_TOKENS),
        "high_or_unknown_is_executable": False,
        "execute_safe_requires_dependabot_low_or_medium": True,
        "execute_safe_requires_two_layer_opt_in": True,
    }


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Credential-value redaction (mirrors the pattern in workloop_runtime
# and recurring_maintenance — defense in depth)
# ---------------------------------------------------------------------------


_CREDENTIAL_FRAGMENTS: Final[tuple[str, ...]] = (
    "sk-ant-",
    "ghp_",
    "github_pat_",
    "AKIA",
    "BEGIN PRIVATE KEY",
)


def assert_no_credential_values(payload: Any, *, _path: str = "$") -> None:
    """Raise ``AssertionError`` if any string in ``payload`` looks
    like a credential value. Path-shaped strings are explicitly
    allowed — only the narrow credential fragments above are
    rejected.

    Mirrors ``reporting.workloop_runtime._assert_no_credential_values``.
    """
    if isinstance(payload, str):
        for frag in _CREDENTIAL_FRAGMENTS:
            if frag in payload:
                raise AssertionError(
                    f"credential-shaped value at {_path}: contains {frag!r}"
                )
        return
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            assert_no_credential_values(v, _path=f"{_path}.{k}")
        return
    if isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_no_credential_values(v, _path=f"{_path}[{i}]")
        return
    return
