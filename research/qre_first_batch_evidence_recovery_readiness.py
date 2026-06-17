from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_basket_evidence_density_materialization as density
from research import qre_basket_evidence_recovery_plan as recovery_plan
from research import qre_basket_lineage_recovery_diagnostics as lineage_diag
from research import qre_discovery_basket_grid_evidence_materialization as grid_materialization
from research import qre_evidence_complete_basket_closure as closure
from research import qre_grid_candidate_campaign_lineage_bridge as lineage_bridge
from research import qre_real_basket_evidence_coverage as coverage


REPORT_KIND: Final[str] = "qre_first_batch_evidence_recovery_readiness"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_first_batch_evidence_recovery_readiness")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_first_batch_evidence_recovery_readiness/"

SAFE_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.qre_discovery_basket_grid_evidence_materialization --write",
    "python -m research.qre_grid_candidate_campaign_lineage_bridge --write",
    "python -m research.qre_basket_lineage_recovery_diagnostics --write",
    "python -m research.qre_basket_evidence_recovery_plan --write",
    "python -m research.qre_basket_next_action_queue --write",
    "python -m research.qre_basket_operator_action_plan --write",
    "python -m research.qre_evidence_complete_basket_closure --write",
    "python -m research.qre_trusted_loop_review_packet --write",
    "python -m research.qre_first_batch_evidence_recovery_readiness --write",
)
UNSAFE_KEYWORDS: Final[tuple[str, ...]] = (
    "campaign_launcher",
    "campaign_queue",
    "campaign_registry",
    "run_campaign",
    "broad research run",
    "strategy synthesis",
    "strategy registration",
    "candidate promotion",
    "paper",
    "shadow",
    "live",
    "broker",
    "risk",
    "execution",
    "provider activation",
    "external data fetch",
)
FIRST_BATCH_SYMBOLS: Final[tuple[str, ...]] = ("AAPL", "NVDA")
SECOND_LINE_LINEAGE_SYMBOLS: Final[tuple[str, ...]] = ("TSM",)
SECOND_LINE_OOS_SYMBOLS: Final[tuple[str, ...]] = ("AMD", "ASML", "MSFT")
SOURCE_CACHE_FIRST_SYMBOLS: Final[tuple[str, ...]] = (
    "ADYEN",
    "BABA",
    "BESI",
    "QQQ",
    "SMH",
    "SONY",
    "SPY",
    "TM",
)
IDENTITY_GATED_SYMBOLS: Final[tuple[str, ...]] = ("ASMI",)
ARCHIVE_PATTERNS: Final[tuple[str, ...]] = (
    "run_manifest.v1.json",
    "run_batch_manifest.v1.json",
    "run_candidates.v1.json",
    "run_screening_candidates.v1.json",
)
ROW_STOP_CONDITIONS: Final[tuple[str, ...]] = (
    "stop_if_controlled_grid_artifact_generation_is_not_explicitly_operator_approved",
    "stop_if_artifact_recovery_requires_campaign_or_queue_mutation",
    "stop_if_lineage_or_oos_would_be_inferred_without_local_evidence",
)
AUTHORITY_BOUNDARY: Final[dict[str, Any]] = {
    "read_only_report_only": True,
    "not_campaign_launcher": True,
    "not_campaign_queue_mutation": True,
    "not_campaign_registry_mutation": True,
    "not_run_campaign_mutation": True,
    "not_broad_research_run": True,
    "not_strategy_synthesis": True,
    "not_strategy_registration": True,
    "not_candidate_promotion": True,
    "not_routing_mutation": True,
    "not_sampling_mutation": True,
    "not_paper_shadow_live": True,
    "not_broker_risk_execution": True,
    "not_provider_activation": True,
    "not_external_data_fetch": True,
    "not_frozen_contract_mutation": True,
    "not_research_latest_mutation": True,
    "not_strategy_matrix_mutation": True,
}


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


def _candidate_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _index_by_candidate(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or row.get("basket_id") or "")
        if candidate_id and candidate_id not in indexed:
            indexed[candidate_id] = dict(row)
    return indexed


