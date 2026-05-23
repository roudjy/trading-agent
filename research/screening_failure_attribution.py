"""Screening failure attribution sidecar.

This module explains why candidate screening produced no survivors or
otherwise rejected candidates. It reads existing research sidecars only
and writes only screening-failure attribution reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

SCREENING_FAILURE_ATTRIBUTION_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path(
    "research/screening_failure_attribution_latest.v1.json"
)
DEFAULT_REPORT_MD_PATH: Final[Path] = Path("research/screening_failure_attribution_latest.md")

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "screening_evidence": Path("research/screening_evidence_latest.v1.json"),
    "run_filter_summary": Path("research/run_filter_summary_latest.v1.json"),
    "run_screening_candidates": Path("research/run_screening_candidates_latest.v1.json"),
    "empty_run_diagnostics": Path("research/empty_run_diagnostics_latest.v1.json"),
    "run_campaign": Path("research/run_campaign_latest.v1.json"),
    "controlled_eval": Path("research/controlled_eval_latest.v1.json"),
    "campaign_registry": Path("research/campaign_registry_latest.v1.json"),
    "campaign_evidence_ledger": Path("research/campaign_evidence_ledger_latest.v1.jsonl"),
    "research_state": Path("research/research_state_latest.v1.json"),
    "policy_filter_diagnostics": Path("research/policy_filter_diagnostics_latest.v1.json"),
}

CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "insufficient_trades",
    "no_oos_returns",
    "timeout",
    "cost_sensitivity",
    "parameter_instability",
    "data_coverage_gap",
    "missing_screening_evidence",
    "incomplete_policy_trace",
    "no_candidate_after_policy_filter",
    "no_survivor_after_eval",
    "insufficient_oos_window",
    "missing_metric_field",
    "unsupported_failure_shape",
    "synthesis_gate_blocked",
    "data_coverage_unknown",
    "identity_unresolved",
    "policy_trace_inconsistent",
    "strict_gate_rejection",
    "missing_diagnostics",
    "unknown_screening_failure",
)

LEGACY_CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "insufficient_trades",
    "no_oos_returns",
    "timeout",
    "cost_sensitivity",
    "parameter_instability",
    "data_coverage_gap",
    "strict_gate_rejection",
    "missing_diagnostics",
    "unknown_screening_failure",
)

LEGACY_REASON_TO_CLASSIFICATION: Final[dict[str, str]] = {
    "insufficient_trades": "insufficient_trades",
    "no_oos_samples": "no_oos_returns",
    "no_oos_returns": "no_oos_returns",
    "no_oos_daily_returns": "no_oos_returns",
    "candidate_budget_exceeded": "timeout",
    "screening_candidate_timeout": "timeout",
    "launcher_timeout": "timeout",
    "timeout": "timeout",
    "timed_out": "timeout",
    "cost_sensitive": "cost_sensitivity",
    "cost_sensitivity": "cost_sensitivity",
    "cost_sensitivity_flag": "cost_sensitivity",
    "unstable_parameter_neighborhood": "parameter_instability",
    "parameter_instability": "parameter_instability",
    "parameter_coverage_gap": "parameter_instability",
    "data_unavailable": "data_coverage_gap",
    "empty_dataset": "data_coverage_gap",
    "coverage_warning": "data_coverage_gap",
    "coverage_gap": "data_coverage_gap",
    "screening_criteria_not_met": "strict_gate_rejection",
    "strict_gate_rejection": "strict_gate_rejection",
    "expectancy_not_positive": "strict_gate_rejection",
    "profit_factor_below_floor": "strict_gate_rejection",
    "drawdown_above_exploratory_limit": "strict_gate_rejection",
}

REASON_TO_CLASSIFICATION: Final[dict[str, str]] = {
    **LEGACY_REASON_TO_CLASSIFICATION,
    "missing_screening_evidence": "missing_screening_evidence",
    "missing_screening_drop_reasons": "missing_screening_evidence",
    "screening_evidence_missing": "missing_screening_evidence",
    "incomplete_policy_trace": "incomplete_policy_trace",
    "missing_policy_rules_trace": "incomplete_policy_trace",
    "missing_r4_r7_policy_trace": "incomplete_policy_trace",
    "missing_r8_idle_policy_trace": "incomplete_policy_trace",
    "no_candidate_after_policy_filter": "no_candidate_after_policy_filter",
    "no_eligible_template": "no_candidate_after_policy_filter",
    "no_policy_candidates": "no_candidate_after_policy_filter",
    "no_survivor_after_eval": "no_survivor_after_eval",
    "completed_no_survivor": "no_survivor_after_eval",
    "degenerate_no_survivors": "no_survivor_after_eval",
    "insufficient_oos_window": "insufficient_oos_window",
    "insufficient_oos_days": "insufficient_oos_window",
    "oos_window_too_short": "insufficient_oos_window",
    "missing_metric_field": "missing_metric_field",
    "unsupported_failure_shape": "unsupported_failure_shape",
    "unknown_stage_result": "unsupported_failure_shape",
    "missing_screening_reason_code": "unsupported_failure_shape",
    "synthesis_gate_blocked": "synthesis_gate_blocked",
    "data_coverage_unknown": "data_coverage_unknown",
    "coverage_unknown": "data_coverage_unknown",
    "identity_unresolved": "identity_unresolved",
    "identity_fallback_used": "identity_unresolved",
    "policy_trace_inconsistent": "policy_trace_inconsistent",
}

SCREENING_METRIC_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "expectancy",
        "profit_factor",
        "max_drawdown",
        "totaal_trades",
    }
)
BLOCKED_SYNTHESIS_STATES: Final[frozenset[str]] = frozenset(
    {
        "blocked_insufficient_attribution",
        "blocked_policy_only_failure",
        "blocked_evaluability_primary",
        "blocked_missing_market_context",
        "blocked_no_preset_space_exhaustion",
    }
)
ACTION_HINT_BY_CLASSIFICATION: Final[dict[str, dict[str, Any]]] = {
    "insufficient_trades": {
        "action": "increase_timeframe_or_extend_sample_window",
        "reason": "Observed candidates do not carry enough trades for reliable screening evidence.",
    },
    "no_oos_returns": {
        "action": "inspect_oos_return_coverage",
        "reason": "Observed artifacts show missing out-of-sample return evidence.",
    },
    "timeout": {
        "action": "inspect_screening_budget_and_worker_health",
        "reason": "Observed screening evidence points to timeout or budget exhaustion.",
    },
    "cost_sensitivity": {
        "action": "review_cost_assumptions",
        "reason": "Observed screening evidence is cost-assumption sensitive.",
    },
    "parameter_instability": {
        "action": "preserve_negative_result_for_unstable_parameter_region",
        "reason": "Observed evidence points to unstable neighboring parameters.",
    },
    "data_coverage_gap": {
        "action": "repair_data_coverage_before_research_action",
        "reason": "Observed artifacts show unavailable or incomplete market data coverage.",
    },
    "missing_screening_evidence": {
        "action": "repair_screening_evidence_instrumentation",
        "reason": "Attribution depends on missing screening evidence sidecars or drop reasons.",
    },
    "incomplete_policy_trace": {
        "action": "repair_policy_trace_instrumentation",
        "reason": "Policy diagnostics do not expose a complete read-only decision trace.",
    },
    "no_candidate_after_policy_filter": {
        "action": "inspect_policy_filter_inputs",
        "reason": "Policy evidence shows no candidate survived the read-only policy filter.",
    },
    "no_survivor_after_eval": {
        "action": "inspect_evaluation_survivor_gate",
        "reason": "Campaign or evaluation evidence completed without surviving candidates.",
    },
    "insufficient_oos_window": {
        "action": "collect_more_oos_window_evidence",
        "reason": "Observed artifacts show the out-of-sample window is too short.",
    },
    "missing_metric_field": {
        "action": "repair_metric_emission",
        "reason": "Existing screening records are missing required diagnostic metrics.",
    },
    "unsupported_failure_shape": {
        "action": "operator_review_unsupported_failure_shape",
        "reason": "The observed failure shape is explicit but not yet actionable by this taxonomy.",
    },
    "synthesis_gate_blocked": {
        "action": "inspect_synthesis_gate_evidence",
        "reason": "Existing research state reports a blocked synthesis gate.",
    },
    "data_coverage_unknown": {
        "action": "resolve_data_coverage_status",
        "reason": "Artifacts expose unknown data coverage rather than a deterministic pass/fail state.",
    },
    "identity_unresolved": {
        "action": "resolve_source_identity",
        "reason": "Artifacts indicate unresolved or fallback source identity.",
    },
    "policy_trace_inconsistent": {
        "action": "repair_policy_trace_consistency",
        "reason": "Policy counts in existing diagnostics are internally inconsistent.",
    },
    "strict_gate_rejection": {
        "action": "preserve_negative_result",
        "reason": "Observed metrics failed the current screening gate; no strategy change is implied.",
    },
    "missing_diagnostics": {
        "action": "inspect_screening_instrumentation",
        "reason": "No usable screening diagnostics were present for attribution.",
    },
    "unknown_screening_failure": {
        "action": "hold_no_action_until_evidence_improves",
        "reason": "Existing evidence is insufficient for a deterministic failure class.",
    },
}


def action_hint_for_classification(classification: str) -> dict[str, Any]:
    hint = ACTION_HINT_BY_CLASSIFICATION.get(
        classification,
        ACTION_HINT_BY_CLASSIFICATION["unknown_screening_failure"],
    )
    return {
        "classification": classification,
        "action": hint["action"],
        "reason": hint["reason"],
        "read_only": True,
        "mutates_routing": False,
        "mutates_strategy": False,
    }


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    if not isinstance(payload, dict):
        return None, "malformed"
    return payload, "present"


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "missing"
    events: list[dict[str, Any]] = []
    malformed = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    malformed = True
                    continue
                if isinstance(item, dict):
                    events.append(item)
                else:
                    malformed = True
    except OSError:
        return [], "malformed"
    return events, "malformed" if malformed and not events else "present"


def load_current_artifacts(
    *,
    root: Path = Path("."),
    artifact_paths: dict[str, Path] = ARTIFACT_PATHS,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    payloads: dict[str, Any] = {}
    statuses: dict[str, dict[str, str]] = {}
    for name, relative_path in artifact_paths.items():
        path = root / relative_path
        if name == "campaign_evidence_ledger":
            payload, status = _read_jsonl(path)
        else:
            payload, status = _read_json(path)
        payloads[name] = payload
        statuses[name] = {"path": relative_path.as_posix(), "status": status}
    return payloads, statuses


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _observe(
    observations: list[dict[str, Any]],
    *,
    source: str,
    raw_reason: str,
    classification: str | None = None,
    legacy_classification: str | None = None,
    subject: dict[str, Any] | None = None,
) -> None:
    classification = classification or REASON_TO_CLASSIFICATION.get(raw_reason)
    if classification is None:
        classification = "unknown_screening_failure"
    if legacy_classification is None:
        legacy_classification = LEGACY_REASON_TO_CLASSIFICATION.get(raw_reason)
    if legacy_classification is None and classification in LEGACY_CLASSIFICATIONS:
        legacy_classification = classification
    if legacy_classification is None:
        legacy_classification = "unknown_screening_failure"
    observations.append(
        {
            "source": source,
            "raw_reason": raw_reason,
            "classification": classification,
            "legacy_classification": legacy_classification,
            "subject": subject or {},
        }
    )


def _metric_gap_observations(
    observations: list[dict[str, Any]],
    *,
    source: str,
    metrics: dict[str, Any],
    subject: dict[str, Any],
) -> None:
    missing = sorted(field for field in SCREENING_METRIC_FIELDS if field not in metrics)
    if missing:
        _observe(
            observations,
            source=source,
            raw_reason="missing_metric_field",
            subject={**subject, "missing_metric_fields": missing},
        )


def _screening_evidence_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    candidates = _list_value(payload.get("candidates"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        subject = {
            "candidate_id": candidate.get("candidate_id"),
            "strategy_name": candidate.get("strategy_name"),
            "asset": candidate.get("asset"),
            "interval": candidate.get("interval"),
            "stage_result": candidate.get("stage_result"),
        }
        for reason in _list_value(candidate.get("failure_reasons")):
            _observe(
                observations,
                source="screening_evidence.candidates.failure_reasons",
                raw_reason=str(reason),
                subject=subject,
            )
        if candidate.get("identity_fallback_used") is True:
            _observe(
                observations,
                source="screening_evidence.candidates.identity_fallback_used",
                raw_reason="identity_fallback_used",
                subject=subject,
            )
        metrics = candidate.get("metrics")
        if isinstance(metrics, dict):
            _metric_gap_observations(
                observations,
                source="screening_evidence.candidates.metrics",
                metrics=metrics,
                subject=subject,
            )
        sampling = _dict_value(candidate.get("sampling"))
        if sampling.get("coverage_warning"):
            _observe(
                observations,
                source="screening_evidence.candidates.sampling",
                raw_reason="coverage_warning",
                subject=subject,
            )
        if candidate.get("stage_result") == "unknown" and not _list_value(
            candidate.get("failure_reasons")
        ):
            _observe(
                observations,
                source="screening_evidence.candidates.stage_result",
                raw_reason="unknown_stage_result",
                subject=subject,
            )
    summary = _dict_value(payload.get("summary"))
    for reason in _list_value(summary.get("dominant_failure_reasons")):
        _observe(
            observations,
            source="screening_evidence.summary.dominant_failure_reasons",
            raw_reason=str(reason),
        )
    return observations


def _filter_summary_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    reasons = _dict_value(payload.get("screening_rejection_reasons"))
    for reason, count in reasons.items():
        for _ in range(max(1, _safe_int(count, 1))):
            _observe(
                observations,
                source="run_filter_summary.screening_rejection_reasons",
                raw_reason=str(reason),
            )
    summary = _dict_value(payload.get("summary"))
    nested = _dict_value(summary.get("screening_rejection_reasons"))
    for reason, count in nested.items():
        for _ in range(max(1, _safe_int(count, 1))):
            _observe(
                observations,
                source="run_filter_summary.summary.screening_rejection_reasons",
                raw_reason=str(reason),
            )
    return observations


def _run_screening_candidate_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for candidate in _list_value(payload.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        reason = candidate.get("reason_code")
        if not reason and candidate.get("final_status") == "timed_out":
            reason = "timed_out"
        metrics = candidate.get("diagnostic_metrics")
        if isinstance(metrics, dict):
            _metric_gap_observations(
                observations,
                source="run_screening_candidates.candidates.diagnostic_metrics",
                metrics=metrics,
                subject={
                    "candidate_id": candidate.get("candidate_id"),
                    "strategy": candidate.get("strategy"),
                    "final_status": candidate.get("final_status"),
                },
            )
        if not reason and candidate.get("final_status") in {
            "rejected",
            "errored",
            "skipped",
        }:
            _observe(
                observations,
                source="run_screening_candidates.candidates.final_status",
                raw_reason="missing_screening_reason_code",
                subject={
                    "candidate_id": candidate.get("candidate_id"),
                    "strategy": candidate.get("strategy"),
                    "final_status": candidate.get("final_status"),
                },
            )
            continue
        if not reason:
            continue
        _observe(
            observations,
            source="run_screening_candidates.candidates.reason_code",
            raw_reason=str(reason),
            subject={
                "candidate_id": candidate.get("candidate_id"),
                "strategy": candidate.get("strategy"),
                "final_status": candidate.get("final_status"),
            },
        )
    return observations


def _empty_run_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    summary = _dict_value(payload.get("summary"))
    for reason in _list_value(summary.get("primary_drop_reasons")):
        _observe(
            observations,
            source="empty_run_diagnostics.summary.primary_drop_reasons",
            raw_reason=str(reason),
        )
    if (
        _safe_int(summary.get("evaluations_with_oos_daily_returns")) == 0
        and _safe_int(summary.get("evaluations_count")) > 0
    ):
        _observe(
            observations,
            source="empty_run_diagnostics.summary.evaluations_with_oos_daily_returns",
            raw_reason="no_oos_daily_returns",
        )
    for pair in _list_value(payload.get("pairs")):
        if not isinstance(pair, dict):
            continue
        reason = pair.get("drop_reason")
        if reason:
            _observe(
                observations,
                source="empty_run_diagnostics.pairs.drop_reason",
                raw_reason=str(reason),
                subject={"asset": pair.get("asset"), "interval": pair.get("interval")},
            )
    return observations


def _run_campaign_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    latest = _dict_value(payload.get("summary"))
    rejection_reasons = _dict_value(latest.get("screening_rejection_reasons"))
    for reason, count in rejection_reasons.items():
        for _ in range(max(1, _safe_int(count, 1))):
            _observe(
                observations,
                source="run_campaign.summary.screening_rejection_reasons",
                raw_reason=str(reason),
            )
    for batch in _list_value(payload.get("batches")):
        if not isinstance(batch, dict):
            continue
        reason = batch.get("reason_code") or batch.get("error_type")
        if reason:
            _observe(
                observations,
                source="run_campaign.batches.reason",
                raw_reason=str(reason),
                subject={"batch_id": batch.get("batch_id"), "status": batch.get("status")},
            )
    return observations


def _policy_filter_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    policy = _dict_value(payload.get("policy_summary"))
    action = policy.get("action")
    reason = policy.get("reason")
    candidate_count = _safe_int(policy.get("candidates_considered_count"))
    r4_r7 = _dict_value(policy.get("r4_r7"))
    r8_idle = _dict_value(policy.get("r8_idle"))
    if action == "idle_noop" and reason == "no_candidates" and candidate_count == 0:
        _observe(
            observations,
            source="policy_filter_diagnostics.policy_summary",
            raw_reason="no_policy_candidates",
            subject={"action": action, "reason": reason, "candidates": candidate_count},
        )
    primary = {str(item) for item in _list_value(payload.get("primary_explanations")) if str(item)}
    if "no_eligible_template" in primary:
        _observe(
            observations,
            source="policy_filter_diagnostics.primary_explanations",
            raw_reason="no_eligible_template",
            subject={"primary_explanations": sorted(primary)},
        )
    diagnostics = [row for row in _list_value(payload.get("diagnostics")) if isinstance(row, dict)]
    for row in diagnostics:
        diagnostic_id = row.get("diagnostic_id")
        if (
            diagnostic_id in {"r4_r7_filtering_counts", "r8_idle_status"}
            and row.get("status") == "unknown"
        ):
            _observe(
                observations,
                source="policy_filter_diagnostics.diagnostics",
                raw_reason=f"missing_{diagnostic_id}",
                classification="incomplete_policy_trace",
                subject={
                    "diagnostic_id": diagnostic_id,
                    "status": row.get("status"),
                },
            )
    surviving = _safe_int(r4_r7.get("surviving"))
    rejected = _safe_int(r4_r7.get("rejected"))
    if candidate_count and candidate_count != surviving + rejected:
        _observe(
            observations,
            source="policy_filter_diagnostics.policy_summary",
            raw_reason="policy_trace_inconsistent",
            subject={
                "candidates_considered_count": candidate_count,
                "r4_r7_surviving": surviving,
                "r4_r7_rejected": rejected,
            },
        )
    if (
        action == "idle_noop"
        and reason == "no_candidates"
        and (not r4_r7.get("present") or not r8_idle.get("present"))
    ):
        _observe(
            observations,
            source="policy_filter_diagnostics.policy_summary",
            raw_reason="incomplete_policy_trace",
            subject={"r4_r7": r4_r7, "r8_idle": r8_idle},
        )
    return observations


def _campaign_outcome_observations(
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    registry = _dict_value(artifacts.get("campaign_registry"))
    for cid, record in _dict_value(registry.get("campaigns")).items():
        if not isinstance(record, dict):
            continue
        outcome = record.get("outcome")
        if outcome in {"completed_no_survivor", "degenerate_no_survivors"}:
            _observe(
                observations,
                source="campaign_registry.campaigns.outcome",
                raw_reason=str(outcome),
                subject={"campaign_id": record.get("campaign_id") or cid},
            )
        for key in ("reason_code", "dominant_failure_mode"):
            reason = record.get(key)
            if reason and reason != "none":
                _observe(
                    observations,
                    source=f"campaign_registry.campaigns.{key}",
                    raw_reason=str(reason),
                    subject={"campaign_id": record.get("campaign_id") or cid},
                )
        for reason in _list_value(record.get("failure_reasons")):
            _observe(
                observations,
                source="campaign_registry.campaigns.failure_reasons",
                raw_reason=str(reason),
                subject={"campaign_id": record.get("campaign_id") or cid},
            )
    for event in _list_value(artifacts.get("campaign_evidence_ledger")):
        if not isinstance(event, dict):
            continue
        reason = event.get("reason_code") or event.get("dominant_failure_mode")
        if reason and reason != "none":
            _observe(
                observations,
                source="campaign_evidence_ledger.reason",
                raw_reason=str(reason),
                subject={"campaign_id": event.get("campaign_id")},
            )

    research_state = _dict_value(artifacts.get("research_state"))
    failure = _dict_value(research_state.get("failure_attribution"))
    if (
        failure.get("state") == "screening_evaluability_unattributed"
        and artifact_status["screening_evidence"]["status"] != "present"
    ):
        _observe(
            observations,
            source="research_state.failure_attribution",
            raw_reason="missing_screening_drop_reasons",
            legacy_classification="missing_diagnostics",
        )
    policy = _dict_value(research_state.get("policy_summary"))
    if research_state.get("policy_state") == "blocked_no_candidates" or (
        policy.get("action") == "idle_noop"
        and policy.get("reason") == "no_candidates"
        and _safe_int(policy.get("candidates_considered")) == 0
    ):
        _observe(
            observations,
            source="research_state.policy_summary",
            raw_reason="no_candidate_after_policy_filter",
            subject={
                "policy_state": research_state.get("policy_state"),
                "action": policy.get("action"),
                "reason": policy.get("reason"),
            },
        )
    synthesis_gate = research_state.get("synthesis_gate")
    if synthesis_gate in BLOCKED_SYNTHESIS_STATES:
        _observe(
            observations,
            source="research_state.synthesis_gate",
            raw_reason="synthesis_gate_blocked",
            subject={"synthesis_gate": synthesis_gate},
        )
    return observations


def collect_observations(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    if isinstance(artifacts.get("screening_evidence"), dict):
        observations.extend(_screening_evidence_observations(artifacts["screening_evidence"]))
    if isinstance(artifacts.get("run_filter_summary"), dict):
        observations.extend(_filter_summary_observations(artifacts["run_filter_summary"]))
    if isinstance(artifacts.get("run_screening_candidates"), dict):
        observations.extend(
            _run_screening_candidate_observations(artifacts["run_screening_candidates"])
        )
    if isinstance(artifacts.get("empty_run_diagnostics"), dict):
        observations.extend(_empty_run_observations(artifacts["empty_run_diagnostics"]))
    if isinstance(artifacts.get("run_campaign"), dict):
        observations.extend(_run_campaign_observations(artifacts["run_campaign"]))
    if isinstance(artifacts.get("policy_filter_diagnostics"), dict):
        observations.extend(_policy_filter_observations(artifacts["policy_filter_diagnostics"]))
    observations.extend(
        _campaign_outcome_observations(
            artifacts=artifacts,
            artifact_status=artifact_status,
        )
    )
    if not observations and all(
        artifact_status[name]["status"] != "present"
        for name in (
            "screening_evidence",
            "run_filter_summary",
            "run_screening_candidates",
            "empty_run_diagnostics",
        )
    ):
        _observe(
            observations,
            source="artifact_inventory",
            raw_reason="missing_screening_diagnostics",
            classification="missing_diagnostics",
        )
    if not observations:
        _observe(
            observations,
            source="artifact_inventory",
            raw_reason="no_screening_failure_reason_observed",
            classification="unknown_screening_failure",
        )
    return observations


def _classification_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(item["classification"]) for item in observations)
    raw_by_class: dict[str, Counter[str]] = {name: Counter() for name in CLASSIFICATIONS}
    sources_by_class: dict[str, set[str]] = {name: set() for name in CLASSIFICATIONS}
    examples_by_class: dict[str, list[dict[str, Any]]] = {name: [] for name in CLASSIFICATIONS}
    for item in observations:
        classification = str(item["classification"])
        if classification not in raw_by_class:
            classification = "unknown_screening_failure"
        raw_by_class[classification][str(item["raw_reason"])] += 1
        sources_by_class[classification].add(str(item["source"]))
        if len(examples_by_class[classification]) < 5:
            examples_by_class[classification].append(item)
    rows = []
    for classification in CLASSIFICATIONS:
        rows.append(
            {
                "classification": classification,
                "status": "observed" if counts.get(classification, 0) > 0 else "not_observed",
                "count": int(counts.get(classification, 0)),
                "raw_reasons": dict(sorted(raw_by_class[classification].items())),
                "sources": sorted(sources_by_class[classification]),
                "examples": examples_by_class[classification],
                "action_hint": action_hint_for_classification(classification),
            }
        )
    return rows


def _primary_classification(rows: list[dict[str, Any]]) -> str:
    observed = [row for row in rows if int(row["count"]) > 0]
    if not observed:
        return "unknown_screening_failure"
    priority = {name: index for index, name in enumerate(CLASSIFICATIONS)}
    observed.sort(
        key=lambda row: (
            -int(row["count"]),
            priority.get(str(row["classification"]), 999),
            str(row["classification"]),
        )
    )
    return str(observed[0]["classification"])


def build_screening_failure_attribution_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    observations = collect_observations(
        artifacts=artifacts,
        artifact_status=artifact_status,
    )
    rows = _classification_rows(observations)
    primary = _primary_classification(rows)
    counts = {row["classification"]: row["count"] for row in rows if int(row["count"]) > 0}
    legacy_unknown_count = sum(
        1
        for item in observations
        if item.get("legacy_classification") == "unknown_screening_failure"
    )
    unknown_count = sum(
        1 for item in observations if item.get("classification") == "unknown_screening_failure"
    )
    primary_action_hint = action_hint_for_classification(primary)
    observed_action_hints = [
        row["action_hint"] | {"count": row["count"]} for row in rows if int(row["count"]) > 0
    ]
    return {
        "schema_version": SCREENING_FAILURE_ATTRIBUTION_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "source_screening_evidence_path": artifact_status["screening_evidence"]["path"],
        "artifact_inputs": artifact_status,
        "summary": {
            "primary_classification": primary,
            "classification_counts": counts,
            "observation_count": len(observations),
            "legacy_unknown_observation_count": legacy_unknown_count,
            "unknown_observation_count": unknown_count,
            "unknown_observation_reduction": legacy_unknown_count - unknown_count,
            "attributed": primary not in {"missing_diagnostics", "unknown_screening_failure"},
            "primary_action_hint": primary_action_hint,
        },
        "classifications": rows,
        "observations": observations,
        "action_hints": observed_action_hints,
        "recommended_next_action": primary_action_hint["action"],
        "safety_invariants": {
            "runs_research": False,
            "runs_campaign_launcher": False,
            "mutates_screening_behavior": False,
            "mutates_campaign_artifacts": False,
            "writes_only_screening_failure_attribution_sidecars": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "frozen_contracts_unchanged": True,
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Screening Failure Attribution",
        "",
        "## Summary",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Source screening evidence: `{payload.get('source_screening_evidence_path')}`",
        f"- Primary classification: `{summary.get('primary_classification')}`",
        f"- Attributed: {summary.get('attributed')}",
        f"- Observation count: {summary.get('observation_count')}",
        (
            "- Unknown observations: "
            f"{summary.get('unknown_observation_count')} "
            f"(legacy {summary.get('legacy_unknown_observation_count')}, "
            f"reduction {summary.get('unknown_observation_reduction')})"
        ),
        f"- Classification counts: {json.dumps(summary.get('classification_counts') or {}, sort_keys=True)}",
        f"- Recommended next action: `{payload.get('recommended_next_action')}`",
        "",
        "## Classifications",
        *[
            (
                f"- `{row['classification']}`: {row['status']} "
                f"(count {row['count']}, action `{row['action_hint']['action']}`)"
            )
            for row in payload.get("classifications") or []
        ],
        "",
        "## Action Hints",
        *[
            (f"- `{hint['classification']}` -> `{hint['action']}`: " f"{hint['reason']}")
            for hint in payload.get("action_hints") or []
        ],
        "",
        "## Evidence Sources",
        *[
            f"- `{source}`"
            for source in sorted(
                {str(obs.get("source")) for obs in payload.get("observations") or []}
            )
        ],
        "",
        "## What To Expect Next",
        (
            "- Use the primary classification to choose between gate diagnostics, "
            "instrumentation repair, or an operator-gated research change."
        ),
        "",
    ]
    return "\n".join(lines)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def build_from_current_artifacts(
    *,
    root: Path = Path("."),
    report_json: Path = DEFAULT_REPORT_JSON_PATH,
    report_md: Path = DEFAULT_REPORT_MD_PATH,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    artifacts, statuses = load_current_artifacts(root=root)
    payload = build_screening_failure_attribution_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.screening_failure_attribution",
        description="Classify screening drop reasons from existing artifacts.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read current QRE sidecars and write screening failure attribution.",
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON_PATH)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.from_current_artifacts:
        parser.error("--from-current-artifacts is required")
    payload = build_from_current_artifacts(
        report_json=args.report_json,
        report_md=args.report_md,
    )
    print(
        "screening_failure_attribution: "
        f"primary={payload['summary']['primary_classification']} "
        f"observations={payload['summary']['observation_count']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ARTIFACT_PATHS",
    "CLASSIFICATIONS",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "SCREENING_FAILURE_ATTRIBUTION_SCHEMA_VERSION",
    "ACTION_HINT_BY_CLASSIFICATION",
    "action_hint_for_classification",
    "build_from_current_artifacts",
    "build_screening_failure_attribution_payload",
    "collect_observations",
    "load_current_artifacts",
    "main",
    "render_markdown_report",
]
