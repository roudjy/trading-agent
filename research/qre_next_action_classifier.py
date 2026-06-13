"""QRE next-action classifier.

This module classifies controlled-research ``next_action`` strings into
operator/ADE-safe routing decisions. It is deliberately planning-only:
no execution authority is granted here.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_next_action_classification"

BLOCKED_AUTHORITIES: Final[tuple[str, ...]] = (
    "paper_shadow_live",
    "broker_risk_execution",
    "campaign_mutation",
    "candidate_promotion",
    "strategy_or_preset_registry_mutation",
    "public_research_output_mutation",
    "broad_run_research",
    "campaign_launcher_direct_execution",
    "external_data_or_network_fetch",
)

ACCEPTANCE_COMMANDS: Final[tuple[str, ...]] = (
    "python -m pytest tests/unit/test_qre_autonomous_market_research_loop.py -q",
    "python -m pytest tests/unit/test_qre_next_action_classifier.py -q",
    "python -m pytest tests/unit/test_qre_build_request_writer.py -q",
    "python -m pytest tests/unit/test_qre_daily_status_digest.py -q",
    "python -m pytest tests/unit/test_qre_controlled_research_run.py -q",
    "python -m research.qre_autonomous_market_research_loop --write --max-cycles 3",
    "python -m research.qre_daily_status_digest --write",
    "git diff --check",
    "git diff -- research/research_latest.json research/strategy_matrix.csv",
)


@dataclass(frozen=True)
class ActionRule:
    rule_id: str
    patterns: tuple[str, ...]
    action_class: str
    safety_class: str
    ade_build_allowed: bool
    human_review_required: bool


RULES: Final[tuple[ActionRule, ...]] = (
    ActionRule(
        rule_id="unsafe_blocked",
        patterns=(
            "activate_live*",
            "enable_shadow*",
            "enable_paper*",
            "promote_candidate*",
            "launch_campaign*",
            "mutate_strategy*",
            "mutate_preset*",
            "increase_risk*",
            "broker*",
            "execution*",
            "place_order*",
            "trade*",
        ),
        action_class="blocked",
        safety_class="unsafe_requires_explicit_separate_governance",
        ade_build_allowed=False,
        human_review_required=True,
    ),
    ActionRule(
        rule_id="hold_or_review",
        patterns=("hold_do_not_build", "operator_review_required", "human_review_required"),
        action_class="review_required",
        safety_class="human_review_required",
        ade_build_allowed=False,
        human_review_required=True,
    ),
    ActionRule(
        rule_id="safe_rerun_or_operator_instruction",
        patterns=("rerun*", "keep_same_universe*", "do_not_rotate*", "adjust_threshold*"),
        action_class="safe_rerun_or_operator_instruction",
        safety_class="safe_to_plan_requires_runtime_gate",
        ade_build_allowed=False,
        human_review_required=True,
    ),
    ActionRule(
        rule_id="metric_data_research_infrastructure",
        patterns=(
            "add_*metric*",
            "*cache_only*",
            "*oos*",
            "*drawdown*",
            "*sharpe*",
            "*trade_count*",
            "add_source_identity*",
            "add_data_freshness*",
            "add_metric_readiness*",
            "add_result_to_market_intake_feedback*",
            "repair_cache_or_add_safe_metric_input",
            "add_preset_metric_adapter",
            "add_safe_oos_splitter",
        ),
        action_class="code_required",
        safety_class="safe_to_plan_requires_pr",
        ade_build_allowed=True,
        human_review_required=True,
    ),
    ActionRule(
        rule_id="reporting_or_ux",
        patterns=(
            "add_*report*",
            "add_operator_summary*",
            "add_blocker_diagnosis*",
            "add_universe_coverage_report",
            "add_research_run_comparison_report",
        ),
        action_class="reporting_or_ux_code_required",
        safety_class="safe_to_plan_requires_pr",
        ade_build_allowed=True,
        human_review_required=True,
    ),
)


def _normalize_action(action: str) -> str:
    value = str(action or "").strip().lower()
    value = re.sub(r"[^a-z0-9_*-]+", "_", value)
    return value.strip("_")


def _slug(value: str, *, max_len: int = 56) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_action(value)).strip("-")
    return (slug[:max_len].strip("-") or "qre-next-action")


def _title(value: str) -> str:
    words = _slug(value).replace("-", " ")
    return f"feat: {words}"


def _scope_for(action: str, action_class: str) -> list[str]:
    if action_class == "code_required":
        return [
            "inspect existing cache-only and controlled metric readers",
            "add or wire a no-network exact-universe metric evidence path if no safe path exists",
            "preserve bounded metric evidence when true metrics remain unavailable",
            "prove protected public research artifacts remain unchanged",
        ]
    if action_class == "reporting_or_ux_code_required":
        return [
            "add the requested report or operator-summary projection",
            "keep output logs-only and safe_to_execute=false",
            "prove no protected public research artifacts are mutated",
        ]
    if action_class == "safe_rerun_or_operator_instruction":
        return [
            "prepare operator rerun instructions only",
            "do not execute runtime changes without an explicit gate",
        ]
    return ["operator review required before implementation scope is defined"]


def classify_next_action(next_action: str) -> dict[str, object]:
    """Classify one next action using denylist-first pattern families."""

    normalized = _normalize_action(next_action)
    matched_rule: ActionRule | None = None
    matched_pattern = ""
    for rule in RULES:
        for pattern in rule.patterns:
            if fnmatch.fnmatchcase(normalized, pattern):
                matched_rule = rule
                matched_pattern = pattern
                break
        if matched_rule is not None:
            break

    if matched_rule is None:
        action_class = "unknown"
        safety_class = "fail_closed_human_review_required"
        ade_build_allowed = False
        human_review_required = True
        rule_id = "unknown_fail_closed"
    else:
        action_class = matched_rule.action_class
        safety_class = matched_rule.safety_class
        ade_build_allowed = matched_rule.ade_build_allowed
        human_review_required = matched_rule.human_review_required
        rule_id = matched_rule.rule_id

    recommended_branch = f"feat/qre-{_slug(normalized)}"
    recommended_pr_title = _title(normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "next_action": normalized,
        "original_next_action": str(next_action or ""),
        "rule_id": rule_id,
        "matched_pattern": matched_pattern,
        "action_class": action_class,
        "safety_class": safety_class,
        "execution_allowed": False,
        "ade_build_allowed": ade_build_allowed,
        "safe_for_ade_build": ade_build_allowed,
        "human_review_required": human_review_required,
        "recommended_branch": recommended_branch,
        "recommended_pr_title": recommended_pr_title,
        "implementation_scope": _scope_for(normalized, action_class),
        "blocked_authorities": list(BLOCKED_AUTHORITIES),
        "forbidden_actions": list(BLOCKED_AUTHORITIES),
        "acceptance_commands": list(ACCEPTANCE_COMMANDS),
        "operator_approval": {
            "required": human_review_required,
            "approval_status": "not_requested",
            "approval_scope": "planning_only_not_execution",
        },
    }


__all__ = [
    "ACCEPTANCE_COMMANDS",
    "BLOCKED_AUTHORITIES",
    "REPORT_KIND",
    "RULES",
    "SCHEMA_VERSION",
    "classify_next_action",
]