def _index_by_symbol_preset(rows: Sequence[Mapping[str, Any]], *, symbol_key: str, preset_key: str) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get(symbol_key) or "")
        preset_id = str(row.get(preset_key) or "")
        key = (symbol, preset_id)
        if symbol and preset_id and key not in indexed:
            indexed[key] = dict(row)
    return indexed


def _scan_history_archive(repo_root: Path, *, symbol: str) -> dict[str, Any]:
    history_root = repo_root / "research" / "history"
    matches: list[str] = []
    if not history_root.is_dir():
        return {
            "archive_hint_status": "history_unavailable",
            "history_match_count": 0,
            "history_match_samples": [],
        }
    needle = f'"{symbol}"'
    for pattern in ARCHIVE_PATTERNS:
        for path in sorted(history_root.rglob(pattern)):
            try:
                if needle in path.read_text(encoding="utf-8", errors="ignore"):
                    matches.append(path.relative_to(repo_root).as_posix())
            except OSError:
                continue
    return {
        "archive_hint_status": "history_archive_hint_present" if matches else "no_history_archive_hint_found",
        "history_match_count": len(matches),
        "history_match_samples": matches[:5],
    }


def classify_command_safety(command: str) -> dict[str, Any]:
    normalized = " ".join(str(command or "").strip().split())
    if normalized in SAFE_COMMANDS:
        return {
            "command": normalized,
            "classification": "safe_read_only",
            "safe_command_available": True,
            "operator_approval_required": False,
            "auto_run_allowed": False,
            "reason": "read_only_report_materialization_only",
        }
    lowered = normalized.lower()
    if "controlled_grid_artifact_generation" in lowered:
        return {
            "command": normalized,
            "classification": "unsafe_or_unproven",
            "safe_command_available": False,
            "operator_approval_required": True,
            "auto_run_allowed": False,
            "candidate_recovery_action": "operator_approve_bounded_controlled_grid_artifact_generation",
            "reason": "controlled_grid_artifact_generation_not_proven_read_only",
        }
    if any(keyword in lowered for keyword in UNSAFE_KEYWORDS):
        return {
            "command": normalized,
            "classification": "unsafe_or_unproven",
            "safe_command_available": False,
            "operator_approval_required": True,
            "auto_run_allowed": False,
            "reason": "command_exceeds_read_only_report_only_authority",
        }
    return {
        "command": normalized,
        "classification": "unproven",
        "safe_command_available": False,
        "operator_approval_required": True,
        "auto_run_allowed": False,
        "reason": "command_not_allowlisted_as_read_only",
    }


def _batch_classification(symbol: str) -> str:
    if symbol in FIRST_BATCH_SYMBOLS:
        return "first_batch"
    if symbol in SECOND_LINE_LINEAGE_SYMBOLS:
        return "second_line_lineage"
    if symbol in SECOND_LINE_OOS_SYMBOLS:
        return "second_line_oos_classification"
    if symbol in SOURCE_CACHE_FIRST_SYMBOLS:
        return "source_cache_first"
    if symbol in IDENTITY_GATED_SYMBOLS:
        return "identity_gated"
    return "unclassified_fail_closed"


def _expected_downstream_effect(batch_classification: str) -> str:
    if batch_classification == "first_batch":
        return "bounded_first_batch_recovery_context_prepared_without_changing_evidence_counts"
    if batch_classification == "second_line_lineage":
        return "lineage_followup_can_start_after_first_batch_or_archive_recovery"
    if batch_classification == "second_line_oos_classification":
        return "oos_classification_can_be_rechecked_after_first_batch_reruns"
    if batch_classification == "source_cache_first":
        return "source_cache_preconditions_must_be_resolved_before_grid_or_oos_recovery"
    if batch_classification == "identity_gated":
        return "identity_resolution_must_remain_separate_before_any_other_recovery_step"
    return "fail_closed_operator_review"


