from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from reporting import qre_controlled_discovery_grid_analysis as grid_analysis
from research import production_discovery_catalog as catalog
from research import qre_real_basket_evidence_coverage as coverage


REPORT_KIND: Final[str] = "qre_discovery_basket_grid_evidence_materialization"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_discovery_basket_grid_evidence_materialization")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_discovery_basket_grid_evidence_materialization/"
GRID_RUNS_DIR: Final[Path] = Path("research/controlled_discovery_grid_runs")
METRIC_AUDIT_PATH: Final[Path] = Path(
    "logs/qre_controlled_discovery_metric_consistency_audit/latest.json"
)
PRESET_EXECUTABILITY_PATH: Final[Path] = Path(
    "logs/qre_controlled_discovery_preset_executability/latest.json"
)
SURVIVOR_STAGE_PATH: Final[Path] = Path(
    "logs/qre_controlled_discovery_survivor_stage_attribution/latest.json"
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.is_file():
        return [], "grid_artifact_missing"
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                rows.append(payload)
    except (OSError, json.JSONDecodeError):
        return [], "grid_artifact_missing"
    return rows, None


def _latest_result_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest_by_sequence: dict[int, dict[str, Any]] = {}
    ordered_sequences: list[int] = []
    for row in rows:
        sequence_number = int(row.get("sequence_number") or 0)
        if sequence_number not in latest_by_sequence:
            ordered_sequences.append(sequence_number)
        latest_by_sequence[sequence_number] = dict(row)
    return [latest_by_sequence[sequence_number] for sequence_number in ordered_sequences]


def _load_optional_rows(path: Path, field: str) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get(field) if isinstance(payload, Mapping) else None
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def _audit_indexes(repo_root: Path) -> dict[str, dict[tuple[str, str], dict[str, Any]]]:
    metric_rows = _load_optional_rows(repo_root / METRIC_AUDIT_PATH, "rows")
    preset_rows = _load_optional_rows(repo_root / PRESET_EXECUTABILITY_PATH, "rows")
    survivor_rows = _load_optional_rows(repo_root / SURVIVOR_STAGE_PATH, "rows")
    return {
        "metric": {
            (str(row.get("instrument_symbol") or ""), str(row.get("behavior_preset_id") or "")): row
            for row in metric_rows
        },
        "preset": {
            (str(row.get("instrument_symbol") or ""), str(row.get("behavior_preset_id") or "")): row
            for row in preset_rows
        },
        "survivor": {
            (str(row.get("instrument_symbol") or ""), str(row.get("behavior_preset_id") or "")): row
            for row in survivor_rows
        },
    }


def _coverage_indexes(
    row: Mapping[str, Any],
) -> tuple[set[str], set[str], str, str, set[str]]:
    symbol = str(row.get("symbol") or "")
    provider_symbol = str(row.get("provider_symbol") or "")
    preset_id = str(row.get("preset_id") or "")
    hypothesis_id = str(row.get("hypothesis_id") or "")
    aliases = {symbol}
    if provider_symbol:
        aliases.add(provider_symbol)
    timeframes = {str(value) for value in row.get("timeframes") or [] if str(value)}
    return aliases, set(), preset_id, hypothesis_id, timeframes


def _match_reasons(
    basket_row: Mapping[str, Any],
    grid_row: Mapping[str, Any],
    *,
    basket_aliases: Sequence[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    basket_symbol = str(basket_row.get("symbol") or "")
    provider_symbol = str(basket_row.get("provider_symbol") or "")
    preset_id = str(basket_row.get("preset_id") or "")
    hypothesis_id = str(basket_row.get("hypothesis_id") or "")
    basket_timeframes = {str(value) for value in basket_row.get("timeframes") or [] if str(value)}
    grid_symbol = str(grid_row.get("instrument_symbol") or "")
    grid_provider_symbol = str(grid_row.get("primary_data_provider_symbol") or "")
    grid_aliases = {str(value) for value in grid_row.get("provider_symbol_aliases") or [] if str(value)}

    if str(grid_row.get("behavior_preset_id") or "") != preset_id:
        reasons.append("preset_mismatch")
    if basket_timeframes and str(grid_row.get("timeframe") or "") not in basket_timeframes:
        reasons.append("timeframe_mismatch")
    grid_hypothesis = str(grid_row.get("hypothesis_id") or "")
    if hypothesis_id and grid_hypothesis and grid_hypothesis != hypothesis_id:
        reasons.append("hypothesis_mismatch")

    symbol_match = False
    if basket_symbol and basket_symbol == grid_symbol:
        symbol_match = True
    elif provider_symbol and provider_symbol == grid_symbol:
        symbol_match = True
        reasons.append("matched_via_provider_symbol")
    elif provider_symbol and provider_symbol == grid_provider_symbol:
        symbol_match = True
        reasons.append("matched_via_primary_provider_symbol")
    elif provider_symbol and provider_symbol in grid_aliases:
        symbol_match = True
        reasons.append("matched_via_grid_alias")
    elif basket_aliases and any(alias == grid_symbol for alias in basket_aliases):
        symbol_match = True
        reasons.append("matched_basket_alias_to_grid_symbol")
    elif basket_aliases and any(alias == grid_provider_symbol for alias in basket_aliases):
        symbol_match = True
        reasons.append("matched_basket_alias_to_grid_provider_symbol")
    elif basket_aliases and any(alias in grid_aliases for alias in basket_aliases):
        symbol_match = True
        reasons.append("matched_alias_to_alias")
    elif basket_symbol and basket_symbol == grid_provider_symbol:
        symbol_match = True
        reasons.append("matched_symbol_to_provider_symbol")
    elif basket_symbol and basket_symbol in grid_aliases:
        symbol_match = True
        reasons.append("matched_symbol_to_grid_alias")
    if not symbol_match:
        reasons.append("symbol_mismatch")
    return (not any(reason.endswith("mismatch") for reason in reasons), reasons)


def _screening_status(matched_rows: Sequence[Mapping[str, Any]], visible: bool) -> str:
    if visible:
        return "visible_in_readiness_loop"
    if not matched_rows:
        return "missing"
    if any(str(row.get("status") or "") == "completed" for row in matched_rows):
        return "grid_only"
    return "grid_blocked"


def _oos_status(matched_rows: Sequence[Mapping[str, Any]]) -> str:
    if not matched_rows:
        return "missing"
    if any(str(row.get("outcome_class") or "") == "sufficient_oos_evidence" for row in matched_rows):
        return "sufficient_oos_evidence_present"
    if any(str(row.get("blocker_class") or "") == "no_oos_evidence" for row in matched_rows):
        return "no_oos_evidence"
    if any(str(row.get("status") or "") == "completed" for row in matched_rows):
        return "completed_without_sufficient_oos"
    return "blocked_or_skipped"


def _candidate_lineage_status(basket_row: Mapping[str, Any]) -> str:
    counts = basket_row.get("evidence_counts") or {}
    candidate_rows = int(counts.get("candidate_lineage_rows") or 0)
    campaign_rows = int(counts.get("campaign_lineage_rows") or 0)
    if candidate_rows > 0 and campaign_rows > 0:
        return "visible"
    if candidate_rows > 0:
        return "candidate_visible_campaign_missing"
    if campaign_rows > 0:
        return "campaign_visible_candidate_missing"
    return "missing"


def _local_metric_status(rows: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    status = "unknown_fail_closed"
    for row in rows:
        diagnostic = grid_analysis._derive_row_diagnostics(dict(row))
        current_status = str(diagnostic.get("metric_consistency_status") or "unknown_fail_closed")
        current_warnings = [str(value) for value in diagnostic.get("metric_consistency_warnings") or []]
        if current_status == "inconsistent":
            return "metric_inconsistent", current_warnings
        if current_status == "consistent":
            status = "clean_consistent"
        warnings.extend(current_warnings)
    return status, sorted(set(warnings))


def _exact_blocker_category(
    *,
    basket_row: Mapping[str, Any],
    matched_rows: Sequence[Mapping[str, Any]],
    join_failure_reason: str | None,
    metric_status: str,
    preset_classification: str | None,
    survivor_stage: str | None,
) -> str:
    if join_failure_reason == "no_grid_run_found":
        return "no_grid_run_found"
    if join_failure_reason == "grid_artifact_missing":
        return "grid_artifact_missing"
    if str(basket_row.get("source_identity_status") or "") == "candidate_alias_only":
        return "source_identity_blocked"
    if metric_status == "metric_inconsistent":
        return "metric_inconsistent"
    if preset_classification in {
        "mapping_missing",
        "preset_not_executable",
        "region_constraint_mismatch",
        "asset_class_constraint_mismatch",
        "timeframe_constraint_mismatch",
        "provider_symbol_unresolved",
        "source_identity_blocked",
        "unsupported_combination",
    }:
        return preset_classification
    if survivor_stage and survivor_stage not in {
        "degenerate_legitimate_no_survivors",
        "unknown_fail_closed",
    }:
        return survivor_stage
    if any(str(row.get("blocker_class") or "") == "degenerate_no_survivors" for row in matched_rows):
        return "degenerate_no_survivors"
    if any(str(row.get("outcome_class") or "") == "sufficient_oos_evidence" for row in matched_rows):
        if any(grid_analysis._derive_row_diagnostics(dict(row)).get("criteria_failure_classes") for row in matched_rows):
            return "criteria_failed"
        return "sufficient_oos_but_not_promotion_ready"
    if any(str(row.get("blocker_class") or "") == "no_oos_evidence" for row in matched_rows):
        return "no_oos_evidence"
    if join_failure_reason == "join_key_mismatch":
        return "join_key_mismatch"
    if join_failure_reason == "grid_row_match_not_found":
        return "grid_row_match_not_found"
    if int((basket_row.get("evidence_counts") or {}).get("candidate_lineage_rows") or 0) == 0:
        return "candidate_lineage_missing"
    if int((basket_row.get("evidence_counts") or {}).get("campaign_lineage_rows") or 0) == 0:
        return "campaign_lineage_missing"
    if matched_rows:
        return "evidence_complete_or_near_complete"
    return "unknown_fail_closed"


def _next_action(blocker: str, *, readiness_adapter_gap: bool) -> str:
    if readiness_adapter_gap:
        return "bridge_grid_evidence_into_readiness_surfaces"
    mapping = {
        "no_grid_run_found": "run_controlled_discovery_grid",
        "grid_artifact_missing": "restore_grid_run_artifacts",
        "join_key_mismatch": "inspect_join_key_mapping",
        "grid_row_match_not_found": "inspect_basket_to_grid_mapping",
        "source_identity_blocked": "require_identity_resolution",
        "metric_inconsistent": "inspect_metric_consistency",
        "preset_not_executable": "keep_blocked",
        "mapping_missing": "classify_mapping_gap",
        "region_constraint_mismatch": "keep_blocked",
        "asset_class_constraint_mismatch": "keep_blocked",
        "timeframe_constraint_mismatch": "keep_blocked",
        "provider_symbol_unresolved": "require_identity_resolution",
        "unsupported_combination": "keep_blocked",
        "degenerate_no_survivors": "inspect_survivor_stage",
        "criteria_failed": "review_criteria_failures",
        "no_oos_evidence": "collect_more_evidence",
        "candidate_lineage_missing": "materialize_candidate_lineage",
        "campaign_lineage_missing": "materialize_campaign_lineage",
        "evidence_complete_or_near_complete": "eligible_for_readonly_routing_review",
    }
    return mapping.get(blocker, "keep_fail_closed")


def _scan_grid_runs(repo_root: Path) -> tuple[list[dict[str, Any]], int, int, int]:
    root = repo_root / GRID_RUNS_DIR
    if not root.is_dir():
        return [], 0, 0, 0
    run_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    all_rows: list[dict[str, Any]] = []
    artifact_failures = 0
    for run_dir in run_dirs:
        rows, error = _load_jsonl(run_dir / "combination_results.v1.jsonl")
        if error:
            artifact_failures += 1
            continue
        for row in _latest_result_rows(rows):
            all_rows.append(
                {
                    **row,
                    "_run_id": run_dir.name,
                    "_run_dir": run_dir.as_posix(),
                }
            )
    all_rows.sort(
        key=lambda row: (
            str(row.get("_run_id") or ""),
            int(row.get("sequence_number") or 0),
        )
    )
    return all_rows, len(run_dirs), len(all_rows), artifact_failures


def build_discovery_basket_grid_evidence_materialization(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    base = coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    basket_rows = base.get("rows")
    if not isinstance(basket_rows, list):
        basket_rows = []
    grid_rows, run_count, grid_row_count, artifact_failures = _scan_grid_runs(repo_root)
    audit_indexes = _audit_indexes(repo_root)
    source_identity_index = {
        str(row.get("instrument_symbol") or ""): row for row in catalog.source_identity_diagnostics()
    }

    materialized_rows: list[dict[str, Any]] = []
    next_action_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()

    for basket_row in basket_rows:
        if not isinstance(basket_row, Mapping):
            continue
        join_keys_attempted = [
            "symbol+preset+timeframe+hypothesis",
            "provider_symbol+preset+timeframe+hypothesis",
            "symbol_to_grid_alias+preset+timeframe+hypothesis",
            "provider_symbol_to_grid_alias+preset+timeframe+hypothesis",
        ]
        matched_rows: list[dict[str, Any]] = []
        saw_same_preset = False
        join_failure_reason: str | None = None
        if run_count == 0:
            join_failure_reason = "no_grid_run_found"
        elif artifact_failures and not grid_rows:
            join_failure_reason = "grid_artifact_missing"
        else:
            saw_same_symbol_or_provider = False
            basket_aliases = [
                str(value)
                for value in (
                    source_identity_index.get(str(basket_row.get("symbol") or ""), {}).get("candidate_aliases")
                    or []
                )
                if str(value)
            ]
            for grid_row in grid_rows:
                if str(grid_row.get("behavior_preset_id") or "") == str(basket_row.get("preset_id") or ""):
                    saw_same_preset = True
                basket_symbol = str(basket_row.get("symbol") or "")
                basket_provider = str(basket_row.get("provider_symbol") or "")
                grid_symbol = str(grid_row.get("instrument_symbol") or "")
                grid_provider = str(grid_row.get("primary_data_provider_symbol") or "")
                grid_aliases = {str(value) for value in grid_row.get("provider_symbol_aliases") or [] if str(value)}
                if basket_symbol in {grid_symbol, grid_provider} or basket_provider in {
                    grid_symbol,
                    grid_provider,
                }:
                    saw_same_symbol_or_provider = True
                elif basket_symbol and basket_symbol in grid_aliases:
                    saw_same_symbol_or_provider = True
                elif basket_provider and basket_provider in grid_aliases:
                    saw_same_symbol_or_provider = True
                elif any(alias in {grid_symbol, grid_provider} for alias in basket_aliases):
                    saw_same_symbol_or_provider = True
                elif any(alias in grid_aliases for alias in basket_aliases):
                    saw_same_symbol_or_provider = True
                matched, reasons = _match_reasons(
                    basket_row,
                    grid_row,
                    basket_aliases=basket_aliases,
                )
                if matched:
                    matched_rows.append(
                        {
                            "run_id": str(grid_row.get("_run_id") or ""),
                            "sequence_number": int(grid_row.get("sequence_number") or 0),
                            "instrument_symbol": str(grid_row.get("instrument_symbol") or ""),
                            "behavior_preset_id": str(grid_row.get("behavior_preset_id") or ""),
                            "status": str(grid_row.get("status") or ""),
                            "outcome_class": str(grid_row.get("outcome_class") or ""),
                            "blocker_class": str(grid_row.get("blocker_class") or ""),
                            "provider_symbol_status": str(grid_row.get("provider_symbol_status") or ""),
                            "source_identity_status": str(grid_row.get("source_identity_status") or ""),
                            "primary_data_provider_symbol": grid_row.get("primary_data_provider_symbol"),
                            "provider_symbol_aliases": list(grid_row.get("provider_symbol_aliases") or []),
                            "result_path": grid_row.get("result_path"),
                            "trades_total": grid_row.get("trades_total"),
                            "oos_trades": grid_row.get("oos_trades"),
                            "hd_trades": grid_row.get("hd_trades"),
                            "criteria_status": grid_row.get("criteria_status"),
                            "join_reasons": reasons,
                        }
                    )
            if not matched_rows:
                join_failure_reason = (
                    "join_key_mismatch"
                    if (saw_same_preset or saw_same_symbol_or_provider)
                    else "grid_row_match_not_found"
                )

        matched_rows.sort(key=lambda row: (str(row["run_id"]), int(row["sequence_number"])))
        evidence_visible = bool(
            int((basket_row.get("evidence_counts") or {}).get("screening_rows") or 0) > 0
            or int(
                (basket_row.get("validation_evidence_status_counts") or {}).get("sufficient_oos_evidence")
                or 0
            )
            > 0
        )
        readiness_adapter_gap = bool(matched_rows) and not evidence_visible
        basket_symbol = str(basket_row.get("symbol") or "")
        basket_preset = str(basket_row.get("preset_id") or "")
        metric_row = audit_indexes["metric"].get((basket_symbol, basket_preset))
        if metric_row:
            metric_status = str(metric_row.get("classification") or "unknown_fail_closed")
            metric_warnings = [str(value) for value in metric_row.get("warnings") or []]
        else:
            metric_status, metric_warnings = _local_metric_status(matched_rows)
        preset_row = audit_indexes["preset"].get((basket_symbol, basket_preset))
        preset_classification = str(preset_row.get("classification") or "") if preset_row else ""
        survivor_row = audit_indexes["survivor"].get((basket_symbol, basket_preset))
        survivor_stage = str(survivor_row.get("stage_classification") or "") if survivor_row else ""
        oos_blocker_class = ""
        candidate_blocker_class = ""
        for row in matched_rows:
            diagnostic = grid_analysis._derive_row_diagnostics(
                {
                    **row,
                    "provider_symbol_aliases": row.get("provider_symbol_aliases") or [],
                    "primary_data_provider_symbol": row.get("primary_data_provider_symbol"),
                }
            )
            if not oos_blocker_class and diagnostic.get("oos_evidence_blocker_class"):
                oos_blocker_class = str(diagnostic["oos_evidence_blocker_class"])
            if not candidate_blocker_class and diagnostic.get("primary_blocker"):
                candidate_blocker_class = str(diagnostic["primary_blocker"])
        exact_blocker = _exact_blocker_category(
            basket_row=basket_row,
            matched_rows=matched_rows,
            join_failure_reason=join_failure_reason,
            metric_status=metric_status,
            preset_classification=preset_classification or None,
            survivor_stage=survivor_stage or None,
        )
        blocker_counts.update([exact_blocker])
        next_action = _next_action(exact_blocker, readiness_adapter_gap=readiness_adapter_gap)
        next_action_counts.update([next_action])
        closest = bool(matched_rows) and exact_blocker in {
            "criteria_failed",
            "sufficient_oos_but_not_promotion_ready",
            "evidence_complete_or_near_complete",
        }

        materialized_rows.append(
            {
                "basket_id": basket_row.get("candidate_id"),
                "asset": basket_symbol,
                "canonical_symbol": basket_symbol,
                "provider_symbol": basket_row.get("provider_symbol"),
                "timeframe": ",".join(str(value) for value in basket_row.get("timeframes") or []),
                "preset": basket_preset,
                "behavior_family": basket_row.get("behavior_family"),
                "hypothesis_id": basket_row.get("hypothesis_id"),
                "source_identity_status": basket_row.get("source_identity_status"),
                "source_identity_blocker": (
                    "source_identity_blocked"
                    if str(basket_row.get("source_identity_status") or "") == "candidate_alias_only"
                    else ""
                ),
                "expected_campaign_artifact_ref": "research/campaign_registry_latest.v1.json",
                "expected_screening_evidence_ref": "research/screening_evidence_latest.v1.json",
                "expected_oos_evidence_ref": "research/screening_evidence_latest.v1.json",
                "expected_candidate_lineage_ref": "research/candidate_registry_latest.v1.json",
                "controlled_grid_run_id": matched_rows[0]["run_id"] if matched_rows else "",
                "matched_grid_rows_count": len(matched_rows),
                "matched_grid_rows": matched_rows,
                "join_keys_attempted": join_keys_attempted,
                "join_key_status": "grid_row_match_found" if matched_rows else (join_failure_reason or "unknown_fail_closed"),
                "join_failure_reason": join_failure_reason or "",
                "evidence_exists_in_grid": bool(matched_rows),
                "evidence_visible_to_readiness_loop": evidence_visible,
                "readiness_adapter_gap": readiness_adapter_gap,
                "screening_evidence_status": _screening_status(matched_rows, evidence_visible),
                "oos_evidence_status": _oos_status(matched_rows),
                "sufficient_oos_evidence_status": (
                    "present"
                    if any(str(row.get("outcome_class") or "") == "sufficient_oos_evidence" for row in matched_rows)
                    else "missing"
                ),
                "candidate_lineage_status": _candidate_lineage_status(basket_row),
                "metric_consistency_status": metric_status,
                "metric_consistency_warnings": metric_warnings,
                "oos_blocker_class": oos_blocker_class,
                "candidate_blocker_class": candidate_blocker_class,
                "preset_executability_classification": preset_classification or "unknown_fail_closed",
                "survivor_stage_classification": survivor_stage or "unknown_fail_closed",
                "closest_to_routing_sampling_ready": closest,
                "exact_blocker_category": exact_blocker,
                "exact_next_action": next_action,
            }
        )

    materialized_rows.sort(
        key=lambda row: (
            0 if row["closest_to_routing_sampling_ready"] else 1,
            str(row["exact_blocker_category"]),
            str(row["asset"]),
            str(row["preset"]),
        )
    )
    closest = [
        {
            "basket_id": row["basket_id"],
            "asset": row["asset"],
            "preset": row["preset"],
            "blocker": row["exact_blocker_category"],
            "next_action": row["exact_next_action"],
        }
        for row in materialized_rows
        if row["closest_to_routing_sampling_ready"]
    ][:10]

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": "deterministic_read_only",
        "input_basket_count": len(materialized_rows),
        "grid_runs_scanned_count": run_count,
        "grid_rows_scanned_count": grid_row_count,
        "baskets_with_matched_grid_rows": sum(bool(row["matched_grid_rows_count"]) for row in materialized_rows),
        "baskets_with_sufficient_oos_in_grid": sum(
            row["sufficient_oos_evidence_status"] == "present" for row in materialized_rows
        ),
        "baskets_where_grid_evidence_not_visible_to_readiness": sum(
            bool(row["readiness_adapter_gap"]) for row in materialized_rows
        ),
        "baskets_blocked_by_source_identity": blocker_counts.get("source_identity_blocked", 0),
        "baskets_blocked_by_metric_inconsistency": blocker_counts.get("metric_inconsistent", 0),
        "baskets_blocked_by_preset_mapping": sum(
            blocker_counts.get(value, 0)
            for value in (
                "mapping_missing",
                "preset_not_executable",
                "region_constraint_mismatch",
                "asset_class_constraint_mismatch",
                "timeframe_constraint_mismatch",
                "provider_symbol_unresolved",
                "unsupported_combination",
            )
        ),
        "baskets_blocked_by_degenerate_no_survivors": blocker_counts.get("degenerate_no_survivors", 0)
        + sum(1 for row in materialized_rows if str(row["survivor_stage_classification"]).endswith("_no_survivors")),
        "closest_baskets_to_readiness": closest,
        "next_action_counts": dict(sorted(next_action_counts.items())),
        "summary": {
            "blocker_category_counts": dict(sorted(blocker_counts.items())),
            "operator_summary": (
                "Discovery basket x controlled-grid materialization shows whether grid evidence exists, "
                "whether readiness can see it, and which deterministic blocker still keeps each basket "
                "out of routing/sampling readiness."
            ),
        },
        "rows": materialized_rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary = report.get("summary") or {}
    counts = summary.get("blocker_category_counts") or {}
    count_table = _table(
        ["Field", "Count"],
        [
            ["input basket count", str(report.get("input_basket_count") or 0)],
            ["grid runs scanned", str(report.get("grid_runs_scanned_count") or 0)],
            ["grid rows scanned", str(report.get("grid_rows_scanned_count") or 0)],
            ["matched baskets", str(report.get("baskets_with_matched_grid_rows") or 0)],
            [
                "sufficient OOS in grid",
                str(report.get("baskets_with_sufficient_oos_in_grid") or 0),
            ],
            [
                "grid evidence not visible to readiness",
                str(report.get("baskets_where_grid_evidence_not_visible_to_readiness") or 0),
            ],
        ],
    )
    blocker_table = _table(
        ["Blocker", "Count"],
        [[str(key), str(value)] for key, value in counts.items()] or [["none", "0"]],
    )
    basket_table = _table(
        [
            "Basket",
            "Asset",
            "Preset",
            "Matched rows",
            "Join status",
            "OOS",
            "Metric",
            "Blocker",
            "Closest",
            "Next action",
        ],
        [
            [
                str(row.get("basket_id") or ""),
                str(row.get("asset") or ""),
                str(row.get("preset") or ""),
                str(row.get("matched_grid_rows_count") or 0),
                str(row.get("join_key_status") or ""),
                str(row.get("sufficient_oos_evidence_status") or ""),
                str(row.get("metric_consistency_status") or ""),
                str(row.get("exact_blocker_category") or ""),
                "yes" if row.get("closest_to_routing_sampling_ready") else "no",
                str(row.get("exact_next_action") or ""),
            ]
            for row in rows
        ],
    )
    closest_rows = report.get("closest_baskets_to_readiness") if isinstance(
        report.get("closest_baskets_to_readiness"), list
    ) else []
    closest_table = _table(
        ["Basket", "Asset", "Preset", "Blocker", "Next action"],
        [
            [
                str(row.get("basket_id") or ""),
                str(row.get("asset") or ""),
                str(row.get("preset") or ""),
                str(row.get("blocker") or ""),
                str(row.get("next_action") or ""),
            ]
            for row in closest_rows
        ]
        or [["none", "-", "-", "-", "-"]],
    )
    return "\n".join(
        [
            "# QRE Discovery Basket Grid Evidence Materialization",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Aggregate counts",
            count_table,
            "",
            "## 3. Top blockers",
            blocker_table,
            "",
            "## 4. Basket materialization",
            basket_table,
            "",
            "## 5. Closest baskets to readiness",
            closest_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_discovery_basket_grid_evidence_materialization: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_discovery_basket_grid_evidence_materialization",
        description="Bridge production discovery baskets to controlled discovery grid evidence.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_discovery_basket_grid_evidence_materialization(
        max_candidates=args.max_candidates
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
