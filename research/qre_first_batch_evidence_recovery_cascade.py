from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_evidence_complete_basket_closure as closure
from research import qre_first_batch_evidence_recovery_readiness as readiness


REPORT_KIND: Final[str] = "qre_first_batch_evidence_recovery_cascade"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_first_batch_evidence_recovery_cascade")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_first_batch_evidence_recovery_cascade/"
TRUSTED_LOOP_PATH: Final[Path] = Path("logs/qre_trusted_loop_review/latest.json")

FIRST_BATCH_SYMBOLS: Final[tuple[str, ...]] = ("AAPL", "NVDA")
SECOND_LINE_SYMBOLS: Final[tuple[str, ...]] = ("TSM",)
TARGET_SYMBOLS: Final[frozenset[str]] = frozenset((*FIRST_BATCH_SYMBOLS, *SECOND_LINE_SYMBOLS))
TARGET_PRESETS: Final[tuple[str, ...]] = (
    "trend_pullback_v1",
    "trend_pullback_continuation_daily_v1",
    "trend_pullback_equities_4h",
)
TARGET_TIMEFRAMES: Final[tuple[str, ...]] = ("4h", "1d", "daily", "daily_v1")
ALLOWLISTED_ROOTS: Final[tuple[str, ...]] = (
    "logs",
    "research",
    "local_quarantine",
    "backup",
    "archived",
    "artifacts",
    ".tmp",
    "tests/fixtures",
)
PROTECTED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "dist",
        "build",
        "live",
        "paper",
        "shadow",
        "broker",
        "risk",
        "execution",
    }
)
PHASE_ONE_STOP_CONDITIONS: Final[tuple[str, ...]] = (
    "stop_if_only_stdout_or_generated_reports_exist_without_structured_results",
    "stop_if_next_step_requires_mutating_campaign_or_registry_state",
    "stop_if_preset_or_timeframe_identity_cannot_be_proven_deterministically",
)
TARGET_PRESET_BY_SYMBOL: Final[dict[str, str]] = {
    "AAPL": "trend_pullback_continuation_daily_v1",
    "NVDA": "trend_pullback_continuation_daily_v1",
    "TSM": "trend_pullback_continuation_daily_v1",
}
TARGET_TIMEFRAME_BY_SYMBOL: Final[dict[str, str]] = {
    "AAPL": "daily_v1",
    "NVDA": "daily_v1",
    "TSM": "daily_v1",
}
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
GENERATED_REPORT_MARKERS: Final[tuple[str, ...]] = (
    "qre_first_batch_evidence_recovery_readiness",
    "qre_discovery_basket_grid_evidence_materialization",
    "qre_grid_candidate_campaign_lineage_bridge",
    "qre_basket_lineage_recovery_diagnostics",
    "qre_basket_operator_action_plan",
    "qre_basket_next_action_queue",
    "qre_evidence_complete_basket_closure",
    "qre_trusted_loop_review",
)
RESULT_WRITTEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"results_written=(?P<count>\d+)")
VALIDATED_COUNT_PATTERN: Final[re.Pattern[str]] = re.compile(r"validated_count=(?P<count>\d+)")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _read_json_payload(path: Path) -> Any | None:
    if path.suffix.lower() not in {".json", ".jsonl"}:
        return None
    text = _read_text(path)
    if not text.strip():
        return None
    if path.suffix.lower() == ".jsonl":
        rows: list[Any] = []
        for line in text.splitlines():
            item = line.strip()
            if not item:
                continue
            try:
                rows.append(json.loads(item))
            except json.JSONDecodeError:
                return None
        return rows
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_json_mapping(path: Path) -> dict[str, Any] | None:
    payload = _read_json_payload(path)
    return payload if isinstance(payload, dict) else None


def _read_csv_rows(path: Path) -> list[dict[str, str]] | None:
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return None