def _grid_artifact_status(grid_row: Mapping[str, Any], archive_state: Mapping[str, Any]) -> str:
    if bool(grid_row.get("evidence_exists_in_grid")):
        if int(grid_row.get("matched_grid_rows_count") or 0) > 0:
            return "grid_artifact_matched"
        return "grid_artifact_present_unmatched"
    if str(grid_row.get("exact_blocker_category") or "") == "no_grid_run_found":
        if str(archive_state.get("archive_hint_status") or "") == "history_archive_hint_present":
            return "no_local_grid_run_found_archive_hint_present"
        return "no_local_grid_run_found"
    return "grid_artifact_status_unknown_fail_closed"


def _source_quality_status(coverage_row: Mapping[str, Any], density_row: Mapping[str, Any]) -> str:
    if str(density_row.get("source_identity_status") or "") != "provider_symbol_verified":
        return "identity_not_verified"
    if bool((coverage_row.get("evidence_presence") or {}).get("source_quality_ready")):
        return "sufficient"
    if int(density_row.get("source_quality_rows") or 0) > 0:
        return "present_not_ready"
    return "missing"


def _cache_coverage_status(coverage_row: Mapping[str, Any], density_row: Mapping[str, Any]) -> str:
    if bool((coverage_row.get("evidence_presence") or {}).get("cache_ready")):
        return "sufficient"
    if int(density_row.get("cache_coverage_rows") or 0) > 0:
        return "present_not_ready"
    return "missing"


def _oos_status(density_row: Mapping[str, Any]) -> str:
    status = str(density_row.get("oos_evidence_status") or "missing")
    if status == "no_oos_evidence":
        return "verified_absent"
    if status in {"sufficient_oos_evidence", "insufficient_oos_evidence"}:
        return status
    if status in {"oos_evidence_unknown", "oos_evidence_missing"}:
        return status
    return "missing"


