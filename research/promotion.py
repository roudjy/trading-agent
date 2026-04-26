"""Pure decision functions for candidate promotion.

Consumes evaluation outputs and statistical defensibility data.
Classifies each strategy run as rejected / needs_investigation / candidate.
No side effects, no IO, no randomness.
"""

import json
from typing import Any

STATUS_REJECTED = "rejected"
STATUS_NEEDS_INVESTIGATION = "needs_investigation"
STATUS_CANDIDATE = "candidate"

DEFAULT_PROMOTION_CONFIG: dict[str, Any] = {
    "min_oos_sharpe": 0.3,
    "max_oos_drawdown": 0.35,
    "min_psr": 0.90,
    "min_dsr_canonical": 0.0,
    "noise_warning_escalates": True,
    "require_leakage_checks_ok": True,
    "require_goedgekeurd": False,
    "min_oos_trades": 10,
}


def normalize_promotion_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Merge user overrides with defaults. Unknown keys are ignored."""
    base = dict(DEFAULT_PROMOTION_CONFIG)
    if config:
        for key in DEFAULT_PROMOTION_CONFIG:
            if key in config:
                base[key] = config[key]
    return base


def build_strategy_id(
    strategy_name: str,
    asset: str,
    interval: str,
    selected_params: dict,
) -> str:
    """Deterministic composite key for a strategy run."""
    params_json = json.dumps(selected_params, sort_keys=True)
    return f"{strategy_name}|{asset}|{interval}|{params_json}"


def classify_candidate(
    oos_summary: dict[str, Any],
    leakage_checks_ok: bool,
    defensibility: dict[str, Any] | None,
    config: dict[str, Any],
    pass_kind: str | None = None,
) -> tuple[str, dict[str, list[str]]]:
    """Classify a single strategy run.

    Returns (status, reasoning) where reasoning has keys
    'passed', 'failed', 'escalated'.

    v3.15.7: ``pass_kind`` is the screening-layer pass_kind for the
    candidate (None / "standard" / "promotion_grade" /
    "exploratory"). When ``pass_kind == "exploratory"`` the
    candidate is downgraded to ``STATUS_NEEDS_INVESTIGATION`` with
    a single escalated reason
    ``exploratory_pass_requires_promotion_grade_confirmation`` —
    exploratory passes must NOT auto-promote to candidate / paper.
    All other ``pass_kind`` values follow the byte-identical
    pre-v3.15.7 classification path below; existing positional
    4-arg call sites keep working thanks to the default.
    """
    if pass_kind == "exploratory":
        return STATUS_NEEDS_INVESTIGATION, {
            "passed": [],
            "failed": [],
            "escalated": ["exploratory_pass_requires_promotion_grade_confirmation"],
        }

    failed: list[str] = []
    escalated: list[str] = []
    passed: list[str] = []

    # --- Rejection rules (hard gates) ---
    _check_rejection_rules(oos_summary, leakage_checks_ok, config, failed, passed)

    if failed:
        return STATUS_REJECTED, {"passed": passed, "failed": failed, "escalated": []}

    # --- Escalation rules (soft gates) ---
    _check_escalation_rules(defensibility, config, escalated, passed)

    if escalated:
        return STATUS_NEEDS_INVESTIGATION, {"passed": passed, "failed": [], "escalated": escalated}

    return STATUS_CANDIDATE, {"passed": passed, "failed": [], "escalated": []}


def _check_rejection_rules(
    oos_summary: dict[str, Any],
    leakage_checks_ok: bool,
    config: dict[str, Any],
    failed: list[str],
    passed: list[str],
) -> None:
    """Evaluate hard rejection rules."""
    oos_sharpe = float(oos_summary.get("sharpe", 0.0))
    if oos_sharpe < config["min_oos_sharpe"]:
        failed.append("oos_sharpe_below_threshold")
    else:
        passed.append("oos_sharpe_above_threshold")

    oos_dd = float(oos_summary.get("max_drawdown", 1.0))
    if oos_dd > config["max_oos_drawdown"]:
        failed.append("drawdown_above_limit")
    else:
        passed.append("drawdown_below_limit")

    if config["require_leakage_checks_ok"] and not leakage_checks_ok:
        failed.append("leakage_detected")
    elif config["require_leakage_checks_ok"]:
        passed.append("leakage_checks_ok")

    oos_trades = int(oos_summary.get("totaal_trades", 0))
    if oos_trades < config["min_oos_trades"]:
        failed.append("insufficient_trades")
    else:
        passed.append("sufficient_trades")

    if config["require_goedgekeurd"] and not oos_summary.get("goedgekeurd", False):
        failed.append("goedgekeurd_required_but_false")
    elif config["require_goedgekeurd"]:
        passed.append("goedgekeurd_passed")


def _check_escalation_rules(
    defensibility: dict[str, Any] | None,
    config: dict[str, Any],
    escalated: list[str],
    passed: list[str],
) -> None:
    """Evaluate soft escalation rules."""
    if defensibility is None:
        escalated.append("defensibility_data_missing")
        return

    noise_warning = defensibility.get("noise_warning", {})
    if config["noise_warning_escalates"] and noise_warning.get("is_likely_noise", False):
        escalated.append("noise_warning_fired")
    elif config["noise_warning_escalates"]:
        passed.append("noise_warning_clear")

    psr = defensibility.get("psr")
    if psr is None:
        escalated.append("psr_unavailable")
    elif psr < config["min_psr"]:
        escalated.append("psr_below_threshold")
    else:
        passed.append("psr_above_threshold")

    dsr = defensibility.get("dsr_canonical")
    if dsr is None:
        escalated.append("dsr_unavailable")
    elif dsr < config["min_dsr_canonical"]:
        escalated.append("dsr_canonical_below_threshold")
    else:
        passed.append("dsr_canonical_above_threshold")

    bootstrap_ci = defensibility.get("bootstrap_ci", {})
    sharpe_ci = bootstrap_ci.get("sharpe", {})
    ci_low = sharpe_ci.get("low")
    if ci_low is None:
        escalated.append("bootstrap_sharpe_ci_unavailable")
    elif ci_low <= 0.0:
        escalated.append("bootstrap_sharpe_ci_includes_zero")
    else:
        passed.append("bootstrap_sharpe_ci_positive")