def _flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _flatten_strings(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _flatten_strings(item)


def _symbol_matches(value: Any) -> list[str]:
    text = " ".join(_flatten_strings(value))
    return sorted(symbol for symbol in TARGET_SYMBOLS if symbol in text)


def _preset_matches(value: Any) -> list[str]:
    text = " ".join(_flatten_strings(value))
    return sorted(preset for preset in TARGET_PRESETS if preset in text)


def _timeframe_matches(value: Any) -> list[str]:
    text = " ".join(_flatten_strings(value))
    return sorted(timeframe for timeframe in TARGET_TIMEFRAMES if timeframe in text)


def _contains_any(value: Any, terms: Sequence[str]) -> bool:
    if isinstance(value, str):
        text = value.lower()
    else:
        try:
            text = json.dumps(value, default=str).lower()
        except TypeError:
            text = str(value).lower()
    return any(term.lower() in text for term in terms)


def _infer_schema_family(payload: Any, text: str) -> str:
    if isinstance(payload, Mapping):
        report_kind = str(payload.get("report_kind") or "")
        if report_kind:
            return report_kind
        if "run_id" in payload and "candidates" in payload:
            return "run_candidates"
        if "run_id" in payload and "batch_id" in payload:
            return "run_batch_manifest"
        if "campaign_id" in payload and "batches" in payload:
            return "run_campaign_manifest"
    if isinstance(payload, list):
        return "jsonl_rows"
    lowered = text.lower()
    if "stdout_tail" in lowered:
        return "legacy_stdout_trace"
    return "unknown"


def _infer_schema_version(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for field in ("schema_version", "version"):
            value = payload.get(field)
            if value is not None:
                return str(value)
    return "unknown"


def _root_type(relative_path: str) -> str:
    for root in ALLOWLISTED_ROOTS:
        normalized = root.replace("\\", "/").rstrip("/")
        if relative_path == normalized or relative_path.startswith(normalized + "/"):
            if normalized == ".tmp":
                return "temp_smoke"
            if normalized == "tests/fixtures":
                return "test_fixture"
            return normalized
    return "unknown"


def _artifact_kind(path: Path, payload: Any) -> str:
    name = path.name.lower()
    if "run_batch_state" in name:
        return "legacy_validation_state"
    if "run_batch_manifest" in name:
        return "legacy_batch_manifest"
    if "run_campaign_manifest" in name:
        return "legacy_campaign_manifest"
    if "run_candidates" in name:
        return "legacy_candidate_results"
    if "campaign_registry" in name:
        return "campaign_registry_snapshot"
    if "controlled_eval" in name:
        return "controlled_validation_execution"
    if "combination_results" in name or "execution_result" in name:
        return "grid_execution_artifact"
    if isinstance(payload, Mapping) and str(payload.get("report_kind") or "").startswith("qre_"):
        return "generated_report"
    return "unknown"


def classify_artifact(path: Path, *, repo_root: Path = Path(".")) -> dict[str, Any]:
    relative_path = path.relative_to(repo_root).as_posix()
    root_type = _root_type(relative_path)
    payload = _read_json_payload(path)
    csv_rows = None if payload is not None else _read_csv_rows(path)
    structured_value: Any = payload if payload is not None else csv_rows if csv_rows is not None else {}
    text = _read_text(path)
    artifact_kind = _artifact_kind(path, payload)
    symbol_matches = _symbol_matches(structured_value if structured_value else text)
    preset_matches = _preset_matches(structured_value if structured_value else text)
    timeframe_matches = _timeframe_matches(structured_value if structured_value else text)
    contains_candidate_id = _contains_any(structured_value if structured_value else text, ("candidate_id",))
    contains_campaign_id = _contains_any(structured_value if structured_value else text, ("campaign_id", "col_campaign_id"))
    contains_grid_run_id = _contains_any(structured_value if structured_value else text, ("grid_run_id", "grid_id"))
    contains_run_id = _contains_any(structured_value if structured_value else text, ("run_id",))
    contains_oos_fields = _contains_any(
        structured_value if structured_value else text,
        ("oos_trade_count", "oos_trades", "sufficient_oos_evidence", "no_oos_trades"),
    )
    contains_validation_fields = _contains_any(
        structured_value if structured_value else text,
        ("validated_count", "results_written", "validation", "result_success"),
    )
    contains_lineage_fields = _contains_any(
        structured_value if structured_value else text,
        ("source_artifact", "source_row_id", "run_manifest_id", "validation_plan_id", "campaign_id"),
    )
    has_structured_results = bool(
        (isinstance(payload, Mapping) and any(key in payload for key in ("rows", "candidates", "batches", "validation", "summary")))
        or isinstance(payload, list)
        or (csv_rows is not None and len(csv_rows) > 0)
    )
    stdout_only = bool(
        payload is not None
        and _contains_any(structured_value if structured_value else text, ("stdout_tail", "results_written=", "validated_count="))
        and not has_structured_results
    )
    schema_family = _infer_schema_family(payload, text)
    schema_version = _infer_schema_version(payload)

    classification_status = "irrelevant"
    rejection_reason = ""
    recommended_next_action = "keep_fail_closed"
    safe_to_use_as_evidence = False
    safe_to_restore_copy_only = False
    operator_approval_required = False
    downstream_expected_effect = "none"

    if root_type == "temp_smoke":
        classification_status = "smoke_temp_not_authoritative"
        rejection_reason = "temp_smoke_root_not_authoritative"
    elif root_type == "test_fixture":
        classification_status = "test_fixture_not_authoritative"
        rejection_reason = "fixture_root_not_authoritative"
    elif stdout_only:
        classification_status = "legacy_validation_stdout_only"
        rejection_reason = "stdout_tail_without_structured_results"
        recommended_next_action = "locate_structured_validation_results"
    elif artifact_kind == "generated_report" or schema_family in GENERATED_REPORT_MARKERS:
        classification_status = "generated_report_not_source_artifact"
        rejection_reason = "report_is_derived_not_source_evidence"
    elif artifact_kind == "campaign_registry_snapshot":
        classification_status = "registry_snapshot_not_lineage_proof"
        rejection_reason = "registry_snapshot_cannot_prove_lineage_alone"
    elif artifact_kind == "legacy_campaign_manifest" and contains_campaign_id and contains_run_id:
        classification_status = "legacy_validation_evidence_candidate"
        safe_to_restore_copy_only = True
        recommended_next_action = "locate_corresponding_symbol_level_validation_results"
        downstream_expected_effect = "campaign_run_identity_available_for_safe_bridge_analysis"
    elif symbol_matches and contains_validation_fields and has_structured_results:
        if contains_campaign_id and contains_run_id:
            classification_status = "legacy_validation_evidence_candidate"
            safe_to_restore_copy_only = True
            downstream_expected_effect = "legacy_validation_context_available_for_alias_analysis"
            recommended_next_action = "analyze_schema_and_alias_compatibility"
        else:
            classification_status = "missing_required_identity_fields"
            rejection_reason = "campaign_or_run_identity_missing"
            recommended_next_action = "locate_more_complete_structured_artifact"
    elif symbol_matches and has_structured_results:
        classification_status = "restorable_candidate"
        safe_to_restore_copy_only = True
        recommended_next_action = "inspect_for_validation_and_lineage_fields"
    elif not symbol_matches and artifact_kind == "legacy_candidate_results":
        classification_status = "legacy_validation_results_missing"
        rejection_reason = "results_written_context_present_but_first_batch_rows_not_found"
        recommended_next_action = "continue_allowlisted_search"

    return {
        "path": str(path.resolve()),
        "relative_path": relative_path,
        "root_type": root_type,
        "artifact_kind": artifact_kind,
        "schema_family": schema_family,
        "schema_version": schema_version,
        "symbol_matches": symbol_matches,
        "preset_matches": preset_matches,
        "timeframe_matches": timeframe_matches,
        "contains_candidate_id": contains_candidate_id,
        "contains_campaign_id": contains_campaign_id,
        "contains_grid_run_id": contains_grid_run_id,
        "contains_run_id": contains_run_id,
        "contains_oos_fields": contains_oos_fields,
        "contains_validation_fields": contains_validation_fields,
        "contains_lineage_fields": contains_lineage_fields,
        "stdout_only": stdout_only,
        "has_structured_results": has_structured_results,
        "file_mtime": int(path.stat().st_mtime) if path.exists() else 0,
        "file_size": int(path.stat().st_size) if path.exists() else 0,
        "classification_status": classification_status,
        "rejection_reason": rejection_reason,
        "recommended_next_action": recommended_next_action,
        "safe_to_use_as_evidence": safe_to_use_as_evidence,
        "safe_to_restore_copy_only": safe_to_restore_copy_only,
        "operator_approval_required": operator_approval_required,
        "downstream_expected_effect": downstream_expected_effect,
    }


def _iter_allowlisted_files(repo_root: Path) -> Iterable[Path]:
    for root in ALLOWLISTED_ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        if base.is_file():
            yield base
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative_parts = path.relative_to(repo_root).parts
            if any(part in PROTECTED_DIRS for part in relative_parts):
                continue
            yield path


def _extract_expected_result_count(row: Mapping[str, Any]) -> int:
    for field in ("expected_result_count", "validated_count"):
        value = row.get(field)
        if isinstance(value, int):
            return value
    payload = _read_json_payload(Path(row["path"]))
    if isinstance(payload, Mapping):
        summary = payload.get("summary")
        if isinstance(summary, Mapping):
            for field in ("validated_count", "result_success_count"):
                value = summary.get(field)
                if isinstance(value, int):
                    return value
        for field in ("validated_candidate_count", "result_success_count"):
            value = payload.get(field)
            if isinstance(value, int):
                return value
        stdout_tail = str(payload.get("stdout_tail") or "")
        for pattern in (RESULT_WRITTEN_PATTERN, VALIDATED_COUNT_PATTERN):
            match = pattern.search(stdout_tail)
            if match:
                return int(match.group("count"))
    text = _read_text(Path(row["path"]))
    for pattern in (RESULT_WRITTEN_PATTERN, VALIDATED_COUNT_PATTERN):
        match = pattern.search(text)
        if match:
            return int(match.group("count"))
    return 0


def _extract_validation_candidate_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get("candidates")
    if not isinstance(rows, list):
        rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    extracted: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        validation = row.get("validation")
        if isinstance(validation, Mapping):
            extracted.append(dict(row))
    return extracted


def _locate_validation_results(
    repo_root: Path,
    artifact_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    stdout_rows = [
        row
        for row in artifact_rows
        if row["classification_status"] == "legacy_validation_stdout_only"
    ]
    structured_rows = [
        row
        for row in artifact_rows
        if row["relative_path"].startswith("research/history/")
        and row["has_structured_results"]
        and (
            row["contains_validation_fields"]
            or row["artifact_kind"] in {"legacy_candidate_results", "legacy_validation_state"}
        )
    ]
    locator_rows: list[dict[str, Any]] = []
    for stdout_row in stdout_rows:
        expected_result_count = _extract_expected_result_count(stdout_row)
        matched_structured: list[dict[str, Any]] = []
        found_symbols: set[str] = set()
        found_validated_count = 0
        found_paths: list[str] = []
        for candidate_row in structured_rows:
            payload = _read_json_payload(Path(candidate_row["path"]))
            validation_rows = _extract_validation_candidate_rows(payload)
            if not validation_rows:
                continue
            matched_candidates = [
                row for row in validation_rows if str(row.get("asset") or "") in TARGET_SYMBOLS
            ]
            if not matched_candidates:
                continue
            for item in matched_candidates:
                found_symbols.add(str(item.get("asset") or ""))
                validation_status = str(((item.get("validation") or {}).get("status")) or "")
                current_status = str(item.get("current_status") or "")
                if validation_status == "validated" or current_status == "validated":
                    found_validated_count += 1
            found_paths.append(candidate_row["relative_path"])
            matched_structured.append(dict(candidate_row))
        found_paths = sorted(set(found_paths))
        result_schema_status = (
            "structured_validation_results_found"
            if found_paths
            else "structured_validation_results_missing"
        )
        missing_result_count = max(expected_result_count - found_validated_count, 0) if expected_result_count else 0
        locator_rows.append(
            {
                "stdout_trace_path": stdout_row["relative_path"],
                "expected_result_count": expected_result_count,
                "found_result_count": found_validated_count,
                "missing_result_count": missing_result_count,
                "found_result_paths": found_paths,
                "matched_symbols": sorted(found_symbols),
                "result_schema_status": result_schema_status,
                "can_use_as_oos_evidence": False,
                "can_use_as_campaign_lineage": False,
                "why_or_why_not": (
                    "structured_legacy_validation_rows_found_but_current_first_batch_daily_lineage_and_oos_proof_remain_unproven"
                    if found_paths
                    else "stdout_trace_exists_but_structured_validation_outputs_were_not_found"
                ),
            }
        )
    locator_rows.sort(key=lambda row: row["stdout_trace_path"])
    return {
        "rows": locator_rows,
        "trace_count": len(locator_rows),
        "structured_result_trace_count": sum(bool(row["found_result_paths"]) for row in locator_rows),
    }


def _analyze_legacy_compatibility(
    repo_root: Path,
    validation_locator: Mapping[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for locator_row in validation_locator.get("rows") or []:
        if not isinstance(locator_row, Mapping):
            continue
        for relative_path in locator_row.get("found_result_paths") or []:
            payload = _read_json_payload(repo_root / relative_path)
            for candidate_row in _extract_validation_candidate_rows(payload):
                symbol = str(candidate_row.get("asset") or "")
                if symbol not in TARGET_SYMBOLS:
                    continue
                legacy_preset = str(candidate_row.get("strategy_name") or "")
                legacy_timeframe = str(candidate_row.get("interval") or "")
                target_preset = TARGET_PRESET_BY_SYMBOL.get(symbol, "")
                target_timeframe = TARGET_TIMEFRAME_BY_SYMBOL.get(symbol, "")
                preset_outcome = (
                    "alias_allowed_for_context_only"
                    if legacy_preset == "trend_pullback_v1" and target_preset == "trend_pullback_continuation_daily_v1"
                    else "alias_blocked_no_policy"
                )
                timeframe_outcome = (
                    "alias_blocked_timeframe_mismatch"
                    if legacy_timeframe == "4h" and target_timeframe == "daily_v1"
                    else "alias_blocked_no_policy"
                )
                rows.append(
                    {
                        "symbol": symbol,
                        "legacy_result_path": relative_path,
                        "legacy_preset_id": legacy_preset,
                        "target_preset_id": target_preset,
                        "legacy_timeframe": legacy_timeframe,
                        "target_timeframe": target_timeframe,
                        "preset_alias_outcome": preset_outcome,
                        "timeframe_alias_outcome": timeframe_outcome,
                        "campaign_lineage_eligible": False,
                        "oos_context_eligible": False,
                        "bridge_status": "context_only_bridge_available",
                        "result": (
                            "legacy_result_can_inform_context_but_cannot_prove_current_daily_lineage_or_oos"
                        ),
                    }
                )
    rows.sort(key=lambda row: (row["symbol"], row["legacy_result_path"]))
    return {
        "rows": rows,
        "alias_policy": "legacy_compatible_for_context_only",
        "bridge_status": "context_only_bridge_available" if rows else "no_bridgeable_structured_results_found",
        "result": (
            "PRESET_TIMEFRAME_ALIAS_BLOCKED"
            if any(row["timeframe_alias_outcome"] == "alias_blocked_timeframe_mismatch" for row in rows)
            else "LEGACY_RESULTS_FOUND_BRIDGE_REQUIRED"
            if rows
            else "LEGACY_STDOUT_ONLY_RESULTS_MISSING"
        ),
    }


def _phase_one_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows = [classify_artifact(path, repo_root=repo_root) for path in _iter_allowlisted_files(repo_root)]
    filtered = [
        row for row in rows
        if row["classification_status"] != "irrelevant"
        or row["symbol_matches"]
        or row["artifact_kind"] in {"campaign_registry_snapshot", "generated_report", "controlled_validation_execution", "legacy_campaign_manifest"}
    ]
    filtered.sort(key=lambda row: (row["classification_status"], row["relative_path"]))
    return filtered


def build_first_batch_evidence_recovery_cascade(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    readiness_report = readiness.build_first_batch_evidence_recovery_readiness(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    closure_report = closure.build_evidence_complete_basket_closure(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    trusted_loop_report = _read_json_mapping(repo_root / TRUSTED_LOOP_PATH) or {}
    artifact_rows = _phase_one_rows(repo_root)
    validation_locator = _locate_validation_results(repo_root, artifact_rows)
    legacy_compatibility = _analyze_legacy_compatibility(repo_root, validation_locator)
    counts = Counter(str(row["classification_status"]) for row in artifact_rows)
    closure_rows = closure_report.get("rows") if isinstance(closure_report.get("rows"), list) else []
    closure_by_symbol = {
        str(row.get("symbol") or ""): dict(row)
        for row in closure_rows
        if isinstance(row, Mapping)
    }
    first_batch_rows = []
    for symbol in FIRST_BATCH_SYMBOLS:
        closure_row = closure_by_symbol.get(symbol, {})
        first_batch_rows.append(
            {
                "symbol": symbol,
                "before_blockers": list(closure_row.get("exact_blockers") or []),
                "artifact_signals": [
                    {
                        "relative_path": row["relative_path"],
                        "classification_status": row["classification_status"],
                        "preset_matches": row["preset_matches"],
                        "timeframe_matches": row["timeframe_matches"],
                    }
                    for row in artifact_rows
                    if symbol in row["symbol_matches"]
                ][:10],
                "stop_conditions": list(PHASE_ONE_STOP_CONDITIONS),
                "authority_boundary": dict(AUTHORITY_BOUNDARY),
            }
        )
    files_scanned = sum(1 for _ in _iter_allowlisted_files(repo_root))
    locator_rows = validation_locator["rows"]
    if legacy_compatibility["result"] == "PRESET_TIMEFRAME_ALIAS_BLOCKED":
        current_top_blocker = "preset_timeframe_alias_unproven"
    elif any(row["found_result_paths"] for row in locator_rows):
        current_top_blocker = "legacy_schema_bridge_or_alias_analysis_required"
    else:
        current_top_blocker = "legacy_results_missing"
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "overall_result": legacy_compatibility["result"],
        "first_batch_summary": {
            "first_batch": list(FIRST_BATCH_SYMBOLS),
            "second_line": list(SECOND_LINE_SYMBOLS),
            "evidence_complete_count": int((closure_report.get("summary") or {}).get("evidence_complete_count") or 0),
            "unknown_blocker_count": int((closure_report.get("summary") or {}).get("unknown_blocker_count") or 0),
            "trusted_loop_verdict": str((trusted_loop_report.get("summary") or {}).get("trust_verdict") or ""),
            "current_top_blocker": current_top_blocker,
            "top_blockers": {
                symbol: list((closure_by_symbol.get(symbol, {}) or {}).get("exact_blockers") or [])
                for symbol in FIRST_BATCH_SYMBOLS
            },
        },
        "artifact_discovery": {
            "phase": "controlled_grid_artifact_discovery_classifier",
            "files_scanned": files_scanned,
            "candidate_artifacts": len(artifact_rows),
            "classification_counts": dict(sorted(counts.items())),
            "rows": artifact_rows,
        },
        "validation_result_locator": validation_locator,
        "legacy_compatibility": legacy_compatibility,
        "first_batch_candidates": first_batch_rows,
        "phase_reports": [
            {
                "phase": "controlled_grid_artifact_discovery_classifier",
                "result": "executed",
                "blocker_before": "campaign_lineage_missing,no_oos_evidence",
                "blocker_after": "artifact_classification_completed_pending_result_location",
                "artifacts_found": len(artifact_rows),
                "actions_taken": [
                    "scanned_allowlisted_local_roots",
                    "classified_temp_fixture_report_registry_and_structured_legacy_artifacts",
                ],
                "why_continued_or_stopped": "continue_to_structured_result_location_if_legacy_candidates_exist",
            },
            {
                "phase": "missing_validation_result_output_locator",
                "result": "executed",
                "blocker_before": "artifact_classification_completed_pending_result_location",
                "blocker_after": current_top_blocker,
                "artifacts_found": validation_locator["structured_result_trace_count"],
                "actions_taken": [
                    "matched_stdout_validation_traces_to_allowlisted_structured_history_outputs",
                    "counted_expected_vs_found_validated_results",
                ],
                "why_continued_or_stopped": (
                    "continue_to_bridge_and_alias_analysis"
                    if current_top_blocker == "legacy_schema_bridge_or_alias_analysis_required"
                    else "stop_if_only_stdout_trace_exists_without_structured_results"
                ),
            },
            {
                "phase": "legacy_schema_bridge_and_alias_analysis",
                "result": legacy_compatibility["result"],
                "blocker_before": "legacy_schema_bridge_or_alias_analysis_required",
                "blocker_after": current_top_blocker,
                "artifacts_found": len(legacy_compatibility["rows"]),
                "actions_taken": [
                    "normalized_legacy_first_batch_validation_rows_for_context_only",
                    "blocked_direct_preset_and_timeframe_alias_for_current_daily_lineage",
                ],
                "why_continued_or_stopped": (
                    "stop_at_preset_timeframe_boundary"
                    if current_top_blocker == "preset_timeframe_alias_unproven"
                    else "continue_if_further_safe_context_integration_is_available"
                ),
            }
        ],
        "fundamental_stop_condition": (
            "preset_timeframe_alias_unproven"
            if current_top_blocker == "preset_timeframe_alias_unproven"
            else "legacy_results_missing"
            if current_top_blocker == "legacy_results_missing"
            else "operator_decision_required"
        ),
        "current_stop_conditions": list(PHASE_ONE_STOP_CONDITIONS),
        "authority_boundary": dict(AUTHORITY_BOUNDARY),
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
            "mutates_queues": False,
            "mutates_frozen_contracts": False,
            "does_not_change_evidence_complete_count": True,
            "does_not_change_trusted_loop_level_without_real_evidence": True,
        },
        "upstream_context": {
            "readiness_report_kind": readiness_report.get("report_kind"),
            "readiness_first_batch": (readiness_report.get("first_batch_summary") or {}).get("first_batch") or [],
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    discovery = report.get("artifact_discovery") if isinstance(report.get("artifact_discovery"), Mapping) else {}
    summary = report.get("first_batch_summary") if isinstance(report.get("first_batch_summary"), Mapping) else {}
    first_batch_rows = report.get("first_batch_candidates") if isinstance(report.get("first_batch_candidates"), list) else []
    return "\n".join(
        [
            "# QRE First-Batch Evidence Recovery Cascade",
            "",
            "## 1. Summary",
            _table(
                ["Field", "Value"],
                [
                    ["first_batch", ", ".join(str(v) for v in summary.get("first_batch") or []) or "none"],
                    ["files_scanned", str(discovery.get("files_scanned") or 0)],
                    ["candidate_artifacts", str(discovery.get("candidate_artifacts") or 0)],
                    ["evidence_complete_count", str(summary.get("evidence_complete_count") or 0)],
                    ["trusted_loop_verdict", str(summary.get("trusted_loop_verdict") or "")],
                    ["current_top_blocker", str(summary.get("current_top_blocker") or "")],
                ],
            ),
            "",
            "## 2. First batch candidates",
            _table(
                ["Symbol", "Before blockers", "Artifact signals"],
                [
                    [
                        str(row.get("symbol") or ""),
                        ",".join(str(v) for v in row.get("before_blockers") or []) or "none",
                        str(len(row.get("artifact_signals") or [])),
                    ]
                    for row in first_batch_rows
                ],
            ),
            "",
            "## 3. Validation locator",
            _table(
                ["Trace", "Expected", "Found", "Missing", "Schema status"],
                [
                    [
                        str(row.get("stdout_trace_path") or ""),
                        str(row.get("expected_result_count") or 0),
                        str(row.get("found_result_count") or 0),
                        str(row.get("missing_result_count") or 0),
                        str(row.get("result_schema_status") or ""),
                    ]
                    for row in (report.get("validation_result_locator") or {}).get("rows", [])
                ]
                or [["none", "0", "0", "0", "none"]],
            ),
            "",
            "## 4. Legacy compatibility",
            _table(
                ["Symbol", "Legacy preset", "Target preset", "Legacy tf", "Target tf", "Result"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(row.get("legacy_preset_id") or ""),
                        str(row.get("target_preset_id") or ""),
                        str(row.get("legacy_timeframe") or ""),
                        str(row.get("target_timeframe") or ""),
                        str(row.get("result") or ""),
                    ]
                    for row in (report.get("legacy_compatibility") or {}).get("rows", [])
                ]
                or [["none", "-", "-", "-", "-", "none"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_first_batch_evidence_recovery_cascade: refusing write outside allowlist: {path!r}"
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
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_first_batch_evidence_recovery_cascade",
        description="Build the read-only first-batch evidence recovery cascade report.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_first_batch_evidence_recovery_cascade(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