def _required_artifacts(density_row: Mapping[str, Any], recovery_row: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for group in (
        density_row.get("source_quality_refs") or [],
        density_row.get("cache_coverage_refs") or [],
        density_row.get("screening_evidence_refs") or [],
        density_row.get("oos_evidence_refs") or [],
        density_row.get("candidate_lineage_refs") or [],
        density_row.get("campaign_lineage_refs") or [],
    ):
        for item in group:
            value = str(item or "")
            if value and value not in refs:
                refs.append(value)
    for blocker in recovery_row.get("blockers") or []:
        if not isinstance(blocker, Mapping):
            continue
        for item in blocker.get("potential_clear_refs") or []:
            value = str(item or "")
            if value and value not in refs:
                refs.append(value)
    return refs


def _candidate_row(
    *,
    repo_root: Path,
    closure_row: Mapping[str, Any],
    coverage_row: Mapping[str, Any],
    density_row: Mapping[str, Any],
    lineage_row: Mapping[str, Any],
    grid_row: Mapping[str, Any],
    bridge_row: Mapping[str, Any],
    recovery_row: Mapping[str, Any],
    campaign_registry_symbols: frozenset[str],
) -> dict[str, Any]:
    symbol = str(closure_row.get("symbol") or coverage_row.get("symbol") or density_row.get("symbol") or "")
    preset_id = str(closure_row.get("preset_id") or coverage_row.get("preset_id") or density_row.get("preset_id") or grid_row.get("preset") or "")
    basket_id = str(grid_row.get("basket_id") or closure_row.get("candidate_id") or coverage_row.get("candidate_id") or "")
    batch_classification = _batch_classification(symbol)
    archive_state = _scan_history_archive(repo_root, symbol=symbol)
    grid_artifact_status = _grid_artifact_status(grid_row, archive_state)
    campaign_lineage_status = str(lineage_row.get("campaign_lineage_proof_status") or "gap")
    candidate_lineage_status = str(lineage_row.get("candidate_lineage_proof_status") or "lineage_gap")
    oos_status = _oos_status(density_row)
    required_artifacts = _required_artifacts(density_row, recovery_row)
    safe_commands = list(SAFE_COMMANDS)
    unsafe_actions = [
        "campaign_launcher",
        "campaign_queue mutation",
        "campaign_registry mutation",
        "run_campaign mutation",
        "broad research run",
        "strategy synthesis",
        "strategy registration",
        "candidate promotion",
        "paper/shadow/live",
        "broker/risk/execution",
        "provider activation",
        "external data fetch",
        "controlled_grid_artifact_generation",
    ]
    screening_rows = int(density_row.get("screening_evidence_rows") or 0)
    source_quality_status = _source_quality_status(coverage_row, density_row)
    cache_coverage_status = _cache_coverage_status(coverage_row, density_row)
    source_quality_sufficient = source_quality_status == "sufficient"
    cache_coverage_sufficient = cache_coverage_status == "sufficient"
    approval_required = True
    next_report = (
        "qre_first_batch_evidence_recovery_readiness"
        if batch_classification == "identity_gated"
        else "qre_discovery_basket_grid_evidence_materialization"
        if grid_artifact_status.startswith("no_local_grid_run_found")
        else "qre_grid_candidate_campaign_lineage_bridge"
        if campaign_lineage_status != "proven"
        else "qre_evidence_complete_basket_closure"
    )
    return {
        "symbol": symbol,
        "preset_id": preset_id,
        "basket_id": basket_id,
        "candidate_id": str(closure_row.get("candidate_id") or coverage_row.get("candidate_id") or ""),
        "batch_classification": batch_classification,
        "current_score": int(closure_row.get("evidence_completeness_score_pct") or coverage_row.get("evidence_completeness_score_pct") or 0),
        "current_exact_blockers": list(closure_row.get("exact_blockers") or []),
        "candidate_lineage_status": candidate_lineage_status,
        "campaign_lineage_status": campaign_lineage_status,
        "grid_artifact_status": grid_artifact_status,
        "oos_evidence_status": oos_status,
        "source_quality_status": source_quality_status,
        "cache_coverage_status": cache_coverage_status,
        "required_artifacts": required_artifacts,
        "safe_readonly_commands_available": safe_commands,
        "unsafe_or_unproven_commands": unsafe_actions,
        "operator_approval_required": approval_required,
        "auto_run_allowed": False,
        "reason_auto_run_disallowed": "controlled_grid_artifact_generation_not_proven_read_only",
        "expected_downstream_effect_if_approved": _expected_downstream_effect(batch_classification),
        "expected_downstream_effect_if_artifact_restored": (
            "campaign_lineage_can_be_retested_from_restored_local_grid_artifacts"
            if grid_artifact_status.startswith("no_local_grid_run_found")
            else "rerun_reports_can_recheck_lineage_and_oos_without_granting_execution_authority"
        ),
        "stop_conditions": list(ROW_STOP_CONDITIONS),
        "next_report_to_rerun": next_report,
        "authority_boundary": dict(AUTHORITY_BOUNDARY),
        "screening_evidence_status": "present" if screening_rows > 0 else "missing",
        "screening_evidence_exists": screening_rows > 0,
        "oos_evidence_truly_absent": oos_status == "verified_absent",
        "oos_evidence_only_unlinked": False,
        "source_cache_sufficient_now": source_quality_sufficient and cache_coverage_sufficient,
        "bridge_input_artifacts_present": bool(grid_row) and bool(bridge_row),
        "bridge_has_matching_keys": int(bridge_row.get("matched_grid_rows_count") or 0) > 0,
        "candidate_lineage_proven_campaign_missing": candidate_lineage_status == "candidate_proven_campaign_missing" and campaign_lineage_status != "proven",
        "campaign_registry_symbol_present": symbol in campaign_registry_symbols,
        "local_archive_state": archive_state,
        "lineage_bridge_status": str(bridge_row.get("lineage_bridge_status") or "blocked_no_grid_match"),
        "join_key_status": str(grid_row.get("join_key_status") or bridge_row.get("join_key_status") or "unknown"),
        "controlled_grid_run_id": str(grid_row.get("controlled_grid_run_id") or ""),
    }


def build_first_batch_evidence_recovery_readiness(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    density_report = density.build_basket_evidence_density_materialization(repo_root=repo_root, max_candidates=max_candidates)
    grid_report = grid_materialization.build_discovery_basket_grid_evidence_materialization(repo_root=repo_root, max_candidates=max_candidates)
    bridge_report = lineage_bridge.build_grid_candidate_campaign_lineage_bridge(repo_root=repo_root, max_candidates=max_candidates)
    lineage_report = lineage_diag.build_basket_lineage_recovery_diagnostics(repo_root=repo_root, max_candidates=max_candidates)
    closure_report = closure.build_evidence_complete_basket_closure(repo_root=repo_root, max_candidates=max_candidates)
    coverage_report = coverage.build_real_basket_evidence_coverage(repo_root=repo_root, max_candidates=max_candidates)
    recovery_report = recovery_plan.build_basket_evidence_recovery_plan(repo_root=repo_root, max_candidates=max_candidates)

    density_by_candidate = _index_by_candidate(_candidate_rows(density_report))
    coverage_by_candidate = _index_by_candidate(_candidate_rows(coverage_report))
    closure_by_candidate = _index_by_candidate(_candidate_rows(closure_report))
    lineage_by_candidate = _index_by_candidate(_candidate_rows(lineage_report))
    recovery_by_candidate = _index_by_candidate(_candidate_rows(recovery_report))
    grid_by_key = _index_by_symbol_preset(_candidate_rows(grid_report), symbol_key="asset", preset_key="preset")
    bridge_by_key = _index_by_symbol_preset(_candidate_rows(bridge_report), symbol_key="asset", preset_key="preset")

    campaign_registry = _read_json(repo_root / Path("research/campaign_registry_latest.v1.json")) or {}
    campaign_registry_text = json.dumps(campaign_registry, sort_keys=True)
    campaign_registry_symbols = frozenset(
        symbol
        for symbol in FIRST_BATCH_SYMBOLS + SECOND_LINE_LINEAGE_SYMBOLS + SECOND_LINE_OOS_SYMBOLS + SOURCE_CACHE_FIRST_SYMBOLS + IDENTITY_GATED_SYMBOLS
        if symbol in campaign_registry_text
    )

    candidate_ids = sorted(
        {
            *density_by_candidate.keys(),
            *coverage_by_candidate.keys(),
            *closure_by_candidate.keys(),
        }
    )
    candidate_rows: list[dict[str, Any]] = []
    for candidate_id in candidate_ids:
        closure_row = closure_by_candidate.get(candidate_id, {})
        coverage_row = coverage_by_candidate.get(candidate_id, {})
        density_row = density_by_candidate.get(candidate_id, {})
        lineage_row = lineage_by_candidate.get(candidate_id, {})
        recovery_row = recovery_by_candidate.get(candidate_id, {})
        symbol = str(closure_row.get("symbol") or coverage_row.get("symbol") or density_row.get("symbol") or "")
        preset_id = str(closure_row.get("preset_id") or coverage_row.get("preset_id") or density_row.get("preset_id") or "")
        grid_row = grid_by_key.get((symbol, preset_id), {})
        bridge_row = bridge_by_key.get((symbol, preset_id), {})
        candidate_rows.append(
            _candidate_row(
                repo_root=repo_root,
                closure_row=closure_row,
                coverage_row=coverage_row,
                density_row=density_row,
                lineage_row=lineage_row,
                grid_row=grid_row,
                bridge_row=bridge_row,
                recovery_row=recovery_row,
                campaign_registry_symbols=campaign_registry_symbols,
            )
        )
    candidate_rows.sort(key=lambda row: (str(row["batch_classification"]), -int(row["current_score"]), str(row["symbol"]), str(row["preset_id"])))

    first_batch_rows = [row for row in candidate_rows if row["batch_classification"] == "first_batch"]
    second_line_rows = [row for row in candidate_rows if row["batch_classification"] == "second_line_lineage"]
    source_cache_rows = [row for row in candidate_rows if row["batch_classification"] == "source_cache_first"]
    identity_rows = [row for row in candidate_rows if row["batch_classification"] == "identity_gated"]

    command_rows = [
        classify_command_safety(command) for command in SAFE_COMMANDS
    ] + [
        classify_command_safety(command)
        for command in (
            "campaign_launcher",
            "campaign_queue mutation",
            "campaign_registry mutation",
            "run_campaign mutation",
            "broad research run",
            "strategy synthesis",
            "strategy registration",
            "candidate promotion",
            "paper shadow live",
            "broker risk execution",
            "provider activation",
            "external data fetch",
            "controlled_grid_artifact_generation",
        )
    ]
    command_rows.sort(key=lambda row: (str(row.get("classification") or ""), str(row.get("command") or "")))
    approval_matrix = [
        {
            "symbol": row["symbol"],
            "candidate_recovery_action": "operator_approve_bounded_controlled_grid_artifact_generation",
            "safe_command_available": False,
            "operator_approval_required": True,
            "auto_run_allowed": False,
            "reason": "controlled_grid_artifact_generation_not_proven_read_only",
        }
        for row in first_batch_rows
    ]
    overall_stop_conditions = list(ROW_STOP_CONDITIONS) + [
        "stop_if_evidence_complete_count_changes_without_new_local_evidence",
        "stop_if_trusted_loop_trust_level_improves_only_because_a_plan_exists",
    ]
    expected_rerun_sequence = [
        "python -m research.qre_discovery_basket_grid_evidence_materialization --write",
        "python -m research.qre_grid_candidate_campaign_lineage_bridge --write",
        "python -m research.qre_basket_lineage_recovery_diagnostics --write",
        "python -m research.qre_first_batch_evidence_recovery_readiness --write",
        "python -m research.qre_basket_operator_action_plan --write",
        "python -m research.qre_basket_next_action_queue --write",
        "python -m research.qre_evidence_complete_basket_closure --write",
        "python -m research.qre_trusted_loop_review_packet --write",
    ]
    grid_summary = grid_report.get("summary") if isinstance(grid_report.get("summary"), Mapping) else {}
    lineage_summary = lineage_report.get("summary") if isinstance(lineage_report.get("summary"), Mapping) else {}
    closure_summary = closure_report.get("summary") if isinstance(closure_report.get("summary"), Mapping) else {}

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "first_batch_summary": {
            "first_batch": [row["symbol"] for row in first_batch_rows],
            "second_line_lineage": [row["symbol"] for row in second_line_rows],
            "second_line_oos_classification": [row["symbol"] for row in candidate_rows if row["batch_classification"] == "second_line_oos_classification"],
            "source_cache_first": [row["symbol"] for row in source_cache_rows],
            "identity_gated": [row["symbol"] for row in identity_rows],
            "evidence_complete_count": int(closure_summary.get("evidence_complete_count") or 0),
            "unknown_blocker_count": int(closure_summary.get("unknown_blocker_count") or 0),
            "operator_summary": "First-batch readiness isolates AAPL/NVDA as the bounded recovery batch and keeps all downstream work fail-closed until operator approval or genuine artifact restoration occurs.",
        },
        "candidate_preconditions": candidate_rows,
        "grid_artifact_recovery_readiness": {
            "grid_runs_scanned": int(grid_report.get("grid_runs_scanned_count") or 0),
            "grid_rows_scanned": int(grid_report.get("grid_rows_scanned_count") or 0),
            "matched_baskets": int(grid_report.get("baskets_with_matched_grid_rows") or 0),
            "sufficient_oos_in_grid": int(grid_report.get("baskets_with_sufficient_oos_in_grid") or 0),
            "top_blocker": "no_grid_run_found" if int(grid_report.get("grid_runs_scanned_count") or 0) == 0 else "matched_or_other",
            "first_batch_rows": [
                {
                    "symbol": row["symbol"],
                    "grid_artifact_status": row["grid_artifact_status"],
                    "local_archive_state": row["local_archive_state"],
                    "bridge_has_matching_keys": row["bridge_has_matching_keys"],
                    "join_key_status": row["join_key_status"],
                }
                for row in first_batch_rows
            ],
        },
        "campaign_lineage_readiness": {
            "candidate_lineage_proven_count": int(lineage_summary.get("candidate_lineage_proven_count") or 0),
            "campaign_lineage_proven_count": int(lineage_summary.get("campaign_lineage_proven_count") or 0),
            "first_batch_rows": [
                {
                    "symbol": row["symbol"],
                    "candidate_lineage_status": row["candidate_lineage_status"],
                    "campaign_lineage_status": row["campaign_lineage_status"],
                    "candidate_lineage_proven_campaign_missing": row["candidate_lineage_proven_campaign_missing"],
                    "bridge_input_artifacts_present": row["bridge_input_artifacts_present"],
                    "bridge_has_matching_keys": row["bridge_has_matching_keys"],
                }
                for row in first_batch_rows
            ],
        },
        "oos_evidence_readiness": {
            "first_batch_rows": [
                {
                    "symbol": row["symbol"],
                    "oos_evidence_status": row["oos_evidence_status"],
                    "oos_evidence_truly_absent": row["oos_evidence_truly_absent"],
                    "oos_evidence_only_unlinked": row["oos_evidence_only_unlinked"],
                    "screening_evidence_status": row["screening_evidence_status"],
                }
                for row in first_batch_rows
            ],
        },
        "source_cache_preconditions": {
            "first_batch_rows": [
                {
                    "symbol": row["symbol"],
                    "source_quality_status": row["source_quality_status"],
                    "cache_coverage_status": row["cache_coverage_status"],
                    "source_cache_sufficient_now": row["source_cache_sufficient_now"],
                    "screening_evidence_status": row["screening_evidence_status"],
                }
                for row in first_batch_rows
            ],
        },
        "command_safety_classification": {
            "rows": command_rows,
            "safe_command_count": sum(1 for row in command_rows if row["classification"] == "safe_read_only"),
            "unsafe_or_unproven_count": sum(1 for row in command_rows if row["classification"] != "safe_read_only"),
        },
        "operator_approval_matrix": approval_matrix,
        "stop_conditions": overall_stop_conditions,
        "expected_rerun_sequence": expected_rerun_sequence,
        "authority_boundary": dict(AUTHORITY_BOUNDARY),
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
            "mutates_queues": False,
            "mutates_frozen_contracts": False,
            "does_not_grant_trading_authority": True,
            "does_not_change_evidence_complete_count": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("first_batch_summary") if isinstance(report.get("first_batch_summary"), Mapping) else {}
    candidate_rows = report.get("candidate_preconditions") if isinstance(report.get("candidate_preconditions"), list) else []
    first_batch = [row for row in candidate_rows if isinstance(row, Mapping) and row.get("batch_classification") == "first_batch"]
    return "\n".join(
        [
            "# QRE First-Batch Evidence Recovery Readiness",
            "",
            "## 1. First batch summary",
            f"- {summary.get('operator_summary') or ''}",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["first_batch", ", ".join(str(item) for item in summary.get("first_batch") or []) or "none"],
                    ["second_line_lineage", ", ".join(str(item) for item in summary.get("second_line_lineage") or []) or "none"],
                    ["evidence_complete_count", str(summary.get("evidence_complete_count") or 0)],
                    ["unknown_blocker_count", str(summary.get("unknown_blocker_count") or 0)],
                ],
            ),
            "",
            "## 2. First batch rows",
            _table(
                ["Symbol", "Score", "Blockers", "Grid", "Campaign lineage", "OOS", "Source/cache"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(row.get("current_score") or 0),
                        ",".join(str(item) for item in row.get("current_exact_blockers") or []) or "none",
                        str(row.get("grid_artifact_status") or ""),
                        str(row.get("campaign_lineage_status") or ""),
                        str(row.get("oos_evidence_status") or ""),
                        f"{row.get('source_quality_status')}/{row.get('cache_coverage_status')}",
                    ]
                    for row in first_batch
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_first_batch_evidence_recovery_readiness: refusing write outside allowlist: {path!r}"
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
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        prog="python -m research.qre_first_batch_evidence_recovery_readiness",
        description="Build the read-only first-batch evidence recovery readiness plan.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_first_batch_evidence_recovery_readiness(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
