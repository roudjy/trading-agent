"""Read-only funnel census and threshold-distance audit for ADE-QRE-017F."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-017f-2026-06-26"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_funnel_threshold_audit"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_funnel_threshold_audit"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_funnel_threshold_audit.md"
_WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_funnel_threshold_audit/",
    "docs/governance/qre_funnel_threshold_audit.md",
)

_VALID_RECOMMENDATIONS: Final[tuple[str, ...]] = (
    "keep",
    "stratify",
    "move_to_later_stage",
    "replace",
    "remove_as_redundant",
    "insufficient_evidence_to_change",
)


def _research_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in _WRITE_PREFIXES):
        raise ValueError(
            "qre_funnel_threshold_audit: refusing write outside allowlist: "
            f"{path!r}"
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _bounded(value: Any, *, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _stable_hash(payload: Mapping[str, Any]) -> str:
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _screening_threshold_specs() -> dict[str, dict[str, Any]]:
    screening_criteria = _research_module("research.screening_criteria")
    return {
        "expectancy_above_zero": {
            "metric_key": "expectancy",
            "threshold": float(screening_criteria.EXPLORATORY_MIN_EXPECTANCY),
            "comparator": "gt",
            "threshold_source": "research.screening_criteria.EXPLORATORY_MIN_EXPECTANCY",
        },
        "profit_factor_at_or_above_floor": {
            "metric_key": "profit_factor",
            "threshold": float(screening_criteria.EXPLORATORY_MIN_PROFIT_FACTOR),
            "comparator": "ge",
            "threshold_source": "research.screening_criteria.EXPLORATORY_MIN_PROFIT_FACTOR",
        },
        "drawdown_within_limit": {
            "metric_key": "max_drawdown",
            "threshold": float(screening_criteria.EXPLORATORY_MAX_DRAWDOWN),
            "comparator": "le",
            "threshold_source": "research.screening_criteria.EXPLORATORY_MAX_DRAWDOWN",
        },
        "sufficient_trades": {
            "metric_key": "totaal_trades",
            "threshold": 10.0,
            "comparator": "ge",
            "threshold_source": (
                "research.screening_runtime engine.min_trades default when "
                "artifact-local threshold is absent"
            ),
        },
    }


def _signed_margin(actual: float, threshold: float, comparator: str) -> float:
    if comparator in {"gt", "ge"}:
        return actual - threshold
    if comparator in {"lt", "le"}:
        return threshold - actual
    raise ValueError(f"unsupported comparator: {comparator}")


def _relative_distance(actual: float, threshold: float) -> float | None:
    scale = max(abs(threshold), 1.0)
    return round(abs(actual - threshold) / scale, 6)


def _recommendation(
    *,
    criterion_id: str,
    pass_count: int,
    fail_count: int,
    failed_assets: set[str],
    passed_assets: set[str],
) -> str:
    if fail_count == 0:
        return "keep"
    if (
        criterion_id == "sufficient_trades"
        and pass_count > 0
        and fail_count > 0
        and len(failed_assets) >= 3
        and len(passed_assets) >= 1
    ):
        return "stratify"
    return "insufficient_evidence_to_change"


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _history_validation_status_counts(repo_root: Path) -> Counter[str]:
    history_root = repo_root / "research" / "history"
    counts: Counter[str] = Counter()
    if not history_root.is_dir():
        return counts
    for path in sorted(history_root.glob("*/run_candidates.v1.json")):
        payload = _read_json(path)
        for row in _list_of_mappings(payload.get("candidates")):
            validation = _mapping(row.get("validation"))
            status = _bounded(validation.get("evidence_status"))
            if status:
                counts[status] += 1
    return counts


def _funnel_summary(
    *,
    run_filter_summary: Mapping[str, Any],
    screening_evidence: Mapping[str, Any],
    run_campaign: Mapping[str, Any],
    campaign_level_evidence: Mapping[str, Any],
    history_validation_counts: Counter[str],
) -> dict[str, Any]:
    filter_summary = _mapping(run_filter_summary.get("summary"))
    screening_summary = _mapping(screening_evidence.get("summary"))
    campaign_summary = _mapping(run_campaign.get("summary"))
    campaign_screening = _mapping(campaign_level_evidence.get("screening_evidence"))
    campaign_screening_counts = _mapping(campaign_screening.get("counts"))

    sufficient_oos = int(screening_summary.get("sufficient_oos_evidence_candidates") or 0)
    validation_status_counts: Counter[str] = Counter()
    for row in _list_of_mappings(screening_evidence.get("candidates")):
        validation = _mapping(row.get("validation_evidence"))
        status = _bounded(validation.get("status"))
        if status:
            validation_status_counts[status] += 1

    failed_validation = sum(
        count
        for key, count in validation_status_counts.items()
        if key != "sufficient_oos_evidence"
    )
    campaign_failure_class = _bounded(
        _mapping(campaign_level_evidence.get("interpretation")).get("primary_limitation")
    )

    return {
        "raw_candidate_count": int(filter_summary.get("raw_candidate_count") or 0),
        "fit_allowed_count": int(filter_summary.get("fit_allowed_count") or 0),
        "fit_discouraged_count": int(filter_summary.get("fit_discouraged_count") or 0),
        "fit_blocked_count": int(filter_summary.get("fit_blocked_count") or 0),
        "deduplicated_candidate_count": int(
            filter_summary.get("deduplicated_candidate_count") or 0
        ),
        "duplicates_removed": int(filter_summary.get("duplicates_removed") or 0),
        "eligible_candidate_count": int(filter_summary.get("eligible_candidate_count") or 0),
        "eligibility_rejected_count": int(
            filter_summary.get("eligibility_rejected_count") or 0
        ),
        "screening_pass_count": int(screening_summary.get("passed_screening") or 0),
        "screening_reject_count": int(screening_summary.get("rejected_screening") or 0),
        "validation_completed_count": int(
            campaign_summary.get("validated_candidate_count")
            or campaign_screening_counts.get("passed_screening")
            or 0
        ),
        "validation_reject_count": int(failed_validation),
        "validation_error_count": int(campaign_summary.get("validation_error_count") or 0),
        "oos_accepted_count": int(sufficient_oos),
        "oos_rejected_or_missing_count": int(failed_validation),
        "evidence_complete_count": int(sufficient_oos),
        "evidence_incomplete_count": int(
            max(
                int(campaign_screening_counts.get("total_candidates") or 0) - sufficient_oos,
                0,
            )
        ),
        "validation_evidence_status_counts": _counter_dict(validation_status_counts),
        "historical_validation_evidence_status_counts": _counter_dict(
            history_validation_counts
        ),
        "campaign_primary_limitation": campaign_failure_class or "unavailable",
    }


def _candidate_stage_row(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = _mapping(row.get("metrics"))
    validation = _mapping(row.get("validation_evidence"))
    promotion_guard = _mapping(row.get("promotion_guard"))
    return {
        "candidate_id": _bounded(row.get("candidate_id")),
        "hypothesis_id": _bounded(row.get("hypothesis_id")),
        "strategy_name": _bounded(row.get("strategy_name")),
        "preset_name": _bounded(row.get("preset_name")),
        "asset": _bounded(row.get("asset")),
        "interval": _bounded(row.get("interval")),
        "stage_result": _bounded(row.get("stage_result")),
        "failure_reasons": [
            _bounded(item) for item in row.get("failure_reasons") or [] if _bounded(item)
        ],
        "promotion_blockers": [
            _bounded(item)
            for item in promotion_guard.get("blocked_by") or []
            if _bounded(item)
        ],
        "validation_evidence_status": _bounded(validation.get("status")) or "unknown",
        "oos_trade_count": validation.get("oos_trade_count"),
        "min_oos_trades": validation.get("min_oos_trades"),
        "metrics": {
            "expectancy": metrics.get("expectancy"),
            "profit_factor": metrics.get("profit_factor"),
            "max_drawdown": metrics.get("max_drawdown"),
            "totaal_trades": metrics.get("totaal_trades"),
            "trades_per_maand": metrics.get("trades_per_maand"),
            "win_rate": metrics.get("win_rate"),
        },
    }


def _criterion_rows(
    *,
    screening_evidence: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    specs = _screening_threshold_specs()
    candidate_rows: list[dict[str, Any]] = []
    aggregates: dict[str, dict[str, Any]] = {
        key: {
            "criterion_id": key,
            "metric_key": spec["metric_key"],
            "threshold_value": spec["threshold"],
            "threshold_source": spec["threshold_source"],
            "comparator": spec["comparator"],
            "observed_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "actual_values": [],
            "absolute_distances": [],
            "relative_distances": [],
            "failing_distances": [],
            "failed_assets": set(),
            "passed_assets": set(),
            "by_preset": Counter(),
            "by_interval": Counter(),
            "by_hypothesis": Counter(),
            "by_asset": Counter(),
            "failed_by_preset": Counter(),
        }
        for key, spec in specs.items()
    }

    failure_reason_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()

    for row in _list_of_mappings(screening_evidence.get("candidates")):
        metrics = _mapping(row.get("metrics"))
        asset = _bounded(row.get("asset"))
        preset_name = _bounded(row.get("preset_name"))
        interval = _bounded(row.get("interval"))
        hypothesis_id = _bounded(row.get("hypothesis_id"))
        for reason in row.get("failure_reasons") or []:
            text = _bounded(reason)
            if text:
                failure_reason_counts[text] += 1
        for blocker in _mapping(row.get("promotion_guard")).get("blocked_by") or []:
            text = _bounded(blocker)
            if text:
                blocker_counts[text] += 1

        for criterion_id, spec in specs.items():
            actual = _num(metrics.get(spec["metric_key"]))
            if actual is None:
                continue
            threshold = float(spec["threshold"])
            signed_margin = _signed_margin(actual, threshold, str(spec["comparator"]))
            abs_distance = round(abs(actual - threshold), 6)
            rel_distance = _relative_distance(actual, threshold)
            passed = signed_margin > 0.0 if spec["comparator"] == "gt" else signed_margin >= 0.0
            row_payload = {
                "criterion_id": criterion_id,
                "candidate_id": _bounded(row.get("candidate_id")),
                "asset": asset,
                "preset_name": preset_name,
                "interval": interval,
                "hypothesis_id": hypothesis_id,
                "actual_value": actual,
                "threshold_value": threshold,
                "comparator": spec["comparator"],
                "signed_margin": round(signed_margin, 6),
                "absolute_threshold_distance": abs_distance,
                "relative_threshold_distance": rel_distance,
                "passed": passed,
                "failure_reason_present": not passed,
            }
            candidate_rows.append(row_payload)

            agg = aggregates[criterion_id]
            agg["observed_count"] += 1
            agg["actual_values"].append(actual)
            agg["absolute_distances"].append(abs_distance)
            if rel_distance is not None:
                agg["relative_distances"].append(rel_distance)
            agg["by_preset"][preset_name or "unknown"] += 1
            agg["by_interval"][interval or "unknown"] += 1
            agg["by_hypothesis"][hypothesis_id or "unknown"] += 1
            agg["by_asset"][asset or "unknown"] += 1
            if passed:
                agg["pass_count"] += 1
                if asset:
                    agg["passed_assets"].add(asset)
            else:
                agg["fail_count"] += 1
                agg["failing_distances"].append(abs_distance)
                agg["failed_by_preset"][preset_name or "unknown"] += 1
                if asset:
                    agg["failed_assets"].add(asset)

    criterion_rows: list[dict[str, Any]] = []
    for criterion_id, agg in sorted(aggregates.items()):
        actual_values = list(agg["actual_values"])
        absolute_distances = list(agg["absolute_distances"])
        relative_distances = list(agg["relative_distances"])
        recommendation = _recommendation(
            criterion_id=criterion_id,
            pass_count=int(agg["pass_count"]),
            fail_count=int(agg["fail_count"]),
            failed_assets=set(agg["failed_assets"]),
            passed_assets=set(agg["passed_assets"]),
        )
        if recommendation not in _VALID_RECOMMENDATIONS:
            raise ValueError((criterion_id, recommendation))
        criterion_rows.append(
            {
                "criterion_id": criterion_id,
                "metric_key": agg["metric_key"],
                "threshold_value": agg["threshold_value"],
                "threshold_source": agg["threshold_source"],
                "comparator": agg["comparator"],
                "observed_count": int(agg["observed_count"]),
                "pass_count": int(agg["pass_count"]),
                "fail_count": int(agg["fail_count"]),
                "actual_value_summary": {
                    "min": min(actual_values) if actual_values else None,
                    "median": median(actual_values) if actual_values else None,
                    "max": max(actual_values) if actual_values else None,
                },
                "absolute_threshold_distance_summary": {
                    "min": min(absolute_distances) if absolute_distances else None,
                    "median": median(absolute_distances) if absolute_distances else None,
                    "max": max(absolute_distances) if absolute_distances else None,
                },
                "relative_threshold_distance_summary": {
                    "min": min(relative_distances) if relative_distances else None,
                    "median": median(relative_distances) if relative_distances else None,
                    "max": max(relative_distances) if relative_distances else None,
                },
                "stratification": {
                    "by_preset": _counter_dict(agg["by_preset"]),
                    "failed_by_preset": _counter_dict(agg["failed_by_preset"]),
                    "by_interval": _counter_dict(agg["by_interval"]),
                    "by_hypothesis": _counter_dict(agg["by_hypothesis"]),
                    "by_asset": _counter_dict(agg["by_asset"]),
                    "regime": "unavailable_in_current_artifacts",
                    "universe": "unavailable_in_current_artifacts",
                },
                "recommendation": recommendation,
            }
        )

    return (
        criterion_rows,
        sorted(
            candidate_rows,
            key=lambda row: (
                str(row["criterion_id"]),
                str(row["asset"]),
                str(row["candidate_id"]),
            ),
        ),
        _counter_dict(failure_reason_counts),
        _counter_dict(blocker_counts),
    )


def _trend_break_rule_rows(
    *,
    run_screening_candidates: Mapping[str, Any],
) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for candidate in _list_of_mappings(run_screening_candidates.get("candidates")):
        diagnostics = candidate.get("sample_diagnostics")
        if not isinstance(diagnostics, list) or not diagnostics:
            continue
        summary = _mapping(candidate.get("sample_diagnostics_summary"))
        best_index = int(summary.get("best_sample_index") or 0)
        if best_index < 0 or best_index >= len(diagnostics):
            best_index = 0
        best = diagnostics[best_index] if isinstance(diagnostics[best_index], Mapping) else {}
        comparison = _mapping(best.get("trend_break_bar_path_threshold_comparison_summary"))
        rules = _mapping(comparison.get("rules"))
        matched_trade_count = int(comparison.get("matched_trade_count") or 0)
        for rule_name, result_any in sorted(rules.items()):
            result = _mapping(result_any)
            row = totals.setdefault(
                str(rule_name),
                {
                    "rule_id": str(rule_name),
                    "matched_trade_count": 0,
                    "asset_count": 0,
                    "triggered_trade_count": 0,
                    "triggered_trend_break_trades": 0,
                    "triggered_pullback_resolved_trades": 0,
                    "triggered_other_trades": 0,
                    "avoided_loss": 0.0,
                    "sacrificed_profit": 0.0,
                    "other_pnl_delta": 0.0,
                    "net_pnl_delta": 0.0,
                },
            )
            row["matched_trade_count"] += matched_trade_count
            row["asset_count"] += 1
            for key in (
                "triggered_trade_count",
                "triggered_trend_break_trades",
                "triggered_pullback_resolved_trades",
                "triggered_other_trades",
            ):
                row[key] += int(result.get(key) or 0)
            for key in (
                "avoided_loss",
                "sacrificed_profit",
                "other_pnl_delta",
                "net_pnl_delta",
            ):
                row[key] += float(result.get(key) or 0.0)
    return [
        {
            "rule_id": row["rule_id"],
            "matched_trade_count": int(row["matched_trade_count"]),
            "asset_count": int(row["asset_count"]),
            "triggered_trade_count": int(row["triggered_trade_count"]),
            "triggered_trend_break_trades": int(row["triggered_trend_break_trades"]),
            "triggered_pullback_resolved_trades": int(
                row["triggered_pullback_resolved_trades"]
            ),
            "triggered_other_trades": int(row["triggered_other_trades"]),
            "avoided_loss": round(float(row["avoided_loss"]), 6),
            "sacrificed_profit": round(float(row["sacrificed_profit"]), 6),
            "other_pnl_delta": round(float(row["other_pnl_delta"]), 6),
            "net_pnl_delta": round(float(row["net_pnl_delta"]), 6),
        }
        for row in sorted(totals.values(), key=lambda item: item["rule_id"])
    ]


def collect_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    generated_at_utc = frozen_utc or _utcnow()
    run_filter_summary = _read_json(repo_root / "research" / "run_filter_summary_latest.v1.json")
    screening_evidence = _read_json(repo_root / "research" / "screening_evidence_latest.v1.json")
    run_campaign = _read_json(repo_root / "research" / "run_campaign_latest.v1.json")
    run_screening_candidates = _read_json(
        repo_root / "research" / "run_screening_candidates_latest.v1.json"
    )
    campaign_level_evidence = _read_json(
        repo_root / "research" / "campaign_level_evidence_latest.v1.json"
    )

    (
        criterion_rows,
        candidate_criterion_rows,
        failure_reason_counts,
        promotion_blocker_counts,
    ) = _criterion_rows(screening_evidence=screening_evidence)
    history_validation_counts = _history_validation_status_counts(repo_root)
    funnel_summary = _funnel_summary(
        run_filter_summary=run_filter_summary,
        screening_evidence=screening_evidence,
        run_campaign=run_campaign,
        campaign_level_evidence=campaign_level_evidence,
        history_validation_counts=history_validation_counts,
    )
    stage_rows = [
        _candidate_stage_row(row)
        for row in sorted(
            _list_of_mappings(screening_evidence.get("candidates")),
            key=lambda item: (
                str(item.get("asset") or ""),
                str(item.get("candidate_id") or ""),
            ),
        )
    ]
    trend_break_rule_rows = _trend_break_rule_rows(
        run_screening_candidates=run_screening_candidates
    )
    snapshot_id = _stable_hash(
        {
            "generated_at_utc": generated_at_utc,
            "funnel_summary": funnel_summary,
            "criterion_rows": criterion_rows,
            "trend_break_rule_rows": trend_break_rule_rows,
        }
    )
    return {
        "generated_at_utc": generated_at_utc,
        "module_version": MODULE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "snapshot_identity": {
            "snapshot_id": snapshot_id,
            "source_artifacts": {
                "run_filter_summary": "research/run_filter_summary_latest.v1.json",
                "screening_evidence": "research/screening_evidence_latest.v1.json",
                "run_campaign": "research/run_campaign_latest.v1.json",
                "run_screening_candidates": "research/run_screening_candidates_latest.v1.json",
                "campaign_level_evidence": "research/campaign_level_evidence_latest.v1.json",
            },
        },
        "funnel_counts": funnel_summary,
        "criterion_rows": criterion_rows,
        "candidate_criterion_rows": candidate_criterion_rows,
        "stage_candidate_rows": stage_rows,
        "rejection_reason_counts": {
            "failure_reasons": failure_reason_counts,
            "promotion_blockers": promotion_blocker_counts,
            "eligibility_rejection_reasons": {
                str(key): int(value)
                for key, value in sorted(
                    _mapping(run_filter_summary.get("summary"))
                    .get("eligibility_rejection_reasons", {})
                    .items()
                )
            },
        },
        "trend_break_threshold_rule_rows": trend_break_rule_rows,
        "summary": {
            "criteria_count": len(criterion_rows),
            "candidate_row_count": len(candidate_criterion_rows),
            "criterion_recommendation_count": len(
                [row for row in criterion_rows if row.get("recommendation")]
            ),
            "all_criteria_have_exactly_one_recommendation": all(
                row.get("recommendation") in _VALID_RECOMMENDATIONS
                for row in criterion_rows
            ),
            "final_recommendation": "funnel_threshold_audit_ready",
            "exact_next_action": (
                "use criterion recommendations as advisory evidence only; "
                "do not change thresholds in ADE-QRE-017F"
            ),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_thresholds": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(snapshot: Mapping[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    counts = _mapping(snapshot.get("funnel_counts"))
    criterion_rows = snapshot.get("criterion_rows")
    if not isinstance(criterion_rows, list):
        criterion_rows = []
    lines = [
        "# QRE Funnel Census and Threshold-Distance Audit",
        "",
        "## 1. Summary",
        f"- snapshot_id: `{_mapping(snapshot.get('snapshot_identity')).get('snapshot_id', '')}`",
        f"- raw_candidate_count: {counts.get('raw_candidate_count')}",
        f"- screening_pass_count: {counts.get('screening_pass_count')}",
        f"- screening_reject_count: {counts.get('screening_reject_count')}",
        f"- validation_completed_count: {counts.get('validation_completed_count')}",
        f"- oos_accepted_count: {counts.get('oos_accepted_count')}",
        f"- campaign_primary_limitation: {counts.get('campaign_primary_limitation')}",
        f"- final_recommendation: {summary.get('final_recommendation')}",
        "",
        "## 2. Criterion recommendations",
        "| Criterion | Metric | Threshold | Pass | Fail | Recommendation |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in criterion_rows:
        if not isinstance(row, Mapping):
            continue
        threshold_value = row.get("threshold_value")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("criterion_id") or ""),
                    str(row.get("metric_key") or ""),
                    "" if threshold_value is None else str(threshold_value),
                    str(row.get("pass_count") or 0),
                    str(row.get("fail_count") or 0),
                    str(row.get("recommendation") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path = ARTIFACT_DIR,
    doc_path: Path = DOC_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    base = output_dir if output_dir.is_absolute() else repo_root / output_dir
    markdown = doc_path if doc_path.is_absolute() else repo_root / doc_path
    base.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    timestamp = str(snapshot["generated_at_utc"]).replace(":", "-")
    latest = base / "latest.json"
    timestamped = base / f"{timestamp}.json"
    history = base / "history.jsonl"
    payload = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
    summary_md = render_operator_summary(snapshot)

    for target in (latest, timestamped, history, markdown):
        _validate_write_target(target)

    def _atomic_write(target: Path, content: str) -> None:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(target.parent), encoding="utf-8"
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, target)

    _atomic_write(latest, payload)
    _atomic_write(timestamped, payload)
    _atomic_write(markdown, summary_md)
    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest),
        "timestamped": _rel(timestamped),
        "history": _rel(history),
        "doc": _rel(markdown),
    }


def read_latest_snapshot(
    *,
    output_dir: Path = ARTIFACT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any] | None:
    latest = output_dir if output_dir.is_absolute() else repo_root / output_dir
    latest = latest / "latest.json"
    if not latest.is_file():
        return None
    return _read_json(latest)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_funnel_threshold_audit")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        snapshot = read_latest_snapshot()
        if snapshot is None:
            snapshot = {
                "report_kind": REPORT_KIND,
                "status": "missing_latest_snapshot",
                "path": _rel(ARTIFACT_LATEST),
            }
        print(json.dumps(snapshot, sort_keys=True, indent=2))
        return 0

    snapshot = collect_snapshot(repo_root=REPO_ROOT, frozen_utc=args.frozen_utc)
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot, repo_root=REPO_ROOT)
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
