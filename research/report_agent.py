"""v3.10 post-run analysis / report agent.

Reads run artifacts (frozen `research_latest.json`, sidecars, run-meta)
and composes `research/report_latest.md` + `research/report_latest.json`.
Existing reporting modules (falsification / promotion / integrity /
regime / statistical / empty-run) are reused — this agent composes, it
does not re-derive strategy or statistical logic.

Layer-safety:
- Reads only from `research/*.json` + `research/*.csv` + `research/run_meta_latest.v1.json`.
- Produces a NEW adjacent artifact (markdown + json). No mutations to the
  frozen public contract.
- Best-effort: the caller wraps this in try/except so a report failure
  never fails an otherwise-successful run (see `run_research.py`).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.registry import STRATEGIES
from research.report_candidate_diagnostics import build_candidate_diagnostics
from research.run_meta import RUN_META_PATH, read_run_meta_sidecar

REPORT_MARKDOWN_PATH = Path("research/report_latest.md")
REPORT_JSON_PATH = Path("research/report_latest.json")
REPORT_SCHEMA_VERSION = "1.1"

_RESEARCH_LATEST_JSON = Path("research/research_latest.json")
_FALSIFICATION_SIDECAR = Path("research/falsification_gates_latest.v1.json")
_INTEGRITY_SIDECAR = Path("research/integrity_report_latest.v1.json")
_EMPTY_RUN_SIDECAR = Path("research/empty_run_diagnostics_latest.v1.json")
_CANDIDATE_REGISTRY_SIDECAR = Path("research/candidate_registry_latest.v1.json")
_DEFENSIBILITY_SIDECAR = Path("research/statistical_defensibility_latest.v1.json")
_REGIME_SIDECAR = Path("research/regime_diagnostics_latest.v1.json")
_RUN_FILTER_SUMMARY_SIDECAR = Path("research/run_filter_summary_latest.v1.json")
_RUN_SCREENING_CANDIDATES_SIDECAR = Path("research/run_screening_candidates_latest.v1.json")
_COST_SENSITIVITY_SIDECAR = Path("research/cost_sensitivity_latest.v1.json")
_REGISTRY_V2_SIDECAR = Path("research/candidate_registry_latest.v2.json")
_REGIME_INTELLIGENCE_SIDECAR = Path("research/regime_intelligence_latest.v1.json")
_REGIME_OVERLAY_SIDECAR = Path("research/candidate_registry_regime_overlay_latest.v1.json")
_SLEEVE_REGISTRY_SIDECAR = Path("research/sleeve_registry_latest.v1.json")
_PORTFOLIO_DIAGNOSTICS_SIDECAR = Path("research/portfolio_diagnostics_latest.v1.json")
_PAPER_LEDGER_SIDECAR = Path("research/paper_ledger_latest.v1.json")
_PAPER_DIVERGENCE_SIDECAR = Path("research/paper_divergence_latest.v1.json")
_PAPER_READINESS_SIDECAR = Path("research/paper_readiness_latest.v1.json")


VERDICT_PROMOTED = "promoted"
VERDICT_CANDIDATES_NO_PROMOTION = "candidates_no_promotion"
VERDICT_NIETS_BRUIKBAARS = "niets_bruikbaars_vandaag"


def _enrich_with_v3_12_fields(
    per_candidate: list[dict[str, Any]],
    registry_v2: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Additively merge v3.12 fields into per_candidate_diagnostics entries.

    The v3.11 shape of each per_candidate entry is preserved; only new
    keys (``lifecycle_status``, ``legacy_verdict``,
    ``observed_reason_codes``, ``taxonomy_rejection_codes``, ``scores``)
    are attached when a matching v2 entry is available. Missing
    entries simply do not gain the v3.12 fields — consumers check
    with ``.get()``.
    """
    if not per_candidate or not registry_v2:
        return per_candidate

    v2_index = {
        entry.get("candidate_id"): entry
        for entry in registry_v2.get("entries") or []
        if isinstance(entry, dict)
    }
    if not v2_index:
        return per_candidate

    enriched: list[dict[str, Any]] = []
    for entry in per_candidate:
        strategy_id = entry.get("strategy_id")
        v2_entry = v2_index.get(strategy_id)
        if v2_entry is None:
            enriched.append(entry)
            continue
        merged = dict(entry)
        merged["lifecycle_status"] = v2_entry.get("lifecycle_status")
        merged["legacy_verdict"] = v2_entry.get("legacy_verdict")
        merged["observed_reason_codes"] = v2_entry.get("observed_reason_codes") or []
        merged["taxonomy_rejection_codes"] = (
            v2_entry.get("taxonomy_rejection_codes") or []
        )
        merged["scores"] = v2_entry.get("scores")
        enriched.append(merged)
    return enriched


def _enrich_with_regime_fields(
    per_candidate: list[dict[str, Any]],
    regime_intelligence: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Additively merge v3.13 regime-intelligence fields into per-candidate diagnostics.

    Parallel to :func:`_enrich_with_v3_12_fields`; adds only new
    optional keys so existing v3.10/v3.11/v3.12 consumers stay
    unaffected. Missing intelligence entries are a no-op.
    """
    if not per_candidate or not regime_intelligence:
        return per_candidate

    intel_index = {
        entry.get("candidate_id"): entry
        for entry in regime_intelligence.get("entries") or []
        if isinstance(entry, dict)
    }
    if not intel_index:
        return per_candidate

    enriched: list[dict[str, Any]] = []
    for entry in per_candidate:
        strategy_id = entry.get("strategy_id")
        intel_entry = intel_index.get(strategy_id)
        if intel_entry is None:
            enriched.append(entry)
            continue
        merged = dict(entry)
        merged["regime_assessment_status"] = intel_entry.get("regime_assessment_status")
        merged["regime_dependency_scores"] = intel_entry.get("regime_dependency_scores")
        experiments = intel_entry.get("regime_gating_experiments") or []
        merged["regime_gating_summary"] = {
            "rule_ids": [exp.get("rule_id") for exp in experiments],
            "evaluated_count": sum(
                1 for exp in experiments if exp.get("status") == "evaluated"
            ),
        }
        enriched.append(merged)
    return enriched


def _regime_layer_summary(
    regime_intelligence: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Top-level additive summary for the report payload."""
    if not regime_intelligence:
        return None
    summary = regime_intelligence.get("summary") or {}
    return {
        "classifier_version": regime_intelligence.get("classifier_version"),
        "regime_layer_version": regime_intelligence.get("regime_layer_version"),
        "candidates_total": summary.get("candidates_total"),
        "candidates_with_sufficient_evidence": summary.get(
            "candidates_with_sufficient_evidence"
        ),
        "gate_rule_ids": summary.get("gate_rule_ids") or [],
    }


def _portfolio_layer_summary(
    sleeve_registry: dict[str, Any] | None,
    portfolio_diagnostics: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """v3.14 additive summary for the report payload.

    Returns ``None`` when neither sidecar is present so consumers can
    differentiate between "no v3.14 run yet" and "empty portfolio".
    """
    if not sleeve_registry and not portfolio_diagnostics:
        return None
    sleeves = (sleeve_registry or {}).get("sleeves") or []
    memberships = (sleeve_registry or {}).get("memberships") or []
    diagnostics = portfolio_diagnostics or {}
    ewp = diagnostics.get("equal_weight_portfolio") or {}
    return {
        "sleeve_count": int(len(sleeves)),
        "candidate_members_total": int(len(memberships)),
        "diagnostics_layer_version": diagnostics.get("diagnostics_layer_version"),
        "authoritative": bool(diagnostics.get("authoritative", False)),
        "thresholds": diagnostics.get("thresholds") or {},
        "equal_weight_portfolio": {
            "candidate_count": ewp.get("candidate_count"),
            "overlap_days": ewp.get("overlap_days"),
            "insufficient_overlap": ewp.get("insufficient_overlap"),
            "sharpe": ewp.get("sharpe"),
            "sortino": ewp.get("sortino"),
            "max_drawdown": ewp.get("max_drawdown"),
            "calmar": ewp.get("calmar"),
            "annualized_return": ewp.get("annualized_return"),
        },
        "concentration_warning_count": int(
            len(diagnostics.get("concentration_warnings") or [])
        ),
        "intra_sleeve_correlation_warning_count": int(
            len(diagnostics.get("intra_sleeve_correlation_warnings") or [])
        ),
    }


def _paper_layer_summary(
    paper_ledger: dict[str, Any] | None,
    paper_divergence: dict[str, Any] | None,
    paper_readiness: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """v3.15 additive summary for the report payload.

    Returns ``None`` when none of the three v3.15 sidecars are
    present so consumers can differentiate "no v3.15 run yet"
    from "empty paper evidence".
    """
    if not paper_ledger and not paper_divergence and not paper_readiness:
        return None
    ledger = paper_ledger or {}
    divergence = paper_divergence or {}
    readiness = paper_readiness or {}
    return {
        "paper_ledger_version": ledger.get("paper_ledger_version"),
        "paper_divergence_version": divergence.get("paper_divergence_version"),
        "paper_readiness_version": readiness.get("paper_readiness_version"),
        "paper_venues_version": (
            ledger.get("paper_venues_version")
            or divergence.get("paper_venues_version")
        ),
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "ledger_event_counts": ledger.get("overall_event_counts") or {},
        "divergence_severity_counts": (
            divergence.get("severity_counts")
            or {"low": 0, "medium": 0, "high": 0}
        ),
        "readiness_counts": readiness.get("counts") or {},
        "candidate_count": int(len(readiness.get("entries") or [])),
    }




def _candidate_id_asset_hint(candidate_id: Any) -> str | None:
    if not isinstance(candidate_id, str) or not candidate_id:
        return None
    parts = candidate_id.split("|")
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return None


def _paper_readiness_diagnosis_class(
    *,
    status: str | None,
    blocking_reasons: list[str],
    warnings: list[str],
    evidence: dict[str, Any],
) -> str:
    if status == "ready_for_paper_promotion":
        return "ready_candidate_found"
    if "missing_execution_events" in blocking_reasons:
        return "execution_event_coverage_gap"
    if "excessive_divergence" in blocking_reasons:
        return "paper_engine_divergence_gap"
    if "insufficient_oos_days" in blocking_reasons:
        return "insufficient_return_evidence"
    if "no_candidate_returns" in blocking_reasons:
        return "missing_return_evidence"
    if "malformed_return_stream" in blocking_reasons:
        return "malformed_return_evidence"
    if "insufficient_venue_mapping" in blocking_reasons:
        return "venue_mapping_gap"
    if "negative_paper_sharpe" in warnings:
        return "weak_paper_performance_signal"
    if status == "insufficient_evidence":
        return "insufficient_evidence"
    if not evidence:
        return "missing_candidate_evidence"
    return "paper_readiness_blocked_unknown"


def _paper_readiness_next_action_for_diagnosis(diagnosis_class: str) -> str:
    mapping = {
        "ready_candidate_found": "review_ready_candidate_for_operator_shadow_or_paper_followup",
        "execution_event_coverage_gap": "inspect_validated_candidate_execution_event_coverage",
        "paper_engine_divergence_gap": "inspect_paper_engine_divergence_components_before_threshold_or_strategy_changes",
        "insufficient_return_evidence": "collect_more_oos_return_evidence_before_paper_review",
        "missing_return_evidence": "repair_candidate_return_stream_before_paper_review",
        "malformed_return_evidence": "repair_malformed_candidate_return_stream_before_paper_review",
        "venue_mapping_gap": "inspect_venue_mapping_before_paper_review",
        "weak_paper_performance_signal": "keep_candidate_blocked_until_paper_performance_signal_improves",
        "insufficient_evidence": "collect_more_candidate_evidence_before_paper_review",
        "missing_candidate_evidence": "run_or_repair_paper_readiness_sidecar_generation",
    }
    return mapping.get(
        diagnosis_class,
        "inspect_paper_readiness_blockers_before_new_strategy_or_preset_changes",
    )


def _paper_candidate_evidence_score(row: dict[str, Any]) -> tuple[int, int, int, int, int]:
    status = str(row.get("readiness_status") or "")
    blockers = row.get("blocking_reasons") if isinstance(row.get("blocking_reasons"), list) else []

    event_count = int(row.get("paper_ledger_event_count") or 0)
    status_score = 3 if status == "ready_for_paper_promotion" else 0

    # A blocked candidate with real reconstructed paper events is closer to
    # paper readiness than a candidate with low divergence caused by zero events.
    event_presence_score = 1 if event_count > 0 else 0
    event_score = event_count

    divergence_score = 0
    severity = row.get("divergence_severity")
    if severity == "low":
        divergence_score = 2
    elif severity == "medium":
        divergence_score = 1

    obs_score = int(row.get("timestamped_returns_n_obs") or 0)

    # Fewer blockers should win only after evidence coverage and quality.
    blocker_penalty = -len(blockers)
    return (
        status_score,
        event_presence_score,
        event_score,
        divergence_score,
        obs_score + blocker_penalty,
    )


def _paper_readiness_blocker_diagnosis(
    paper_readiness: dict[str, Any] | None,
    paper_ledger: dict[str, Any] | None,
    paper_divergence: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a generic paper-readiness blocker diagnosis.

    This is report-only and does not alter readiness thresholds, strategy
    behavior, preset behavior, campaign queues, or runtime activation.
    """
    if not paper_readiness and not paper_ledger and not paper_divergence:
        return None

    readiness = paper_readiness or {}
    entries = readiness.get("entries") if isinstance(readiness, dict) else []
    if not isinstance(entries, list):
        entries = []

    ledger = paper_ledger or {}
    divergence = paper_divergence or {}

    blocker_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    diagnosis_counts: dict[str, int] = {}
    candidate_rows: list[dict[str, Any]] = []

    ready_count = 0
    blocked_count = 0
    insufficient_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        status = str(entry.get("readiness_status") or "unknown")
        if status == "ready_for_paper_promotion":
            ready_count += 1
        elif status == "blocked":
            blocked_count += 1
        elif status == "insufficient_evidence":
            insufficient_count += 1

        blocking_reasons = list(entry.get("blocking_reasons") or [])
        warnings = list(entry.get("warnings") or [])
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}

        for reason in blocking_reasons:
            blocker_counts[str(reason)] = blocker_counts.get(str(reason), 0) + 1
        for warning in warnings:
            warning_counts[str(warning)] = warning_counts.get(str(warning), 0) + 1

        diagnosis_class = _paper_readiness_diagnosis_class(
            status=status,
            blocking_reasons=[str(reason) for reason in blocking_reasons],
            warnings=[str(warning) for warning in warnings],
            evidence=evidence,
        )
        diagnosis_counts[diagnosis_class] = diagnosis_counts.get(diagnosis_class, 0) + 1

        candidate_rows.append(
            {
                "candidate_id": entry.get("candidate_id"),
                "asset_hint": _candidate_id_asset_hint(entry.get("candidate_id")),
                "asset_type": entry.get("asset_type"),
                "sleeve_id": entry.get("sleeve_id"),
                "readiness_status": status,
                "blocking_reasons": blocking_reasons,
                "warnings": warnings,
                "paper_ledger_event_count": int(evidence.get("paper_ledger_event_count") or 0),
                "timestamped_returns_n_obs": int(evidence.get("timestamped_returns_n_obs") or 0),
                "divergence_severity": evidence.get("divergence_severity"),
                "paper_sharpe_proxy": evidence.get("paper_sharpe_proxy"),
                "diagnosis_class": diagnosis_class,
                "recommended_next_action": _paper_readiness_next_action_for_diagnosis(
                    diagnosis_class
                ),
            }
        )

    if ready_count > 0:
        search_status = "ready_candidate_found"
    elif entries:
        search_status = "no_ready_candidate"
    elif paper_readiness:
        search_status = "insufficient_evidence"
    else:
        search_status = "missing_paper_readiness"

    closest = None
    if candidate_rows:
        closest = max(candidate_rows, key=_paper_candidate_evidence_score)

    dominant_blockers = [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            blocker_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    dominant_diagnoses = [
        {"diagnosis_class": reason, "count": count}
        for reason, count in sorted(
            diagnosis_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    if ready_count > 0:
        recommended = "review_ready_candidate_for_operator_shadow_or_paper_followup"
    elif closest:
        recommended = closest["recommended_next_action"]
    elif not paper_readiness:
        recommended = "run_or_repair_paper_readiness_sidecar_generation"
    else:
        recommended = "inspect_paper_readiness_blockers_before_new_strategy_or_preset_changes"

    return {
        "schema_version": "paper_readiness_blocker_diagnosis.v1",
        "advisory_only": True,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "paper_runtime_enabled": False,
        "shadow_runtime_enabled": False,
        "paper_candidate_search_status": search_status,
        "candidate_count": len(candidate_rows),
        "ready_candidate_count": ready_count,
        "blocked_candidate_count": blocked_count,
        "insufficient_evidence_candidate_count": insufficient_count,
        "dominant_blockers": dominant_blockers,
        "warning_counts": dict(sorted(warning_counts.items())),
        "diagnosis_counts": dict(sorted(diagnosis_counts.items())),
        "dominant_diagnoses": dominant_diagnoses,
        "closest_candidate": closest,
        "recommended_next_action": recommended,
        "ledger_event_counts": ledger.get("overall_event_counts") or {},
        "divergence_severity_counts": divergence.get("severity_counts") or {},
        "candidates": candidate_rows,
    }




def _infer_regular_asset_scope_from_report(
    *,
    preset_name: Any,
    diagnosis: dict[str, Any] | None,
) -> bool:
    preset = str(preset_name or "").lower()
    if any(token in preset for token in ("equities", "equity", "stocks", "stock")):
        return True
    if any(token in preset for token in ("crypto", "btc", "eth")):
        return False

    rows = (diagnosis or {}).get("candidates") if isinstance(diagnosis, dict) else []
    if not isinstance(rows, list) or not rows:
        return False
    asset_types = {
        str(row.get("asset_type") or "").lower()
        for row in rows
        if isinstance(row, dict)
    }
    return bool(asset_types) and asset_types.issubset({"equity", "stock"})


def _next_research_action_from_paper_diagnosis(
    *,
    preset_name: Any,
    paper_diagnosis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Translate paper-readiness diagnosis into a bounded next action plan.

    This is an advisory/report-only gate. It can recommend diagnostics or
    operator-gated proposal review, but it never mutates presets, campaigns,
    strategies, paper runtime, shadow runtime, or live state.
    """
    if not paper_diagnosis:
        return None

    search_status = str(
        paper_diagnosis.get("paper_candidate_search_status") or "unknown"
    )
    regular_asset_scope = _infer_regular_asset_scope_from_report(
        preset_name=preset_name,
        diagnosis=paper_diagnosis,
    )
    dominant_diagnoses = [
        str(row.get("diagnosis_class"))
        for row in (paper_diagnosis.get("dominant_diagnoses") or [])
        if isinstance(row, dict) and row.get("diagnosis_class")
    ]
    dominant_blockers = [
        str(row.get("reason"))
        for row in (paper_diagnosis.get("dominant_blockers") or [])
        if isinstance(row, dict) and row.get("reason")
    ]
    closest = paper_diagnosis.get("closest_candidate") or {}
    closest_diagnosis = (
        str(closest.get("diagnosis_class") or "") if isinstance(closest, dict) else ""
    )

    if search_status == "ready_candidate_found":
        action_id = "review_ready_paper_candidate"
        proposal_gate_status = "not_needed_ready_candidate_exists"
        action_mode = "operator_review"
        reason_codes = ["paper_ready_candidate_exists"]
        bounded_next_step = "review_ready_candidate_for_operator_shadow_or_paper_followup"
    elif closest_diagnosis == "paper_engine_divergence_gap":
        action_id = "inspect_paper_engine_divergence"
        proposal_gate_status = "blocked_until_divergence_explained"
        action_mode = "automatic_diagnostic"
        reason_codes = ["closest_candidate_has_execution_events_but_high_divergence"]
        bounded_next_step = (
            "inspect_paper_engine_divergence_components_before_new_hypothesis_or_preset"
        )
    elif "execution_event_coverage_gap" in dominant_diagnoses:
        action_id = "inspect_execution_event_coverage"
        proposal_gate_status = "blocked_until_execution_coverage_explained"
        action_mode = "automatic_diagnostic"
        reason_codes = ["dominant_blocker_missing_execution_events"]
        bounded_next_step = (
            "inspect_validated_candidates_without_reconstructed_execution_events"
        )
    elif search_status == "no_ready_candidate":
        action_id = "diagnose_no_paper_candidate"
        proposal_gate_status = "blocked_pending_blocker_attribution"
        action_mode = "automatic_diagnostic"
        reason_codes = ["no_ready_paper_candidate"]
        bounded_next_step = "diagnose_paper_readiness_blockers_before_more_preset_runs"
    elif search_status == "missing_paper_readiness":
        action_id = "repair_paper_readiness_artifacts"
        proposal_gate_status = "blocked_missing_readiness_artifact"
        action_mode = "automatic_diagnostic"
        reason_codes = ["paper_readiness_artifact_missing"]
        bounded_next_step = "run_or_repair_paper_readiness_sidecar_generation"
    else:
        action_id = "inspect_paper_candidate_search_state"
        proposal_gate_status = "blocked_unknown_paper_candidate_state"
        action_mode = "automatic_diagnostic"
        reason_codes = ["paper_candidate_search_state_unknown"]
        bounded_next_step = "inspect_latest_paper_candidate_search_artifacts"

    hypothesis_preset_proposal_gate = {
        "gate_status": proposal_gate_status,
        "regular_asset_scope": regular_asset_scope,
        "automatic_preset_mutation_allowed": False,
        "automatic_strategy_mutation_allowed": False,
        "automatic_campaign_queue_mutation_allowed": False,
        "operator_approval_required_for_new_hypothesis_or_preset": True,
        "allowed_after": [
            "paper_readiness_blockers_explained",
            "execution_event_coverage_or_divergence_diagnosed",
            "operator_approves_bounded_hypothesis_or_preset_review",
        ],
    }

    if regular_asset_scope and proposal_gate_status.startswith("blocked"):
        hypothesis_preset_proposal_gate["regular_asset_research_direction"] = (
            "do_not_try_more_regular_asset_presets_blindly"
        )
    elif regular_asset_scope:
        hypothesis_preset_proposal_gate["regular_asset_research_direction"] = (
            "operator_review_ready_candidate_before_new_regular_asset_preset"
        )

    return {
        "schema_version": "no_paper_candidate_next_action_plan.v1",
        "advisory_only": True,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "paper_runtime_enabled": False,
        "shadow_runtime_enabled": False,
        "preset_name": preset_name,
        "paper_candidate_search_status": search_status,
        "regular_asset_scope": regular_asset_scope,
        "dominant_blockers": dominant_blockers,
        "dominant_diagnoses": dominant_diagnoses,
        "closest_candidate": closest,
        "recommended_action_id": action_id,
        "recommended_action_mode": action_mode,
        "reason_codes": reason_codes,
        "bounded_next_step": bounded_next_step,
        "hypothesis_preset_proposal_gate": hypothesis_preset_proposal_gate,
        "forbidden_actions": [
            "blind_regular_asset_preset_search",
            "automatic_strategy_change",
            "automatic_preset_change",
            "automatic_campaign_queue_mutation",
            "paper_runtime_activation",
            "shadow_runtime_activation",
            "live_trading",
        ],
    }




def _safe_float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _paper_engine_divergence_driver(
    *,
    final_equity_delta_bps: float | None,
    fee_drag_delta_vs_baseline: float | None,
    slippage_drag: float | None,
    n_full_fills: int,
) -> str:
    if final_equity_delta_bps is None:
        return "missing_metrics_delta"
    if n_full_fills <= 0:
        return "no_full_fills"

    fee_abs = abs(fee_drag_delta_vs_baseline or 0.0)
    slip_abs = abs(slippage_drag or 0.0)

    if fee_abs == 0.0 and slip_abs == 0.0:
        return "metrics_delta_without_cost_component_breakdown"
    if slip_abs > fee_abs * 1.5:
        return "slippage_drag_dominant"
    if fee_abs > slip_abs * 1.5:
        return "fee_model_delta_dominant"
    return "mixed_fee_and_slippage_effects"


def _paper_engine_divergence_next_action(driver: str) -> str:
    mapping = {
        "missing_metrics_delta": "repair_paper_divergence_metrics_before_threshold_review",
        "no_full_fills": "inspect_execution_event_coverage_before_divergence_review",
        "slippage_drag_dominant": "inspect_venue_slippage_assumptions_before_strategy_or_threshold_changes",
        "fee_model_delta_dominant": "inspect_engine_vs_venue_fee_model_before_strategy_or_threshold_changes",
        "mixed_fee_and_slippage_effects": "inspect_combined_fee_and_slippage_model_before_strategy_or_threshold_changes",
        "metrics_delta_without_cost_component_breakdown": "inspect_paper_divergence_payload_completeness",
    }
    return mapping.get(driver, "inspect_paper_engine_divergence_components")


def _paper_engine_divergence_component_diagnosis(
    paper_divergence: dict[str, Any] | None,
    paper_diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Explain paper-engine divergence components using existing sidecar fields.

    Report-only: does not change divergence math, readiness thresholds,
    strategy behavior, presets, campaign queues, or runtime activation.
    """
    if not paper_divergence:
        return None

    per_candidate = paper_divergence.get("per_candidate")
    if not isinstance(per_candidate, list):
        per_candidate = []

    closest_candidate_id = None
    if isinstance(paper_diagnosis, dict):
        closest = paper_diagnosis.get("closest_candidate") or {}
        if isinstance(closest, dict):
            closest_candidate_id = closest.get("candidate_id")

    rows: list[dict[str, Any]] = []
    driver_counts: dict[str, int] = {}
    high_count = 0

    for entry in per_candidate:
        if not isinstance(entry, dict):
            continue

        metrics = entry.get("metrics_delta") if isinstance(entry.get("metrics_delta"), dict) else {}
        costs = entry.get("venue_cost_delta") if isinstance(entry.get("venue_cost_delta"), dict) else {}

        severity = entry.get("divergence_severity")
        final_bps = _safe_float_or_none(metrics.get("final_equity_delta_bps"))
        cumulative_adjustment = _safe_float_or_none(metrics.get("cumulative_adjustment"))
        sharpe_proxy_delta = _safe_float_or_none(metrics.get("sharpe_proxy_delta"))

        venue_fee = _safe_float_or_none(costs.get("venue_fee_per_side"))
        venue_slippage = _safe_float_or_none(costs.get("venue_slippage_bps"))
        per_fill_adjustment = _safe_float_or_none(costs.get("per_fill_adjustment"))
        fee_drag_venue = _safe_float_or_none(costs.get("fee_drag_venue"))
        fee_drag_engine = _safe_float_or_none(costs.get("fee_drag_engine_baseline"))
        fee_delta = _safe_float_or_none(costs.get("fee_drag_delta_vs_baseline"))
        slippage_drag = _safe_float_or_none(costs.get("slippage_drag"))

        n_full_fills = int(entry.get("n_full_fills") or 0)

        driver = _paper_engine_divergence_driver(
            final_equity_delta_bps=final_bps,
            fee_drag_delta_vs_baseline=fee_delta,
            slippage_drag=slippage_drag,
            n_full_fills=n_full_fills,
        )
        driver_counts[driver] = driver_counts.get(driver, 0) + 1
        if severity == "high":
            high_count += 1

        rows.append(
            {
                "candidate_id": entry.get("candidate_id"),
                "asset_hint": _candidate_id_asset_hint(entry.get("candidate_id")),
                "asset_type": entry.get("asset_type"),
                "sleeve_id": entry.get("sleeve_id"),
                "venue": entry.get("venue"),
                "included_in_portfolio": entry.get("included_in_portfolio"),
                "reason_excluded": entry.get("reason_excluded"),
                "divergence_severity": severity,
                "n_full_fills": n_full_fills,
                "metrics_delta": {
                    "final_equity_delta_bps": final_bps,
                    "cumulative_adjustment": cumulative_adjustment,
                    "sharpe_proxy_delta": sharpe_proxy_delta,
                },
                "venue_cost_delta": {
                    "venue_fee_per_side": venue_fee,
                    "venue_slippage_bps": venue_slippage,
                    "per_fill_adjustment": per_fill_adjustment,
                    "fee_drag_venue": fee_drag_venue,
                    "fee_drag_engine_baseline": fee_drag_engine,
                    "fee_drag_delta_vs_baseline": fee_delta,
                    "slippage_drag": slippage_drag,
                },
                "divergence_component_driver": driver,
                "recommended_next_action": _paper_engine_divergence_next_action(driver),
                "is_closest_paper_candidate": (
                    closest_candidate_id is not None
                    and entry.get("candidate_id") == closest_candidate_id
                ),
            }
        )

    if not rows:
        return {
            "schema_version": "paper_engine_divergence_component_diagnosis.v1",
            "advisory_only": True,
            "authoritative": False,
            "diagnostic_only": True,
            "live_eligible": False,
            "paper_runtime_enabled": False,
            "shadow_runtime_enabled": False,
            "candidate_count": 0,
            "high_divergence_candidate_count": 0,
            "component_driver_counts": {},
            "closest_candidate_component_diagnosis": None,
            "recommended_next_action": "run_or_repair_paper_divergence_sidecar_generation",
            "candidates": [],
        }

    closest_row = None
    for row in rows:
        if row.get("is_closest_paper_candidate"):
            closest_row = row
            break

    if closest_row is None:
        # Prefer high-divergence rows, then rows with largest absolute equity delta.
        closest_row = max(
            rows,
            key=lambda row: (
                1 if row.get("divergence_severity") == "high" else 0,
                abs((row.get("metrics_delta") or {}).get("final_equity_delta_bps") or 0.0),
                int(row.get("n_full_fills") or 0),
            ),
        )

    return {
        "schema_version": "paper_engine_divergence_component_diagnosis.v1",
        "advisory_only": True,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "paper_runtime_enabled": False,
        "shadow_runtime_enabled": False,
        "candidate_count": len(rows),
        "high_divergence_candidate_count": high_count,
        "component_driver_counts": dict(sorted(driver_counts.items())),
        "severity_counts": paper_divergence.get("severity_counts") or {},
        "closest_candidate_component_diagnosis": closest_row,
        "recommended_next_action": closest_row.get("recommended_next_action"),
        "candidates": rows,
    }




_RESEARCH_ACTION_FORBIDDEN_ACTIONS: list[str] = [
    "automatic_strategy_change",
    "automatic_preset_change",
    "automatic_campaign_queue_mutation",
    "threshold_change",
    "readiness_threshold_change",
    "paper_runtime_activation",
    "shadow_runtime_activation",
    "live_trading",
]


def _research_action_queue_item(
    *,
    action_id: str,
    source_section: str,
    target_candidate_id: Any = None,
    priority: str = "medium",
    reason_codes: list[str] | None = None,
    bounded_next_step: str | None = None,
    scope: str = "report_only",
    operator_approval_required: bool = False,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable advisory research action queue item.

    This does not enqueue, execute, mutate campaigns, mutate presets, mutate
    strategies, or activate paper/shadow/live runtime.
    """
    return {
        "schema_version": "research_action_queue_item.v1",
        "advisory_only": True,
        "authoritative": False,
        "diagnostic_only": True,
        "queue_emitter_only": True,
        "execution_enabled": False,
        "live_eligible": False,
        "paper_runtime_enabled": False,
        "shadow_runtime_enabled": False,
        "action_id": action_id,
        "queue_item_type": action_id,
        "source_section": source_section,
        "target_candidate_id": target_candidate_id,
        "priority": priority,
        "scope": scope,
        "operator_approval_required": operator_approval_required,
        "bounded_next_step": bounded_next_step or action_id,
        "reason_codes": list(reason_codes or []),
        "forbidden_actions": list(_RESEARCH_ACTION_FORBIDDEN_ACTIONS),
        "evidence": dict(evidence or {}),
    }


def _build_research_action_queue_items(
    *,
    paper_readiness_diagnosis: dict[str, Any] | None = None,
    paper_engine_divergence_diagnosis: dict[str, Any] | None = None,
    no_paper_candidate_next_action_plan: dict[str, Any] | None = None,
    candidate_shadow_readiness_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Emit advisory next-action queue items from report diagnostics.

    The output is machine-readable intent only. It is not a persisted queue,
    not an ADE command, and not a campaign mutation.
    """
    items: list[dict[str, Any]] = []

    if isinstance(paper_engine_divergence_diagnosis, dict):
        closest = (
            paper_engine_divergence_diagnosis.get(
                "closest_candidate_component_diagnosis"
            )
            or {}
        )
        action = paper_engine_divergence_diagnosis.get("recommended_next_action")
        if action:
            items.append(
                _research_action_queue_item(
                    action_id=str(action),
                    source_section="paper_engine_divergence_component_diagnosis",
                    target_candidate_id=closest.get("candidate_id")
                    if isinstance(closest, dict)
                    else None,
                    priority="high"
                    if paper_engine_divergence_diagnosis.get(
                        "high_divergence_candidate_count"
                    )
                    else "medium",
                    reason_codes=[
                        str(closest.get("divergence_component_driver"))
                    ]
                    if isinstance(closest, dict)
                    and closest.get("divergence_component_driver")
                    else [],
                    bounded_next_step=str(action),
                    scope="report_only",
                    operator_approval_required=False,
                    evidence={
                        "divergence_severity": closest.get("divergence_severity")
                        if isinstance(closest, dict)
                        else None,
                        "n_full_fills": closest.get("n_full_fills")
                        if isinstance(closest, dict)
                        else None,
                        "metrics_delta": closest.get("metrics_delta")
                        if isinstance(closest, dict)
                        else None,
                        "venue_cost_delta": closest.get("venue_cost_delta")
                        if isinstance(closest, dict)
                        else None,
                    },
                )
            )

    if isinstance(no_paper_candidate_next_action_plan, dict):
        action = no_paper_candidate_next_action_plan.get("bounded_next_step")
        closest = no_paper_candidate_next_action_plan.get("closest_candidate") or {}
        if action:
            items.append(
                _research_action_queue_item(
                    action_id=str(
                        no_paper_candidate_next_action_plan.get(
                            "recommended_action_id"
                        )
                        or action
                    ),
                    source_section="no_paper_candidate_next_action_plan",
                    target_candidate_id=closest.get("candidate_id")
                    if isinstance(closest, dict)
                    else None,
                    priority="high"
                    if no_paper_candidate_next_action_plan.get(
                        "paper_candidate_search_status"
                    )
                    == "no_ready_candidate"
                    else "medium",
                    reason_codes=[
                        str(reason)
                        for reason in (
                            no_paper_candidate_next_action_plan.get(
                                "reason_codes"
                            )
                            or []
                        )
                    ],
                    bounded_next_step=str(action),
                    scope="report_only",
                    operator_approval_required=False,
                    evidence={
                        "regular_asset_scope": no_paper_candidate_next_action_plan.get(
                            "regular_asset_scope"
                        ),
                        "paper_candidate_search_status": no_paper_candidate_next_action_plan.get(
                            "paper_candidate_search_status"
                        ),
                        "hypothesis_preset_proposal_gate": no_paper_candidate_next_action_plan.get(
                            "hypothesis_preset_proposal_gate"
                        ),
                    },
                )
            )

    if isinstance(paper_readiness_diagnosis, dict):
        status = paper_readiness_diagnosis.get("paper_candidate_search_status")
        if status == "missing_paper_readiness":
            items.append(
                _research_action_queue_item(
                    action_id="run_or_repair_paper_readiness_sidecar_generation",
                    source_section="paper_readiness_blocker_diagnosis",
                    priority="high",
                    reason_codes=["paper_readiness_artifact_missing"],
                    bounded_next_step="run_or_repair_paper_readiness_sidecar_generation",
                    operator_approval_required=False,
                    evidence={"paper_candidate_search_status": status},
                )
            )

    if isinstance(candidate_shadow_readiness_report, dict):
        readiness = candidate_shadow_readiness_report.get("readiness_status")
        if readiness == "ready_for_operator_shadow_review":
            items.append(
                _research_action_queue_item(
                    action_id="operator_review_candidate_shadow_readiness",
                    source_section="candidate_shadow_readiness_report",
                    priority="high",
                    reason_codes=["candidate_shadow_readiness_ready"],
                    bounded_next_step="operator_review_candidate_shadow_readiness",
                    operator_approval_required=True,
                    evidence={
                        "paper_ready_candidate_count": candidate_shadow_readiness_report.get(
                            "paper_ready_candidate_count"
                        ),
                        "operator_go_required": candidate_shadow_readiness_report.get(
                            "operator_go_required"
                        ),
                    },
                )
            )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            str(item.get("action_id")),
            str(item.get("source_section")),
            str(item.get("target_candidate_id")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped



def _candidate_shadow_readiness_report(
    paper_readiness: dict[str, Any] | None,
    exit_quality_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build a report-only candidate shadow-readiness surface.

    This is deliberately not a runtime gate. It combines existing paper
    readiness evidence with exit-quality diagnostics so the operator can see
    whether candidates are even worth considering for a future shadow-review
    lane. Missing evidence fails closed. Shadow/paper runtime flags stay off.
    """
    if not paper_readiness and not exit_quality_rows:
        return None

    readiness = paper_readiness or {}
    entries = readiness.get("entries") if isinstance(readiness, dict) else []
    if not isinstance(entries, list):
        entries = []

    quality_rows = exit_quality_rows if isinstance(exit_quality_rows, list) else []

    ready_count = 0
    blocked_count = 0
    insufficient_count = 0
    candidate_summaries: list[dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = entry.get("readiness_status")
        if status == "ready_for_paper_promotion":
            ready_count += 1
        elif status == "blocked":
            blocked_count += 1
        elif status == "insufficient_evidence":
            insufficient_count += 1

        candidate_summaries.append(
            {
                "candidate_id": entry.get("candidate_id"),
                "paper_readiness_status": status,
                "blocking_reasons": list(entry.get("blocking_reasons") or []),
                "warnings": list(entry.get("warnings") or []),
                "eligible_for_operator_shadow_review": (
                    status == "ready_for_paper_promotion"
                ),
            }
        )

    quality_disagreement_count = 0
    late_or_choppy_candidate_count = 0
    risk_exit_candidate_count = 0
    unknown_exit_candidate_count = 0
    boundary_exit_candidate_count = 0

    for row in quality_rows:
        if not isinstance(row, dict):
            continue
        audit = row.get("best_sample_exit_quality_audit") or {}
        if bool(audit.get("exit_quality_disagreement")):
            quality_disagreement_count += 1
        counts = row.get("exit_health_counts") or {}
        if int(counts.get("late_or_choppy_exit", 0) or 0) > 0:
            late_or_choppy_candidate_count += 1
        if int(counts.get("risk_exit", 0) or 0) > 0:
            risk_exit_candidate_count += 1
        if int(counts.get("unknown_exit", 0) or 0) > 0:
            unknown_exit_candidate_count += 1
        if int(counts.get("boundary_exit", 0) or 0) > 0:
            boundary_exit_candidate_count += 1

    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if not readiness or not entries:
        blocking_reasons.append("paper_readiness_missing")
    if entries and ready_count == 0:
        blocking_reasons.append("no_paper_ready_candidates")
    if blocked_count:
        blocking_reasons.append("paper_readiness_blocked_candidates_present")
    if not quality_rows:
        blocking_reasons.append("exit_quality_missing")
    if quality_disagreement_count:
        warnings.append("exit_quality_best_sample_disagreement_present")
    if late_or_choppy_candidate_count:
        warnings.append("late_or_choppy_exits_present")
    if risk_exit_candidate_count:
        warnings.append("risk_exits_present")
    if unknown_exit_candidate_count:
        warnings.append("unknown_exits_present")
    if boundary_exit_candidate_count:
        warnings.append("boundary_exits_present")

    if blocking_reasons:
        readiness_status = "blocked"
    elif ready_count == 0 or quality_disagreement_count:
        readiness_status = "insufficient_evidence"
    else:
        readiness_status = "ready_for_operator_shadow_review"

    return {
        "schema_version": "candidate_shadow_readiness_report.v1",
        "advisory_only": True,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "shadow_runtime_enabled": False,
        "paper_runtime_enabled": False,
        "operator_go_required": True,
        "readiness_status": readiness_status,
        "eligible_for_operator_shadow_review": (
            readiness_status == "ready_for_operator_shadow_review"
        ),
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "candidate_count": len(candidate_summaries),
        "paper_ready_candidate_count": ready_count,
        "paper_blocked_candidate_count": blocked_count,
        "paper_insufficient_evidence_candidate_count": insufficient_count,
        "exit_quality_candidate_count": len(quality_rows),
        "exit_quality_disagreement_count": quality_disagreement_count,
        "late_or_choppy_candidate_count": late_or_choppy_candidate_count,
        "risk_exit_candidate_count": risk_exit_candidate_count,
        "unknown_exit_candidate_count": unknown_exit_candidate_count,
        "boundary_exit_candidate_count": boundary_exit_candidate_count,
        "candidates": candidate_summaries,
    }



def _lifecycle_breakdown(
    per_candidate: list[dict[str, Any]],
) -> dict[str, int] | None:
    """Count per_candidate entries by lifecycle_status (v3.12)."""
    if not per_candidate:
        return None
    counts: dict[str, int] = {}
    has_any = False
    for entry in per_candidate:
        status = entry.get("lifecycle_status")
        if status is None:
            continue
        has_any = True
        counts[status] = counts.get(status, 0) + 1
    return counts if has_any else None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _extract_rejection_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        if row.get("success") is True and row.get("goedgekeurd") is True:
            continue
        reden = row.get("reden")
        if isinstance(reden, str) and reden.strip():
            counter[reden.strip()] += 1
        else:
            error = row.get("error")
            if isinstance(error, str) and error.strip():
                counter[f"error: {error.strip()}"] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in counter.most_common(10)
    ]


def _extract_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    promoted: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("success"):
            continue
        if not row.get("goedgekeurd"):
            continue
        promoted.append({
            "strategy_name": row.get("strategy_name"),
            "asset": row.get("asset"),
            "interval": row.get("interval"),
            "win_rate": row.get("win_rate"),
            "sharpe": row.get("sharpe"),
            "deflated_sharpe": row.get("deflated_sharpe"),
            "max_drawdown": row.get("max_drawdown"),
            "trades_per_maand": row.get("trades_per_maand"),
            "totaal_trades": row.get("totaal_trades"),
        })
    return promoted


def _summarize_counts(
    rows: list[dict[str, Any]],
    meta_summary: dict[str, int] | None,
) -> dict[str, int]:
    if isinstance(meta_summary, dict) and meta_summary:
        return {k: int(v) for k, v in meta_summary.items()}
    success_rows = [r for r in rows if r.get("success")]
    promoted_rows = [r for r in success_rows if r.get("goedgekeurd")]
    return {
        "raw": len(rows),
        "screened": len(success_rows),
        "validated": len(success_rows),
        "rejected": len(rows) - len(promoted_rows),
        "promoted": len(promoted_rows),
    }


def _summarize_screening(
    rows: list[dict[str, Any]],
    filter_summary: dict[str, Any] | None,
) -> dict[str, int]:
    """v3.11 screening-layer counts, joined from run_filter_summary.

    Falls back to deriving counts from the rows when the sidecar is
    missing. All integers; never negative.
    """
    success_rows = [r for r in rows if r.get("success")]
    if isinstance(filter_summary, dict):
        summary = filter_summary.get("summary") or {}
        raw = int(summary.get("raw_candidate_count", 0) or 0)
        eligible = int(summary.get("eligible_candidate_count", 0) or 0)
        screening = filter_summary.get("screening_decisions") or {}
        promoted = int(screening.get("promoted_to_validation", 0) or 0)
        rejected = int(screening.get("rejected_in_screening", 0) or 0)
        return {
            "raw": raw,
            "eligible": eligible,
            "screening_passed": promoted,
            "screening_rejected": rejected,
        }
    return {
        "raw": len(rows),
        "eligible": len(rows),
        "screening_passed": len(success_rows),
        "screening_rejected": len(rows) - len(success_rows),
    }


def _summarize_promotion(
    rows: list[dict[str, Any]],
    candidate_registry: dict[str, Any] | None,
) -> dict[str, int]:
    """v3.11 promotion-layer counts, joined from candidate_registry.

    Falls back to deriving counts from rows.goedgekeurd when the
    registry sidecar is missing.
    """
    success_rows = [r for r in rows if r.get("success")]
    promoted_rows = [r for r in success_rows if r.get("goedgekeurd")]
    if isinstance(candidate_registry, dict):
        summary = candidate_registry.get("summary") or {}
        total = int(summary.get("total", len(success_rows)) or 0)
        return {
            "evaluated": total,
            "promoted": int(summary.get("candidate", len(promoted_rows)) or 0),
            "needs_investigation": int(summary.get("needs_investigation", 0) or 0),
            "rejected_promotion": int(summary.get("rejected", 0) or 0),
        }
    return {
        "evaluated": len(success_rows),
        "promoted": len(promoted_rows),
        "needs_investigation": 0,
        "rejected_promotion": len(success_rows) - len(promoted_rows),
    }


def _screening_layer_reason_counts(
    rows: list[dict[str, Any]],
    filter_summary: dict[str, Any] | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Aggregate screening-layer rejection reasons.

    Sources read in priority order:
    1. ``run_filter_summary.screening_rejection_reasons`` (canonical)
    2. ``run_filter_summary.eligibility_rejection_reasons``
    3. ``run_filter_summary.fit_blocked_reasons``
    4. Non-empty ``reden`` strings in the rows (fallback)
    """
    counter: Counter[str] = Counter()
    if isinstance(filter_summary, dict):
        for key in (
            "screening_rejection_reasons",
            "eligibility_rejection_reasons",
            "fit_blocked_reasons",
        ):
            bucket = filter_summary.get(key)
            if isinstance(bucket, dict):
                for reason, count in bucket.items():
                    if isinstance(reason, str) and reason:
                        counter[reason] += int(count or 0)
    if not counter:
        for row in rows:
            reden = row.get("reden") if isinstance(row, dict) else None
            if isinstance(reden, str) and reden.strip():
                counter[reden.strip()] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in counter.most_common(limit)
    ]


def _promotion_layer_reason_counts(
    candidate_registry: dict[str, Any] | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Aggregate promotion-layer rejection reasons from the candidate
    registry's per-candidate ``reasoning.failed`` + ``.escalated``
    codes. Consumer-only; we do not re-classify."""
    if not isinstance(candidate_registry, dict):
        return []
    candidates = candidate_registry.get("candidates")
    if not isinstance(candidates, list):
        return []
    counter: Counter[str] = Counter()
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        reasoning = entry.get("reasoning") or {}
        for bucket_key in ("failed", "escalated"):
            bucket = reasoning.get(bucket_key)
            if not isinstance(bucket, list):
                continue
            for code in bucket:
                if isinstance(code, str) and code:
                    counter[code] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in counter.most_common(limit)
    ]


def _extract_red_flags() -> list[dict[str, Any]]:
    payload = _load_json(_INTEGRITY_SIDECAR)
    if not payload:
        return []
    flags: list[dict[str, Any]] = []
    for check in payload.get("checks") or []:
        if not isinstance(check, dict):
            continue
        status = check.get("status")
        if status in {"WARN", "FAIL", "ERROR"}:
            flags.append({
                "check": check.get("name") or check.get("check"),
                "status": status,
                "message": check.get("message") or check.get("detail"),
            })
    return flags


def _statistical_diagnostics() -> dict[str, Any]:
    payload = _load_json(Path("research/statistical_defensibility_latest.v1.json"))
    if not isinstance(payload, dict):
        return {}
    return {
        "generated_at_utc": payload.get("generated_at_utc"),
        "candidate_count": payload.get("candidate_count"),
        "deflated_sharpe_threshold": payload.get("deflated_sharpe_threshold"),
    }


def _regime_diagnostics() -> dict[str, Any]:
    payload = _load_json(Path("research/regime_diagnostics_latest.v1.json"))
    if not isinstance(payload, dict):
        return {}
    return {
        "generated_at_utc": payload.get("generated_at_utc"),
        "regime_count": payload.get("regime_count"),
    }


_PROMOTION_STATISTICAL_CODES = frozenset({
    "psr_below_threshold",
    "psr_unavailable",
    "dsr_canonical_below_threshold",
    "dsr_unavailable",
    "bootstrap_sharpe_ci_includes_zero",
    "bootstrap_sharpe_ci_unavailable",
})
_PROMOTION_RISK_CODES = frozenset({
    "drawdown_above_limit",
})
_PROMOTION_TRADES_CODES = frozenset({
    "insufficient_trades",
})
_PROMOTION_NOISE_CODES = frozenset({
    "noise_warning_fired",
})


def _dominant_promotion_failure_type(
    promotion_reasons: list[dict[str, Any]] | None,
) -> str | None:
    """Return the dominant failure-type among promotion reasons.

    Uses only the pre-existing reason vocabulary — no new taxonomy.
    Returns one of {"statistical", "risk", "trades", "noise"} or None
    when the data is inconclusive (no reasons or no majority bucket).
    """
    if not isinstance(promotion_reasons, list):
        return None
    buckets = {"statistical": 0, "risk": 0, "trades": 0, "noise": 0}
    for entry in promotion_reasons:
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason")
        count = int(entry.get("count") or 0)
        if not isinstance(reason, str) or count <= 0:
            continue
        if reason in _PROMOTION_STATISTICAL_CODES:
            buckets["statistical"] += count
        elif reason in _PROMOTION_RISK_CODES:
            buckets["risk"] += count
        elif reason in _PROMOTION_TRADES_CODES:
            buckets["trades"] += count
        elif reason in _PROMOTION_NOISE_CODES:
            buckets["noise"] += count
    if not any(buckets.values()):
        return None
    dominant = max(buckets, key=lambda k: buckets[k])
    return dominant if buckets[dominant] > 0 else None


def suggest_next_experiment(
    summary: dict[str, int],
    candidates: list[dict[str, Any]],
    meta: dict[str, Any] | None,
    *,
    rejection_reasons_by_layer: dict[str, Any] | None = None,
) -> str:
    """v3.11: layer-aware + failure-type next-experiment suggestion.

    Decision tree (read-only; uses existing reason codes only):

    1. Zero rows -> universe/snapshot check.
    2. Promoted candidates -> broaden timeframe.
    3. Promotion-layer dominant failures -> subtype-aware suggestion
       (statistical / risk / trades / noise).
    4. Screening-layer dominant failures -> hypothesis-level advice.
    5. Diagnostic preset -> preserve rejection patterns.
    6. Otherwise -> try the regime-filtered baseline.
    """
    if summary.get("raw", 0) == 0:
        return (
            "Geen kandidaten gepland. Controleer universe, preset en "
            "asset-snapshot."
        )
    if summary.get("promoted", 0) >= 1:
        names = ", ".join(
            sorted({str(c.get("strategy_name")) for c in candidates})
        )
        return (
            f"Hercheck OOS voor gepromoveerde strategieen ({names}) op "
            "een bredere timeframe; bewaar fold pins voor walk-forward."
        )

    screening_reasons = (
        (rejection_reasons_by_layer or {}).get("screening_layer") or []
    )
    promotion_reasons = (
        (rejection_reasons_by_layer or {}).get("promotion_layer") or []
    )
    screening_total = sum(int(r.get("count") or 0) for r in screening_reasons)
    promotion_total = sum(int(r.get("count") or 0) for r in promotion_reasons)

    if promotion_total > 0 and promotion_total >= screening_total:
        failure_type = _dominant_promotion_failure_type(promotion_reasons)
        if failure_type == "statistical":
            return (
                "Kandidaten haalden screening maar faalden op statistische "
                "defensibility (PSR/DSR/bootstrap). Meer data of langere "
                "history nodig; smallere universe overwegen voordat aan "
                "de parameters wordt gedraaid."
            )
        if failure_type == "risk":
            return (
                "Kandidaten haalden screening maar faalden op drawdown. "
                "Dit is een risk-profiel probleem — onderzoek stop-loss "
                "discipline of positie-sizing, niet de entry-logica."
            )
        if failure_type == "trades":
            return (
                "Kandidaten haalden screening maar produceerden te weinig "
                "trades. Frequenter interval of ruimere drempel binnen de "
                "falsification-criteria; verandering mag geen re-fit zijn."
            )
        if failure_type == "noise":
            return (
                "Promotion markeert runs als waarschijnlijk ruis. "
                "Hercheck feature-kwaliteit en fold-stabiliteit voordat "
                "een volgende preset gepland wordt."
            )
        return (
            "Kandidaten haalden screening maar faalden promotion. Loop "
            "falsification_gates door en overweeg preset met regime filter "
            "('trend_regime_filtered_equities_4h')."
        )

    if screening_total > 0:
        return (
            "Screening-laag is het knelpunt. Hypothese heroverwegen: "
            "andere strategy family, andere timeframe, of gerichter "
            "universe. Drempels niet verlagen zonder falsification-update."
        )

    if summary.get("validated", 0) >= 1:
        return (
            "Kandidaten haalden screening maar faalden promotion. Loop "
            "falsification_gates door en overweeg preset met regime filter "
            "('trend_regime_filtered_equities_4h')."
        )
    if meta and meta.get("diagnostic_only"):
        return (
            "Diagnostische run; geen actie vereist. Bewaar reject-reasons "
            "voor de volgende niet-diagnostische baseline."
        )
    return (
        "Geen trades haalden screening. Overweeg timeframe-variatie of "
        "verlaag niet de drempels; begin met 'trend_regime_filtered_equities_4h'."
    )


def classify_verdict(summary: dict[str, int], meta: dict[str, Any] | None) -> str:
    if summary.get("promoted", 0) >= 1:
        return VERDICT_PROMOTED
    if summary.get("validated", 0) >= 1 or summary.get("screened", 0) >= 1:
        return VERDICT_CANDIDATES_NO_PROMOTION
    return VERDICT_NIETS_BRUIKBAARS


def build_report_payload(
    *,
    run_id: str | None = None,
    research_latest_path: Path = _RESEARCH_LATEST_JSON,
    run_meta_path: Path = RUN_META_PATH,
) -> dict[str, Any]:
    research = _load_json(research_latest_path) or {}
    meta = read_run_meta_sidecar(run_meta_path)
    rows: list[dict[str, Any]] = list(research.get("results") or [])

    # v3.11: load sidecars read-only for screening/promotion split +
    # per-candidate diagnostics.
    candidate_registry = _load_json(_CANDIDATE_REGISTRY_SIDECAR)
    filter_summary = _load_json(_RUN_FILTER_SUMMARY_SIDECAR)
    screening_candidates_payload = _load_json(_RUN_SCREENING_CANDIDATES_SIDECAR)
    defensibility_payload = _load_json(_DEFENSIBILITY_SIDECAR)
    regime_payload = _load_json(_REGIME_SIDECAR)
    cost_sensitivity_payload = _load_json(_COST_SENSITIVITY_SIDECAR)
    strategy_index = {entry["name"]: entry for entry in STRATEGIES}
    per_candidate, join_stats = build_candidate_diagnostics(
        rows=rows,
        candidate_registry=candidate_registry,
        defensibility=defensibility_payload,
        regime=regime_payload,
        cost_sensitivity=cost_sensitivity_payload,
        strategy_index=strategy_index,
    )

    # v3.12: additive enrichment of per_candidate_diagnostics with
    # lifecycle_status, legacy_verdict, observed_reason_codes,
    # taxonomy_rejection_codes, and scores. Report schema_version
    # stays "1.1" — these are optional fields consumers may ignore.
    registry_v2 = _load_json(_REGISTRY_V2_SIDECAR)
    per_candidate = _enrich_with_v3_12_fields(per_candidate, registry_v2)

    # v3.13: additive enrichment with regime_assessment_status,
    # regime_dependency_scores, and a gating-rule summary. Report
    # schema_version remains "1.1" — v3.13 only adds optional fields.
    regime_intelligence_payload = _load_json(_REGIME_INTELLIGENCE_SIDECAR)
    per_candidate = _enrich_with_regime_fields(
        per_candidate, regime_intelligence_payload
    )

    summary = _summarize_counts(
        rows,
        meta.get("candidate_summary") if isinstance(meta, dict) else None,
    )
    # v3.11 additive: screening + promotion counts alongside the
    # existing v3.10 raw/screened/validated/rejected/promoted keys so
    # dashboard consumers that only know v3.10 keep working.
    summary["screening"] = _summarize_screening(rows, filter_summary)
    summary["promotion"] = _summarize_promotion(rows, candidate_registry)

    legacy_rejection_reasons = (
        meta.get("top_rejection_reasons")
        if isinstance(meta, dict) and meta.get("top_rejection_reasons")
        else _extract_rejection_counts(rows)
    )
    # v3.11: same top_rejection_reasons key now carries screening and
    # promotion-layer breakdowns as a dict under ``by_layer``. The
    # flat list shape remains the default for the key itself — keeping
    # v3.10 consumers working — while ``top_rejection_reasons_by_layer``
    # is the new sibling key with the split.
    rejection_reasons_by_layer = {
        "screening_layer": _screening_layer_reason_counts(rows, filter_summary),
        "promotion_layer": _promotion_layer_reason_counts(candidate_registry),
    }

    candidates = _extract_candidates(rows)
    red_flags = _extract_red_flags()
    next_experiment = suggest_next_experiment(
        summary,
        candidates,
        meta,
        rejection_reasons_by_layer=rejection_reasons_by_layer,
    )
    verdict = classify_verdict(summary, meta)

    preset_name = meta.get("preset_name") if isinstance(meta, dict) else None

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id or (meta or {}).get("run_id"),
        "preset": preset_name,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "summary": summary,
        "top_rejection_reasons": legacy_rejection_reasons,
        "top_rejection_reasons_by_layer": rejection_reasons_by_layer,
        "candidates": candidates,
        "per_candidate_diagnostics": per_candidate,
        "trend_pullback_exit_impact": _build_trend_pullback_exit_impact(
            screening_candidates_payload
        ),
        "trend_pullback_exit_quality": _build_trend_pullback_exit_quality(
            screening_candidates_payload
        ),
        "trend_break_threshold_comparison": (
            trend_break_threshold_comparison := _build_trend_break_threshold_comparison(
                screening_candidates_payload
            )
        ),
        "trend_break_threshold_decision_gate": _build_trend_break_threshold_decision_gate(
            trend_break_threshold_comparison
        ),
        "join_stats": join_stats,
        "red_flags": red_flags,
        "regime_diagnostics": _regime_diagnostics(),
        "statistical_diagnostics": _statistical_diagnostics(),
        "next_experiment": next_experiment,
        "verdict": verdict,
        "lifecycle_breakdown": _lifecycle_breakdown(per_candidate),
        "regime_layer_summary": _regime_layer_summary(regime_intelligence_payload),
        "portfolio_layer_summary": _portfolio_layer_summary(
            _load_json(_SLEEVE_REGISTRY_SIDECAR),
            _load_json(_PORTFOLIO_DIAGNOSTICS_SIDECAR),
        ),
        "paper_layer_summary": _paper_layer_summary(
            _load_json(_PAPER_LEDGER_SIDECAR),
            _load_json(_PAPER_DIVERGENCE_SIDECAR),
            _load_json(_PAPER_READINESS_SIDECAR),
        ),
        "paper_readiness_blocker_diagnosis": (
            paper_readiness_blocker_diagnosis := _paper_readiness_blocker_diagnosis(
                _load_json(_PAPER_READINESS_SIDECAR),
                _load_json(_PAPER_LEDGER_SIDECAR),
                _load_json(_PAPER_DIVERGENCE_SIDECAR),
            )
        ),
        "paper_engine_divergence_component_diagnosis": (
            paper_engine_divergence_component_diagnosis := (
                _paper_engine_divergence_component_diagnosis(
                    _load_json(_PAPER_DIVERGENCE_SIDECAR),
                    paper_readiness_blocker_diagnosis,
                )
            )
        ),
        "candidate_shadow_readiness_report": (
            candidate_shadow_readiness_report := _candidate_shadow_readiness_report(
                _load_json(_PAPER_READINESS_SIDECAR),
                _build_trend_pullback_exit_quality(screening_candidates_payload),
            )
        ),
        "no_paper_candidate_next_action_plan": (
            no_paper_candidate_next_action_plan := (
                _next_research_action_from_paper_diagnosis(
                    preset_name=preset_name,
                    paper_diagnosis=paper_readiness_blocker_diagnosis,
                )
            )
        ),
        "research_action_queue_items": _build_research_action_queue_items(
            paper_readiness_diagnosis=paper_readiness_blocker_diagnosis,
            paper_engine_divergence_diagnosis=paper_engine_divergence_component_diagnosis,
            no_paper_candidate_next_action_plan=no_paper_candidate_next_action_plan,
            candidate_shadow_readiness_report=candidate_shadow_readiness_report,
        ),
    }


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _bucket_counts_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "n/a"
    return ", ".join(
        f"{key}={int(count or 0)}"
        for key, count in sorted(value.items())
    )


def _impact_totals_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "n/a"

    parts: list[str] = []
    for key, summary in sorted(value.items()):
        if not isinstance(summary, dict):
            continue
        parts.append(f"{key}={_pct(summary.get('total_pnl'))}")
    return ", ".join(parts) if parts else "n/a"


def _worst_total_pnl_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "n/a"

    candidates: list[tuple[str, float]] = []
    for key, summary in value.items():
        if not isinstance(summary, dict):
            continue
        try:
            candidates.append((str(key), float(summary.get("total_pnl", 0.0))))
        except (TypeError, ValueError):
            continue
    if not candidates:
        return "n/a"
    key, total_pnl = min(candidates, key=lambda item: item[1])
    return f"{key}={_pct(total_pnl)}"


def _best_sample_diagnostic(
    candidate: dict[str, Any],
) -> tuple[int, dict[str, Any], dict[str, Any]] | None:
    diagnostics = candidate.get("sample_diagnostics")
    summary = candidate.get("sample_diagnostics_summary") or {}
    if not isinstance(diagnostics, list) or not diagnostics:
        return None

    try:
        best_index = int(summary.get("best_sample_index", 0))
    except (TypeError, ValueError):
        best_index = 0
    if best_index < 0 or best_index >= len(diagnostics):
        return None

    best = diagnostics[best_index]
    if not isinstance(best, dict):
        return None
    return best_index, best, summary


def _build_trend_pullback_exit_impact(
    screening_candidates: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(screening_candidates, dict):
        return []
    candidates = screening_candidates.get("candidates")
    if not isinstance(candidates, list):
        return []

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        best_result = _best_sample_diagnostic(candidate)
        if best_result is None:
            continue
        best_index, best, _summary = best_result

        exit_summary = best.get("trend_pullback_exit_reason_summary")
        if not isinstance(exit_summary, dict):
            continue

        pnl = exit_summary.get("exit_reason_pnl_summary") or {}
        realized = exit_summary.get("realized_pnl_impact") or {}
        exit_reason_impact = realized.get("by_exit_reason") or pnl
        unknown_subtype_impact = (
            realized.get("by_unknown_subcategory")
            or exit_summary.get("signal_change_unknown_subcategory_pnl_summary")
            or {}
        )
        boundary_bucket_impact = (
            realized.get("by_boundary_proximity_bucket") or {}
        )
        asset_impact = realized.get("by_asset") or {}
        fold_impact = realized.get("by_fold_index") or {}
        counts = exit_summary.get("exit_reason_counts") or {}
        boundary = exit_summary.get("boundary_proximity_summary") or {}
        pullback = exit_reason_impact.get("pullback_resolved") or {}
        trend_break = exit_reason_impact.get("trend_break") or {}
        window_end = exit_reason_impact.get("window_end") or {}
        invalidation = best.get("trend_break_invalidation_summary") or {}

        rows.append(
            {
                "asset": candidate.get("asset"),
                "interval": candidate.get("interval"),
                "decision": candidate.get("decision"),
                "best_sample_index": best_index,
                "pullback_resolved_count": int(
                    counts.get("pullback_resolved", 0) or 0
                ),
                "pullback_resolved_avg_pnl": pullback.get("avg_pnl"),
                "pullback_resolved_total_pnl": pullback.get("total_pnl"),
                "trend_break_count": int(counts.get("trend_break", 0) or 0),
                "trend_break_avg_pnl": trend_break.get("avg_pnl"),
                "trend_break_total_pnl": trend_break.get("total_pnl"),
                "trend_break_largest_loss": trend_break.get("largest_loss"),
                "window_end_count": int(counts.get("window_end", 0) or 0),
                "window_end_avg_pnl": window_end.get("avg_pnl"),
                "window_end_total_pnl": window_end.get("total_pnl"),
                "exit_reason_realized_pnl_impact": exit_reason_impact,
                "unknown_subtype_realized_pnl_impact": unknown_subtype_impact,
                "boundary_bucket_realized_pnl_impact": boundary_bucket_impact,
                "asset_realized_pnl_impact": asset_impact,
                "fold_realized_pnl_impact": fold_impact,
                "boundary_proximity_bucket_counts": boundary.get(
                    "bucket_counts"
                )
                or {},
                "boundary_proximity_by_exit_reason": boundary.get(
                    "by_exit_reason"
                )
                or {},
                "boundary_proximity_by_unknown_subcategory": boundary.get(
                    "by_unknown_subcategory"
                )
                or {},
                "boundary_proximity_by_asset": boundary.get("by_asset") or {},
                "trend_break_avg_mae": invalidation.get("avg_mae"),
                "trend_break_avg_mfe": invalidation.get("avg_mfe"),
                "trend_break_zero_mfe_count": invalidation.get("zero_mfe_count"),
                "trend_break_adverse_dominant_count": invalidation.get(
                    "adverse_dominant_count"
                ),
                "trend_break_avg_holding_bars": invalidation.get("avg_holding_bars"),
                "trend_break_avg_exit_lag_bars": invalidation.get(
                    "avg_exit_lag_bars"
                ),
            }
        )

    return rows


def _build_trend_pullback_exit_quality(
    screening_candidates: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(screening_candidates, dict):
        return []
    candidates = screening_candidates.get("candidates")
    if not isinstance(candidates, list):
        return []

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        best_result = _best_sample_diagnostic(candidate)
        if best_result is None:
            continue
        best_index, best, sample_summary = best_result

        exit_summary = best.get("trend_pullback_exit_reason_summary")
        if not isinstance(exit_summary, dict):
            continue

        health = exit_summary.get("exit_health_summary") or {}
        overall_health = health.get("overall") or {}
        realized = exit_summary.get("realized_pnl_impact") or {}
        boundary = exit_summary.get("boundary_proximity_summary") or {}
        audit = sample_summary.get("best_sample_exit_quality_audit") or {}
        rows.append(
            {
                "asset": candidate.get("asset"),
                "interval": candidate.get("interval"),
                "decision": candidate.get("decision"),
                "best_sample_index": best_index,
                "advisory_only": True,
                "exit_health_summary": health,
                "exit_health_counts": overall_health.get("health_class_counts")
                or {},
                "exit_health_by_class": overall_health.get("by_health_class") or {},
                "exit_health_by_asset": health.get("by_asset") or {},
                "exit_health_by_reason": health.get("by_exit_reason") or {},
                "exit_health_by_unknown_subcategory": health.get(
                    "by_unknown_subcategory"
                )
                or {},
                "exit_health_by_boundary_bucket": health.get(
                    "by_boundary_proximity_bucket"
                )
                or {},
                "exit_reason_semantics": exit_summary.get("exit_reason_semantics")
                or {},
                "exit_reason_realized_pnl_impact": realized.get("by_exit_reason")
                or {},
                "unknown_subtype_realized_pnl_impact": realized.get(
                    "by_unknown_subcategory"
                )
                or {},
                "boundary_bucket_realized_pnl_impact": realized.get(
                    "by_boundary_proximity_bucket"
                )
                or {},
                "boundary_proximity_bucket_counts": boundary.get("bucket_counts")
                or {},
                "best_sample_exit_quality_audit": audit,
            }
        )

    return rows


def _build_trend_break_threshold_comparison(
    screening_candidates_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(screening_candidates_payload, dict):
        return []

    totals: dict[str, dict[str, Any]] = {}
    for candidate in screening_candidates_payload.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue

        diagnostics = candidate.get("sample_diagnostics") or []
        summary = candidate.get("sample_diagnostics_summary") or {}
        if not diagnostics:
            continue

        best_index = int(summary.get("best_sample_index") or 0)
        if best_index < 0 or best_index >= len(diagnostics):
            best_index = 0

        best = diagnostics[best_index] or {}
        comparison = (
            best.get("trend_break_bar_path_threshold_comparison_summary") or {}
        )
        rules = comparison.get("rules") or {}

        for rule_name, result in rules.items():
            if not isinstance(result, dict):
                continue

            row = totals.setdefault(
                str(rule_name),
                {
                    "rule": str(rule_name),
                    "asset_count": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "net_pnl_delta": 0.0,
                    "avoided_loss": 0.0,
                    "sacrificed_profit": 0.0,
                    "other_pnl_delta": 0.0,
                    "triggered_trend_break": 0,
                    "triggered_pullback": 0,
                    "triggered_other": 0,
                },
            )

            net = float(result.get("net_pnl_delta") or 0.0)
            row["asset_count"] += 1
            if net > 0.0:
                row["positive_count"] += 1
            elif net < 0.0:
                row["negative_count"] += 1

            row["net_pnl_delta"] += net
            row["avoided_loss"] += float(result.get("avoided_loss") or 0.0)
            row["sacrificed_profit"] += float(
                result.get("sacrificed_profit") or 0.0
            )
            row["other_pnl_delta"] += float(result.get("other_pnl_delta") or 0.0)
            row["triggered_trend_break"] += int(
                result.get("triggered_trend_break_trades") or 0
            )
            row["triggered_pullback"] += int(
                result.get("triggered_pullback_resolved_trades") or 0
            )
            row["triggered_other"] += int(result.get("triggered_other_trades") or 0)

    return sorted(
        [
            {
                "rule": row["rule"],
                "asset_count": int(row["asset_count"]),
                "positive_count": int(row["positive_count"]),
                "negative_count": int(row["negative_count"]),
                "net_pnl_delta": float(row["net_pnl_delta"]),
                "avoided_loss": float(row["avoided_loss"]),
                "sacrificed_profit": float(row["sacrificed_profit"]),
                "other_pnl_delta": float(row["other_pnl_delta"]),
                "triggered_trend_break": int(row["triggered_trend_break"]),
                "triggered_pullback": int(row["triggered_pullback"]),
                "triggered_other": int(row["triggered_other"]),
            }
            for row in totals.values()
        ],
        key=lambda row: row["net_pnl_delta"],
        reverse=True,
    )


def _build_trend_break_threshold_decision_gate(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        rule = str(row.get("rule") or "")
        net = float(row.get("net_pnl_delta") or 0.0)
        avoided = float(row.get("avoided_loss") or 0.0)
        sacrificed = float(row.get("sacrificed_profit") or 0.0)
        positive_count = int(row.get("positive_count") or 0)
        negative_count = int(row.get("negative_count") or 0)
        triggered_trend_break = int(row.get("triggered_trend_break") or 0)
        triggered_pullback = int(row.get("triggered_pullback") or 0)

        sacrificed_to_avoided_ratio = (
            sacrificed / avoided if avoided > 0.0 else None
        )
        pullback_to_trend_break_ratio = (
            triggered_pullback / triggered_trend_break
            if triggered_trend_break > 0
            else None
        )

        reasons: list[str] = []
        if net <= 0.0:
            decision = "fail"
            reasons.append("net_pnl_delta_not_positive")
        else:
            decision = "pass"

            if positive_count <= negative_count:
                decision = "watch"
                reasons.append("positive_count_not_greater_than_negative_count")

            if sacrificed_to_avoided_ratio is None:
                decision = "watch"
                reasons.append("avoided_loss_zero")
            elif sacrificed_to_avoided_ratio > 0.60:
                decision = "watch"
                reasons.append("sacrificed_profit_above_60pct_of_avoided_loss")

            if pullback_to_trend_break_ratio is None:
                decision = "watch"
                reasons.append("triggered_trend_break_zero")
            elif pullback_to_trend_break_ratio > 0.50:
                decision = "watch"
                reasons.append("pullback_hits_above_50pct_of_trend_break_hits")

        decisions.append(
            {
                "rule": rule,
                "decision": decision,
                "reasons": reasons,
                "net_pnl_delta": net,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "avoided_loss": avoided,
                "sacrificed_profit": sacrificed,
                "sacrificed_to_avoided_ratio": sacrificed_to_avoided_ratio,
                "triggered_trend_break": triggered_trend_break,
                "triggered_pullback": triggered_pullback,
                "pullback_to_trend_break_ratio": pullback_to_trend_break_ratio,
            }
        )

    rank = {"pass": 0, "watch": 1, "fail": 2}
    return sorted(
        decisions,
        key=lambda item: (
            rank.get(str(item.get("decision")), 99),
            -float(item.get("net_pnl_delta") or 0.0),
        ),
    )


def _append_trend_break_threshold_decision_gate_section(
    lines: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    lines.append("## Trend-break early invalidation decision gate")
    lines.append("")
    lines.append(
        "| Rule | Decision | Reasons | Net PnL delta | +Assets | -Assets | "
        "Sacrificed/Avoided | Pullback/TB hit ratio |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")

    for row in rows:
        reasons = row.get("reasons") or []
        reason_text = ", ".join(str(reason) for reason in reasons) if reasons else "?"
        sacrificed_ratio = row.get("sacrificed_to_avoided_ratio")
        pullback_ratio = row.get("pullback_to_trend_break_ratio")
        lines.append(
            f"| `{row.get('rule')}` | "
            f"{row.get('decision')} | "
            f"{reason_text} | "
            f"{_pct(row.get('net_pnl_delta'))} | "
            f"{row.get('positive_count')} | "
            f"{row.get('negative_count')} | "
            f"{_pct(sacrificed_ratio)} | "
            f"{_pct(pullback_ratio)} |"
        )

    lines.append("")


def _append_trend_break_threshold_comparison_section(
    lines: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    lines.append("## Trend-break early invalidation threshold comparison")
    lines.append("")
    lines.append(
        "| Rule | Net PnL delta | Avoided loss | Sacrificed profit | "
        "Other PnL delta | +Assets | -Assets | TB hit | Pullbacks hit | Other hit |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    for row in rows:
        lines.append(
            f"| `{row.get('rule')}` | "
            f"{_pct(row.get('net_pnl_delta'))} | "
            f"{_pct(row.get('avoided_loss'))} | "
            f"{_pct(row.get('sacrificed_profit'))} | "
            f"{_pct(row.get('other_pnl_delta'))} | "
            f"{row.get('positive_count')} | "
            f"{row.get('negative_count')} | "
            f"{row.get('triggered_trend_break')} | "
            f"{row.get('triggered_pullback')} | "
            f"{row.get('triggered_other')} |"
        )

    lines.append("")


def _append_trend_pullback_exit_impact_section(
    lines: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    lines.append("## Trend-pullback exit impact (diagnostic only)")
    lines.append(
        "| Asset | Decision | Pullback count | Pullback total PnL | "
        "Pullback avg PnL | Trend-break count | Trend-break total PnL | "
        "Trend-break avg PnL | Trend-break largest loss | Window-end count | "
        "Window-end total PnL | Window-end avg PnL | Worst exit reason | "
        "Unknown subtype totals | Boundary buckets | Boundary totals | "
        "TB avg MAE | TB avg MFE | TB zero-MFE | TB adverse-dominant | "
        "TB avg hold bars | TB avg exit-lag bars |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|"
    )
    for row in rows:
        lines.append(
            f"| `{row.get('asset')}` | {row.get('decision')} | "
            f"{row.get('pullback_resolved_count')} | "
            f"{_pct(row.get('pullback_resolved_total_pnl'))} | "
            f"{_pct(row.get('pullback_resolved_avg_pnl'))} | "
            f"{row.get('trend_break_count')} | "
            f"{_pct(row.get('trend_break_total_pnl'))} | "
            f"{_pct(row.get('trend_break_avg_pnl'))} | "
            f"{_pct(row.get('trend_break_largest_loss'))} | "
            f"{row.get('window_end_count')} | "
            f"{_pct(row.get('window_end_total_pnl'))} | "
            f"{_pct(row.get('window_end_avg_pnl'))} | "
            f"{_worst_total_pnl_text(row.get('exit_reason_realized_pnl_impact'))} | "
            f"{_impact_totals_text(row.get('unknown_subtype_realized_pnl_impact'))} | "
            f"{_bucket_counts_text(row.get('boundary_proximity_bucket_counts'))} | "
            f"{_impact_totals_text(row.get('boundary_bucket_realized_pnl_impact'))} | "
            f"{_pct(row.get('trend_break_avg_mae'))} | "
            f"{_pct(row.get('trend_break_avg_mfe'))} | "
            f"{row.get('trend_break_zero_mfe_count')} | "
            f"{row.get('trend_break_adverse_dominant_count')} | "
            f"{_num(row.get('trend_break_avg_holding_bars'))} | "
            f"{_num(row.get('trend_break_avg_exit_lag_bars'))} |"
        )
    lines.append("")


def _health_share_text(row: dict[str, Any], health_class: str) -> str:
    summary = row.get("exit_health_by_class") or {}
    if not isinstance(summary, dict):
        return "n/a"
    return _pct((summary.get(health_class) or {}).get("trade_share"))


def _append_trend_pullback_exit_quality_section(
    lines: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    lines.append("## Trend-pullback exit quality (advisory only)")
    lines.append(
        "- Health classes are diagnostic context only; they do not change "
        "exit reasons, strategy behavior, or sample selection."
    )
    lines.append(
        "- Boundary proximity is context, not reclassification; realized PnL "
        "impact remains separate from simulated invalidation deltas."
    )
    lines.append(
        "- `pullback_resolved_and_trend_break` is treated as ambiguous late/choppy "
        "evidence until further research proves otherwise."
    )
    lines.append("")
    lines.append(
        "| Asset | Decision | Best sample | Health counts | Risk share | "
        "Unknown share | Boundary share | Late/choppy share | Selected score | "
        "Exit-quality best | Disagreement | Advisory message |"
    )
    lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|")
    for row in rows:
        audit = row.get("best_sample_exit_quality_audit") or {}
        lines.append(
            f"| `{row.get('asset')}` | {row.get('decision')} | "
            f"{row.get('best_sample_index')} | "
            f"{_bucket_counts_text(row.get('exit_health_counts'))} | "
            f"{_health_share_text(row, 'risk_exit')} | "
            f"{_health_share_text(row, 'unknown_exit')} | "
            f"{_health_share_text(row, 'boundary_exit')} | "
            f"{_health_share_text(row, 'late_or_choppy_exit')} | "
            f"{_num(audit.get('selected_sample_health_score'))} | "
            f"{audit.get('exit_quality_best_sample_index')} | "
            f"{audit.get('exit_quality_disagreement')} | "
            f"{audit.get('advisory_message') or 'n/a'} |"
        )
    lines.append("")


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    preset = report.get("preset") or "(no preset)"
    verdict = report.get("verdict") or "unknown"
    summary = report.get("summary") or {}
    lines.append(f"# Research report — {preset}")
    lines.append("")
    lines.append(f"- run_id: `{report.get('run_id')}`")
    lines.append(f"- generated_at_utc: `{report.get('generated_at_utc')}`")
    lines.append(f"- verdict: **{verdict}**")
    lines.append("")

    _append_hypothesis_section(lines)
    _append_summary_section(lines, summary, report.get("join_stats"))

    if verdict == VERDICT_NIETS_BRUIKBAARS:
        lines.append("> **Niets bruikbaars vandaag.** Geen kandidaten haalden screening.")
        lines.append("")

    _append_what_worked_section(lines, report.get("candidates") or [])
    _append_what_didnt_work_section(
        lines,
        report.get("top_rejection_reasons_by_layer"),
        report.get("top_rejection_reasons") or [],
    )
    _append_waarom_section(lines, report.get("per_candidate_diagnostics") or [])
    _append_trend_pullback_exit_impact_section(
        lines,
        report.get("trend_pullback_exit_impact") or [],
    )
    _append_trend_pullback_exit_quality_section(
        lines,
        report.get("trend_pullback_exit_quality") or [],
    )
    _append_trend_break_threshold_comparison_section(
        lines,
        report.get("trend_break_threshold_comparison") or [],
    )
    _append_trend_break_threshold_decision_gate_section(
        lines,
        report.get("trend_break_threshold_decision_gate") or [],
    )
    _append_lifecycle_breakdown_section(lines, report.get("lifecycle_breakdown"))
    _append_portfolio_layer_section(lines, report.get("portfolio_layer_summary"))
    _append_paper_layer_section(lines, report.get("paper_layer_summary"))
    _append_paper_readiness_blocker_diagnosis_section(
        lines,
        report.get("paper_readiness_blocker_diagnosis"),
    )
    _append_paper_engine_divergence_component_diagnosis_section(
        lines,
        report.get("paper_engine_divergence_component_diagnosis"),
    )
    _append_candidate_shadow_readiness_section(
        lines,
        report.get("candidate_shadow_readiness_report"),
    )
    _append_no_paper_candidate_next_action_section(
        lines,
        report.get("no_paper_candidate_next_action_plan"),
    )
    _append_research_action_queue_items_section(
        lines,
        report.get("research_action_queue_items"),
    )

    red_flags = report.get("red_flags") or []
    if red_flags:
        lines.append("## Red flags")
        for f in red_flags:
            lines.append(f"- {f.get('status')}: {f.get('check')} — {f.get('message')}")
        lines.append("")
    lines.append("## Diagnostics")
    lines.append(f"- statistical: {report.get('statistical_diagnostics') or {}}")
    lines.append(f"- regime: {report.get('regime_diagnostics') or {}}")
    lines.append("")
    lines.append("## Volgende stap")
    lines.append(f"- {report.get('next_experiment')}")
    lines.append("")
    return "\n".join(lines)


def _append_lifecycle_breakdown_section(
    lines: list[str], breakdown: dict[str, int] | None
) -> None:
    """v3.12 additive markdown section — rendered only when data is present."""
    if not breakdown:
        return
    lines.append("## Candidate Lifecycle Breakdown (v3.12)")
    for status in sorted(breakdown.keys()):
        lines.append(f"- {status}: {breakdown[status]}")
    lines.append("")


def _append_portfolio_layer_section(
    lines: list[str], summary: dict[str, Any] | None
) -> None:
    """v3.14 additive markdown section — rendered only when v3.14 sidecars exist.

    Non-authoritative by construction: the section title and every
    metric explicitly labels itself as diagnostic so the reader does
    not mistake it for a portfolio allocation decision.
    """
    if not summary:
        return
    lines.append("## Portfolio Layer Summary (v3.14 — diagnostic only)")
    lines.append(
        f"- sleeve_count: {summary.get('sleeve_count')} "
        f"(candidate members total: {summary.get('candidate_members_total')})"
    )
    ewp = summary.get("equal_weight_portfolio") or {}
    lines.append(
        "- equal_weight_portfolio: "
        f"candidate_count={ewp.get('candidate_count')}, "
        f"overlap_days={ewp.get('overlap_days')}, "
        f"insufficient_overlap={ewp.get('insufficient_overlap')}, "
        f"sharpe={ewp.get('sharpe')}, "
        f"sortino={ewp.get('sortino')}, "
        f"max_drawdown={ewp.get('max_drawdown')}, "
        f"calmar={ewp.get('calmar')}"
    )
    lines.append(
        f"- concentration_warnings: {summary.get('concentration_warning_count')}"
    )
    lines.append(
        "- intra_sleeve_correlation_warnings: "
        f"{summary.get('intra_sleeve_correlation_warning_count')}"
    )
    lines.append(
        "- authoritative: "
        f"{summary.get('authoritative')} (diagnostics are non-authoritative)"
    )
    lines.append("")


def _append_paper_layer_section(
    lines: list[str], summary: dict[str, Any] | None
) -> None:
    """v3.15 additive markdown section — rendered only when v3.15 sidecars exist.

    All metrics are diagnostic-only. ``live_eligible`` is always
    ``False`` — the section header and the trailing bullet reinforce
    that v3.15 evidence cannot promote anything to live.
    """
    if not summary:
        return
    lines.append("## Paper Layer Summary (v3.15 — diagnostic only, live_eligible=False)")
    lines.append(
        f"- candidate_count: {summary.get('candidate_count')}"
    )
    ec = summary.get("ledger_event_counts") or {}
    lines.append(
        "- ledger_event_counts: "
        f"signal={ec.get('signal', 0)}, "
        f"order={ec.get('order', 0)}, "
        f"fill={ec.get('fill', 0)}, "
        f"reject={ec.get('reject', 0)}, "
        f"skip={ec.get('skip', 0)}, "
        f"position={ec.get('position', 0)}"
    )
    sev = summary.get("divergence_severity_counts") or {}
    lines.append(
        "- divergence_severity: "
        f"low={sev.get('low', 0)}, "
        f"medium={sev.get('medium', 0)}, "
        f"high={sev.get('high', 0)}"
    )
    rc = summary.get("readiness_counts") or {}
    lines.append(
        "- readiness_counts: "
        f"ready_for_paper_promotion={rc.get('ready_for_paper_promotion', 0)}, "
        f"blocked={rc.get('blocked', 0)}, "
        f"insufficient_evidence={rc.get('insufficient_evidence', 0)}"
    )
    lines.append(
        f"- live_eligible: {summary.get('live_eligible')} (v3.15 is research-only)"
    )
    lines.append("")




def _append_paper_readiness_blocker_diagnosis_section(
    lines: list[str], summary: dict[str, Any] | None
) -> None:
    """Render generic paper-readiness blocker diagnosis."""
    if not summary:
        return
    lines.append("## Paper Readiness Blocker Diagnosis (advisory only)")
    lines.append(
        f"- paper_candidate_search_status: {summary.get('paper_candidate_search_status')}"
    )
    lines.append(
        "- candidates: "
        f"total={summary.get('candidate_count')}, "
        f"ready={summary.get('ready_candidate_count')}, "
        f"blocked={summary.get('blocked_candidate_count')}, "
        f"insufficient_evidence={summary.get('insufficient_evidence_candidate_count')}"
    )
    blockers = summary.get("dominant_blockers") or []
    lines.append(
        "- dominant_blockers: "
        + (
            ", ".join(
                f"{row.get('reason')}={row.get('count')}"
                for row in blockers
                if isinstance(row, dict)
            )
            if blockers
            else "none"
        )
    )
    diagnoses = summary.get("dominant_diagnoses") or []
    lines.append(
        "- dominant_diagnoses: "
        + (
            ", ".join(
                f"{row.get('diagnosis_class')}={row.get('count')}"
                for row in diagnoses
                if isinstance(row, dict)
            )
            if diagnoses
            else "none"
        )
    )
    closest = summary.get("closest_candidate") or {}
    if closest:
        lines.append(
            "- closest_candidate: "
            f"{closest.get('candidate_id')} "
            f"status={closest.get('readiness_status')} "
            f"diagnosis={closest.get('diagnosis_class')} "
            f"events={closest.get('paper_ledger_event_count')} "
            f"divergence={closest.get('divergence_severity')}"
        )
    else:
        lines.append("- closest_candidate: none")
    lines.append(
        f"- recommended_next_action: {summary.get('recommended_next_action')}"
    )
    lines.append(
        "- advisory: this diagnosis explains why paper candidates are absent; "
        "it does not change readiness thresholds, presets, strategies, campaign queues, "
        "or paper/shadow/live runtime."
    )
    lines.append("")




def _append_no_paper_candidate_next_action_section(
    lines: list[str], summary: dict[str, Any] | None
) -> None:
    """Render bounded next action plan when no paper candidate is available."""
    if not summary:
        return
    lines.append("## No Paper Candidate Next Action Plan (advisory only)")
    lines.append(
        f"- paper_candidate_search_status: {summary.get('paper_candidate_search_status')}"
    )
    lines.append(f"- regular_asset_scope: {summary.get('regular_asset_scope')}")
    lines.append(f"- recommended_action_id: {summary.get('recommended_action_id')}")
    lines.append(f"- recommended_action_mode: {summary.get('recommended_action_mode')}")
    lines.append(
        "- reason_codes: "
        + (
            ", ".join(str(code) for code in (summary.get("reason_codes") or []))
            if summary.get("reason_codes")
            else "none"
        )
    )
    lines.append(f"- bounded_next_step: {summary.get('bounded_next_step')}")
    gate = summary.get("hypothesis_preset_proposal_gate") or {}
    lines.append(
        "- hypothesis_preset_proposal_gate: "
        f"status={gate.get('gate_status')}, "
        f"operator_approval_required="
        f"{gate.get('operator_approval_required_for_new_hypothesis_or_preset')}, "
        f"automatic_preset_mutation_allowed="
        f"{gate.get('automatic_preset_mutation_allowed')}, "
        f"automatic_strategy_mutation_allowed="
        f"{gate.get('automatic_strategy_mutation_allowed')}, "
        f"automatic_campaign_queue_mutation_allowed="
        f"{gate.get('automatic_campaign_queue_mutation_allowed')}"
    )
    if gate.get("regular_asset_research_direction"):
        lines.append(
            "- regular_asset_research_direction: "
            f"{gate.get('regular_asset_research_direction')}"
        )
    lines.append(
        "- forbidden_actions: "
        + ", ".join(str(item) for item in (summary.get("forbidden_actions") or []))
    )
    lines.append(
        "- advisory: QRE should explain missing paper candidates before more manual "
        "preset attempts; any new hypothesis or preset proposal remains operator-gated."
    )
    lines.append("")




def _append_paper_engine_divergence_component_diagnosis_section(
    lines: list[str], summary: dict[str, Any] | None
) -> None:
    """Render paper-engine divergence component diagnosis."""
    if not summary:
        return

    lines.append("## Paper Engine Divergence Component Diagnosis (advisory only)")
    lines.append(
        "- candidates: "
        f"total={summary.get('candidate_count')}, "
        f"high_divergence={summary.get('high_divergence_candidate_count')}"
    )
    driver_counts = summary.get("component_driver_counts") or {}
    lines.append(
        "- component_driver_counts: "
        + (
            ", ".join(f"{key}={value}" for key, value in sorted(driver_counts.items()))
            if driver_counts
            else "none"
        )
    )

    closest = summary.get("closest_candidate_component_diagnosis") or {}
    if closest:
        metrics = closest.get("metrics_delta") or {}
        costs = closest.get("venue_cost_delta") or {}
        lines.append(
            "- closest_candidate: "
            f"{closest.get('candidate_id')} "
            f"severity={closest.get('divergence_severity')} "
            f"driver={closest.get('divergence_component_driver')} "
            f"fills={closest.get('n_full_fills')} "
            f"final_equity_delta_bps={_num(metrics.get('final_equity_delta_bps'))}"
        )
        lines.append(
            "- closest_candidate_cost_components: "
            f"fee_drag_engine_baseline={_pct(costs.get('fee_drag_engine_baseline'))}, "
            f"fee_drag_venue={_pct(costs.get('fee_drag_venue'))}, "
            f"fee_drag_delta_vs_baseline={_pct(costs.get('fee_drag_delta_vs_baseline'))}, "
            f"slippage_drag={_pct(costs.get('slippage_drag'))}, "
            f"venue_fee_per_side={_pct(costs.get('venue_fee_per_side'))}, "
            f"venue_slippage_bps={_num(costs.get('venue_slippage_bps'))}"
        )
        lines.append(
            "- closest_candidate_adjustment: "
            f"per_fill_adjustment={_num(costs.get('per_fill_adjustment'))}, "
            f"cumulative_adjustment={_num(metrics.get('cumulative_adjustment'))}, "
            f"sharpe_proxy_delta={_num(metrics.get('sharpe_proxy_delta'))}"
        )
    else:
        lines.append("- closest_candidate: none")

    lines.append(
        f"- recommended_next_action: {summary.get('recommended_next_action')}"
    )
    lines.append(
        "- advisory: this explains divergence components only; it does not change "
        "paper-readiness thresholds, divergence math, presets, strategies, campaign "
        "queues, or paper/shadow/live runtime."
    )
    lines.append("")




def _append_research_action_queue_items_section(
    lines: list[str], items: list[dict[str, Any]] | None
) -> None:
    """Render advisory research action queue items."""
    if not items:
        return

    lines.append("## Research Action Queue Items (emitter only)")
    lines.append(
        "- status: emitted_machine_readable_actions_only; "
        "execution_enabled=False; no campaign/ADE/runtime mutation"
    )
    lines.append("")
    lines.append(
        "| Priority | Action | Source | Target candidate | Operator approval | Bounded next step |"
    )
    lines.append("|---|---|---|---|---:|---|")

    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {item.get('priority')} | "
            f"`{item.get('action_id')}` | "
            f"{item.get('source_section')} | "
            f"{item.get('target_candidate_id') or 'n/a'} | "
            f"{item.get('operator_approval_required')} | "
            f"{item.get('bounded_next_step')} |"
        )

    forbidden = sorted(
        {
            str(action)
            for item in items
            if isinstance(item, dict)
            for action in (item.get("forbidden_actions") or [])
        }
    )
    lines.append("")
    lines.append(
        "- forbidden_actions: "
        + (", ".join(forbidden) if forbidden else "none")
    )
    lines.append(
        "- advisory: queue items are report-only intent; they do not execute, "
        "write an ADE queue, mutate campaigns, change strategies/presets, alter "
        "thresholds, or activate paper/shadow/live runtime."
    )
    lines.append("")



def _append_candidate_shadow_readiness_section(
    lines: list[str], summary: dict[str, Any] | None
) -> None:
    """Render advisory candidate shadow-readiness evidence.

    This section is deliberately default-off: it can recommend operator review,
    but it cannot activate shadow, paper, or live behavior.
    """
    if not summary:
        return
    lines.append("## Candidate Shadow Readiness (advisory only, default-off)")
    lines.append(f"- readiness_status: {summary.get('readiness_status')}")
    lines.append(
        "- runtime_enabled: "
        f"shadow={summary.get('shadow_runtime_enabled')}, "
        f"paper={summary.get('paper_runtime_enabled')}, "
        f"live_eligible={summary.get('live_eligible')}"
    )
    lines.append(
        "- operator_go_required: "
        f"{summary.get('operator_go_required')} "
        "(this report does not authorize runtime activation)"
    )
    lines.append(
        "- candidates: "
        f"total={summary.get('candidate_count')}, "
        f"paper_ready={summary.get('paper_ready_candidate_count')}, "
        f"blocked={summary.get('paper_blocked_candidate_count')}, "
        f"insufficient_evidence={summary.get('paper_insufficient_evidence_candidate_count')}"
    )
    lines.append(
        "- exit_quality_context: "
        f"rows={summary.get('exit_quality_candidate_count')}, "
        f"disagreements={summary.get('exit_quality_disagreement_count')}, "
        f"risk_candidates={summary.get('risk_exit_candidate_count')}, "
        f"late_or_choppy_candidates={summary.get('late_or_choppy_candidate_count')}, "
        f"unknown_candidates={summary.get('unknown_exit_candidate_count')}, "
        f"boundary_candidates={summary.get('boundary_exit_candidate_count')}"
    )
    blockers = summary.get("blocking_reasons") or []
    warnings = summary.get("warnings") or []
    lines.append(
        "- blocking_reasons: "
        + (", ".join(str(reason) for reason in blockers) if blockers else "none")
    )
    lines.append(
        "- warnings: "
        + (", ".join(str(reason) for reason in warnings) if warnings else "none")
    )
    lines.append(
        "- advisory: candidate shadow readiness is evidence context only; "
        "best-sample selection, paper runtime, shadow runtime, and live paths remain unchanged."
    )
    lines.append("")



def _append_hypothesis_section(lines: list[str]) -> None:
    """Render preset-level hypothesis metadata from run_meta sidecar."""
    meta = read_run_meta_sidecar()
    lines.append("## Hypothese")
    if not isinstance(meta, dict):
        lines.append("- (run_meta sidecar ontbreekt; hypothese niet beschikbaar)")
        lines.append("")
        return
    hypothesis = meta.get("preset_hypothesis")
    preset_class = meta.get("preset_class")
    rationale = meta.get("preset_rationale")
    expected = meta.get("preset_expected_behavior")
    falsification = meta.get("preset_falsification") or []
    bundle_hypotheses = meta.get("preset_bundle_hypotheses") or []

    if preset_class:
        lines.append(f"- preset_class: `{preset_class}`")
    if isinstance(hypothesis, str) and hypothesis.strip():
        lines.append(f"- hypothesis: {hypothesis}")
    if isinstance(rationale, str) and rationale.strip():
        lines.append(f"- rationale: {rationale}")
    if isinstance(expected, str) and expected.strip():
        lines.append(f"- expected_behavior: {expected}")
    if isinstance(falsification, list) and falsification:
        lines.append("- falsification:")
        for criterion in falsification:
            if isinstance(criterion, str) and criterion.strip():
                lines.append(f"    - {criterion}")
    if isinstance(bundle_hypotheses, list) and bundle_hypotheses:
        lines.append("- bundle hypotheses:")
        for entry in bundle_hypotheses:
            if not isinstance(entry, dict):
                continue
            name = entry.get("strategy_name")
            h = entry.get("hypothesis")
            if isinstance(name, str) and isinstance(h, str):
                lines.append(f"    - `{name}`: {h}")
    lines.append("")


def _append_summary_section(
    lines: list[str],
    summary: dict[str, Any],
    join_stats: dict[str, Any] | None,
) -> None:
    lines.append("## Samenvatting")
    for key in ("raw", "screened", "validated", "rejected", "promoted"):
        lines.append(f"- {key}: {summary.get(key, 0)}")
    screening = summary.get("screening") or {}
    promotion = summary.get("promotion") or {}
    if screening:
        lines.append("### Screening-laag")
        for key in ("raw", "eligible", "screening_passed", "screening_rejected"):
            lines.append(f"- {key}: {screening.get(key, 0)}")
    if promotion:
        lines.append("### Promotion-laag")
        for key in ("evaluated", "promoted", "needs_investigation", "rejected_promotion"):
            lines.append(f"- {key}: {promotion.get(key, 0)}")
    if isinstance(join_stats, dict) and join_stats:
        lines.append("### Join stats (artifact koppeling)")
        for key, value in sorted(join_stats.items()):
            lines.append(f"- {key}: {value}")
    lines.append("")


def _append_what_worked_section(
    lines: list[str],
    candidates: list[dict[str, Any]],
) -> None:
    lines.append("## Wat werkte")
    if not candidates:
        lines.append("Geen kandidaten gepromoveerd.")
        lines.append("")
        return
    for c in candidates:
        lines.append(
            f"- `{c.get('strategy_name')}` op `{c.get('asset')}` "
            f"({c.get('interval')}) — sharpe {c.get('sharpe')}, "
            f"win_rate {c.get('win_rate')}"
        )
    lines.append("")


def _append_what_didnt_work_section(
    lines: list[str],
    by_layer: dict[str, Any] | None,
    legacy_flat: list[dict[str, Any]],
) -> None:
    lines.append("## Wat werkte niet")
    screening_reasons = (
        (by_layer or {}).get("screening_layer") or []
    )
    promotion_reasons = (
        (by_layer or {}).get("promotion_layer") or []
    )
    if not screening_reasons and not promotion_reasons and not legacy_flat:
        lines.append("Geen rejection reasons geregistreerd.")
        lines.append("")
        return

    lines.append("### Screening-laag")
    if screening_reasons:
        for item in screening_reasons:
            lines.append(f"- {item.get('reason')} ({item.get('count')})")
    else:
        lines.append("(geen screening-laag rejecties)")

    lines.append("### Promotion-laag")
    if promotion_reasons:
        for item in promotion_reasons:
            lines.append(f"- {item.get('reason')} ({item.get('count')})")
    else:
        lines.append("(geen promotion-laag rejecties)")
    lines.append("")


def _append_waarom_section(
    lines: list[str],
    per_candidate: list[dict[str, Any]],
) -> None:
    """v3.11 per-candidate 'why' section.

    Renders verdict + rejection_layer + top 2 reasons +
    stability/cost/regime flags per row, without re-deriving anything.
    """
    lines.append("## Waarom (per candidate)")
    if not per_candidate:
        lines.append("Geen per-candidate diagnostics beschikbaar.")
        lines.append("")
        return
    for entry in per_candidate:
        name = entry.get("strategy_name")
        asset = entry.get("asset")
        interval = entry.get("interval")
        verdict = entry.get("verdict")
        layer = entry.get("rejection_layer") or "—"
        reasons = entry.get("rejection_reasons") or []
        top_reasons = ", ".join(str(r) for r in reasons[:2]) if reasons else "—"
        flags = entry.get("stability_flags") or {}
        active_flags = [
            key for key, value in flags.items() if value is True
        ]
        flag_str = ", ".join(active_flags) if active_flags else "geen"
        cost_flag = entry.get("cost_sensitivity_flag")
        regime_flag = entry.get("regime_suspicion_flag")
        lines.append(
            f"- `{name}` / `{asset}` / `{interval}` — "
            f"verdict=**{verdict}** (layer={layer}); "
            f"reasons=[{top_reasons}]; "
            f"stability_flags=[{flag_str}]; "
            f"cost_sensitivity={cost_flag}; "
            f"regime_suspicion={regime_flag}"
        )
    lines.append("")


def write_report(
    report: dict[str, Any],
    *,
    markdown_path: Path = REPORT_MARKDOWN_PATH,
    json_path: Path = REPORT_JSON_PATH,
) -> tuple[Path, Path]:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return markdown_path, json_path


def generate_post_run_report(
    run_id: str | None = None,
    *,
    research_latest_path: Path = _RESEARCH_LATEST_JSON,
    run_meta_path: Path = RUN_META_PATH,
    markdown_path: Path = REPORT_MARKDOWN_PATH,
    json_path: Path = REPORT_JSON_PATH,
) -> dict[str, Any]:
    report = build_report_payload(
        run_id=run_id,
        research_latest_path=research_latest_path,
        run_meta_path=run_meta_path,
    )
    write_report(report, markdown_path=markdown_path, json_path=json_path)
    return report


__all__ = [
    "REPORT_JSON_PATH",
    "REPORT_MARKDOWN_PATH",
    "REPORT_SCHEMA_VERSION",
    "VERDICT_CANDIDATES_NO_PROMOTION",
    "VERDICT_NIETS_BRUIKBAARS",
    "VERDICT_PROMOTED",
    "build_report_payload",
    "classify_verdict",
    "generate_post_run_report",
    "render_markdown",
    "suggest_next_experiment",
    "write_report",
]
