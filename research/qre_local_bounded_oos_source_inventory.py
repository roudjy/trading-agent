from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_controlled_validation_source_metadata as source_metadata


REPORT_KIND: Final[str] = "qre_local_bounded_oos_source_inventory"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_local_bounded_oos_source_inventory")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_local_bounded_oos_source_inventory/"
SOURCE_ARTIFACT_DIR: Final[Path] = Path("logs/qre_controlled_validation_adapter_results/source_artifacts")
ADAPTER_RESULT_PATH: Final[Path] = Path("logs/qre_controlled_validation_adapter_results/latest.json")
APPROVED_RUN_PATH: Final[Path] = Path(
    "logs/qre_bounded_current_basket_generation_runner/approved_bounded_validation_execution/latest.json"
)
CONTROLLED_EXECUTION_REPORT_PATH: Final[Path] = Path(
    "logs/qre_controlled_validation_execution/controlled_eval_latest.v1.json"
)
NEXT_ACTION_QUEUE_PATH: Final[Path] = Path("logs/qre_basket_next_action_queue/latest.json")
LOCAL_CACHE_DIR: Final[Path] = Path("data/cache/market")
SUPPORTED_LOCAL_ONLY_PRESETS: Final[frozenset[str]] = frozenset(
    {
        "trend_pullback_continuation_daily_v1",
    }
)
SUPPORTED_LOCAL_ONLY_TIMEFRAMES: Final[frozenset[str]] = frozenset({"daily_v1"})
SOURCE_CLASSIFICATION_ORDER: Final[tuple[str, ...]] = (
    "eligible_existing_structured_oos_source",
    "eligible_but_requires_new_exact_scope_approval",
    "blocked_non_positive_oos_trade_count",
    "blocked_missing_oos_window",
    "blocked_missing_oos_metrics",
    "blocked_missing_cost_slippage_refs",
    "blocked_missing_lineage_metadata",
    "blocked_context_only",
    "blocked_stdout_only",
    "blocked_generated_report_only",
    "blocked_fixture_only",
    "blocked_legacy_alias",
    "blocked_scope_ambiguity",
)
INVENTORY_RESULTS: Final[tuple[str, ...]] = (
    "ELIGIBLE_EXISTING_SOURCE_FOUND",
    "SAFE_LOCAL_WINDOW_GENERATION_AVAILABLE",
    "NO_ELIGIBLE_LOCAL_SOURCE",
    "EXTERNAL_FETCH_APPROVAL_REQUIRED",
    "NO_SAFE_NEXT_ACTION",
)
BLOCKED_SOURCE_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {
        "blocked_non_positive_oos_trade_count",
        "blocked_missing_oos_window",
        "blocked_missing_oos_metrics",
        "blocked_missing_cost_slippage_refs",
        "blocked_missing_lineage_metadata",
        "blocked_context_only",
        "blocked_stdout_only",
        "blocked_generated_report_only",
        "blocked_fixture_only",
        "blocked_legacy_alias",
        "blocked_scope_ambiguity",
    }
)
NON_PERFORMANCE_FIELDS: Final[tuple[str, ...]] = (
    "metadata_complete",
    "positive_oos_trade_count",
    "explicit_oos_window",
    "explicit_cost_slippage_refs",
    "exact_preset_timeframe_identity",
    "structured_source_authority",
    "reproducible_local_path",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [text for item in value if (text := _text(item))]


def _relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _symbol_from_candidate(candidate_id: str) -> str:
    if "::" not in candidate_id:
        return ""
    return _text(candidate_id.rsplit("::", 1)[-1]).upper()


def _materialized_source_details(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(repo_root / ADAPTER_RESULT_PATH)
    if not isinstance(payload, dict):
        return {}
    details: dict[str, dict[str, Any]] = {}
    lineage_candidates = payload.get("lineage_candidates")
    oos_candidates = payload.get("oos_candidates")
    if not isinstance(lineage_candidates, list):
        lineage_candidates = []
    if not isinstance(oos_candidates, list):
        oos_candidates = []
    for candidate in lineage_candidates:
        if not isinstance(candidate, Mapping):
            continue
        source_ref = _text(candidate.get("source_ref"))
        if not source_ref:
            continue
        bucket = details.setdefault(
            source_ref,
            {
                "request_ref": _text(payload.get("request_ref")),
                "preset_id": _text(payload.get("preset_id")),
                "timeframe": _text(payload.get("timeframe")),
                "lineage_candidates": [],
                "oos_candidates": [],
            },
        )
        bucket["lineage_candidates"].append(dict(candidate))
    for candidate in oos_candidates:
        if not isinstance(candidate, Mapping):
            continue
        source_ref = _text(candidate.get("source_ref"))
        if not source_ref:
            continue
        bucket = details.setdefault(
            source_ref,
            {
                "request_ref": _text(payload.get("request_ref")),
                "preset_id": _text(payload.get("preset_id")),
                "timeframe": _text(payload.get("timeframe")),
                "lineage_candidates": [],
                "oos_candidates": [],
            },
        )
        bucket["oos_candidates"].append(dict(candidate))
    return details


def _existing_source_candidate_paths(repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    source_root = repo_root / SOURCE_ARTIFACT_DIR
    if source_root.exists():
        candidates.extend(sorted(path for path in source_root.glob("*.json") if path.is_file()))
    for path in (
        repo_root / CONTROLLED_EXECUTION_REPORT_PATH,
        repo_root / APPROVED_RUN_PATH,
        repo_root / ADAPTER_RESULT_PATH,
    ):
        if path.is_file():
            candidates.append(path)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _existing_source_row(
    *,
    repo_root: Path,
    path: Path,
    payload: Mapping[str, Any],
    materialized_details: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    relative_path = _relative(path, repo_root)
    lowered_path = relative_path.lower()
    metadata = source_metadata.build_controlled_validation_source_metadata(payload)
    explicit_source_ref = _text(payload.get("source_ref")) or relative_path
    details = dict(materialized_details.get(explicit_source_ref) or {})
    lineage_records = payload.get("lineage_records") if isinstance(payload.get("lineage_records"), list) else []
    oos_records = payload.get("oos_records") if isinstance(payload.get("oos_records"), list) else []
    candidate_ids = list(
        dict.fromkeys(
            [
                *[
                    _text(record.get("candidate_id"))
                    for record in lineage_records
                    if isinstance(record, Mapping) and _text(record.get("candidate_id"))
                ],
                *[
                    _text(record.get("candidate_id"))
                    for record in oos_records
                    if isinstance(record, Mapping) and _text(record.get("candidate_id"))
                ],
                *[
                    _text(candidate.get("candidate_id"))
                    for candidate in details.get("lineage_candidates", [])
                    if isinstance(candidate, Mapping) and _text(candidate.get("candidate_id"))
                ],
                *[
                    _text(candidate.get("candidate_id"))
                    for candidate in details.get("oos_candidates", [])
                    if isinstance(candidate, Mapping) and _text(candidate.get("candidate_id"))
                ],
            ]
        )
    )
    symbols = list(dict.fromkeys(symbol for candidate_id in candidate_ids if (symbol := _symbol_from_candidate(candidate_id))))
    generation_ids = list(
        dict.fromkeys(
            [
                *[
                    _text(record.get("generation_run_id") or record.get("grid_run_id"))
                    for record in lineage_records
                    if isinstance(record, Mapping)
                    and _text(record.get("generation_run_id") or record.get("grid_run_id"))
                ],
                *[
                    _text(candidate.get("generation_id") or candidate.get("grid_run_id"))
                    for candidate in details.get("lineage_candidates", [])
                    if isinstance(candidate, Mapping)
                    and _text(candidate.get("generation_id") or candidate.get("grid_run_id"))
                ],
            ]
        )
    )
    campaign_ids = list(
        dict.fromkeys(
            [
                _text(candidate.get("campaign_id"))
                for candidate in details.get("lineage_candidates", [])
                if isinstance(candidate, Mapping) and _text(candidate.get("campaign_id"))
            ]
        )
    )
    oos_windows = [
        dict(record.get("oos_window"))
        for record in oos_records
        if isinstance(record, Mapping) and isinstance(record.get("oos_window"), Mapping)
    ]
    oos_trade_counts: list[int | float] = []
    has_oos_metrics = False
    has_cost_refs = False
    for record in oos_records:
        if not isinstance(record, Mapping):
            continue
        metrics = record.get("oos_metric_fields")
        if isinstance(metrics, Mapping) and metrics:
            has_oos_metrics = True
            if metrics.get("oos_trade_count") not in (None, ""):
                oos_trade_counts.append(metrics.get("oos_trade_count"))  # type: ignore[arg-type]
        cost_refs = _text_list(record.get("cost_slippage_assumption_refs"))
        if cost_refs:
            has_cost_refs = True
    report_kind = _text(payload.get("report_kind"))
    source_authority = _text(payload.get("source_authority"))
    source_type = _text(payload.get("source_type"))
    is_fixture = lowered_path.startswith("tests/") or "fixture" in lowered_path
    is_stdout_only = "stdout" in lowered_path or source_type == "stdout_only"
    is_legacy_alias = "legacy_alias" in lowered_path or source_type == "legacy_alias_only"
    is_context_only = source_authority == "context_only" or source_type == "context_only"
    is_generated_report = (
        not relative_path.startswith(SOURCE_ARTIFACT_DIR.as_posix())
        and report_kind.startswith("qre_")
    )
    rejection_reasons: list[str] = []
    if is_fixture:
        classification = "blocked_fixture_only"
        rejection_reasons.append("fixture_only_source")
    elif is_stdout_only:
        classification = "blocked_stdout_only"
        rejection_reasons.append("stdout_only_source")
    elif is_legacy_alias:
        classification = "blocked_legacy_alias"
        rejection_reasons.append("legacy_alias_only_source")
    elif is_context_only:
        classification = "blocked_context_only"
        rejection_reasons.append("context_only_source")
    elif is_generated_report:
        classification = "blocked_generated_report_only"
        rejection_reasons.append("generated_report_only_source")
    elif metadata["metadata_status"] != "metadata_complete":
        classification = "blocked_missing_lineage_metadata"
        rejection_reasons.extend(_text_list(metadata.get("reasons")))
    elif not oos_windows or not all(_text(window.get("start")) and _text(window.get("end")) for window in oos_windows):
        classification = "blocked_missing_oos_window"
        rejection_reasons.append("missing_oos_window")
    elif not has_oos_metrics:
        classification = "blocked_missing_oos_metrics"
        rejection_reasons.append("missing_oos_metrics")
    elif not has_cost_refs:
        classification = "blocked_missing_cost_slippage_refs"
        rejection_reasons.append("missing_cost_slippage_refs")
    elif oos_trade_counts and all(float(value) > 0 for value in oos_trade_counts):
        classification = "eligible_existing_structured_oos_source"
    elif oos_trade_counts:
        classification = "blocked_non_positive_oos_trade_count"
        rejection_reasons.append("non_positive_oos_trade_count")
    else:
        classification = "blocked_scope_ambiguity"
        rejection_reasons.append("missing_oos_trade_count")
    preset_id = _text(details.get("preset_id"))
    timeframe = _text(details.get("timeframe"))
    suitability_score = sum(
        [
            1 if metadata["metadata_status"] == "metadata_complete" else 0,
            1 if any(float(value) > 0 for value in oos_trade_counts if value not in (None, "")) else 0,
            1 if bool(oos_windows) else 0,
            1 if has_cost_refs else 0,
            1 if bool(preset_id and timeframe) else 0,
            1 if source_authority == "structured_source" else 0,
            1 if relative_path.startswith(SOURCE_ARTIFACT_DIR.as_posix()) else 0,
        ]
    )
    return {
        "row_kind": "existing_source",
        "source_artifact_ref": explicit_source_ref,
        "classification": classification,
        "candidate_ids": candidate_ids,
        "campaign_ids": campaign_ids,
        "generation_ids": generation_ids,
        "symbols": symbols,
        "preset_id": preset_id,
        "timeframe": timeframe,
        "oos_windows": oos_windows,
        "oos_trade_count": oos_trade_counts,
        "oos_metrics_present": has_oos_metrics,
        "cost_slippage_refs_present": has_cost_refs,
        "validation_status": _text(payload.get("validation_status")) or "structured_source_present",
        "lineage_metadata_completeness": _text(metadata.get("metadata_status")),
        "source_authority": source_authority or report_kind or "unknown",
        "fixture_or_test_flag": is_fixture,
        "generated_report_only_flag": is_generated_report,
        "context_only_flag": is_context_only,
        "stdout_only_flag": is_stdout_only,
        "legacy_alias_only_flag": is_legacy_alias,
        "approval_eligibility": classification == "eligible_existing_structured_oos_source",
        "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
        "evidence_suitability_score": suitability_score,
        "selection_basis": list(NON_PERFORMANCE_FIELDS),
    }


def _queue_candidate_rows(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / NEXT_ACTION_QUEUE_PATH)
    rows = payload.get("rows") if isinstance(payload, Mapping) else []
    if not isinstance(rows, list):
        return []
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        candidate_id = _text(row.get("candidate_id"))
        symbol = _text(row.get("symbol")).upper()
        preset_id = _text(row.get("preset_id"))
        if not candidate_id or not symbol or not preset_id:
            continue
        key = (candidate_id, symbol, preset_id)
        if key in unique:
            continue
        unique[key] = dict(row)
    return list(unique.values())


def _has_local_cache(repo_root: Path, symbol: str, timeframe: str) -> bool:
    interval = "1d" if timeframe == "daily_v1" else timeframe
    pattern = f"yfinance__{symbol.upper()}__{interval}__*.parquet"
    return any((repo_root / LOCAL_CACHE_DIR).glob(pattern))


def _distinct_window_generation_rows(
    *,
    repo_root: Path,
    existing_source_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    existing_scopes = {
        (
            tuple(_text_list(row.get("symbols"))),
            _text(row.get("preset_id")),
            _text(row.get("timeframe")),
        )
        for row in existing_source_rows
    }
    for row in _queue_candidate_rows(repo_root):
        candidate_id = _text(row.get("candidate_id"))
        symbol = _text(row.get("symbol")).upper()
        preset_id = _text(row.get("preset_id"))
        if preset_id not in SUPPORTED_LOCAL_ONLY_PRESETS:
            continue
        timeframe = "daily_v1"
        source_scope = ((symbol,), preset_id, timeframe)
        distinct_from_existing = source_scope not in existing_scopes
        has_local_cache = _has_local_cache(repo_root, symbol, timeframe)
        if not has_local_cache:
            classification = "blocked_scope_ambiguity"
            rejection_reasons = ["local_cache_unavailable"]
        elif not distinct_from_existing:
            classification = "blocked_scope_ambiguity"
            rejection_reasons = ["no_distinct_local_scope_from_existing_source"]
        else:
            classification = "eligible_but_requires_new_exact_scope_approval"
            rejection_reasons = []
        rows.append(
            {
                "row_kind": "preregisterable_window_candidate",
                "source_artifact_ref": "",
                "classification": classification,
                "candidate_ids": [candidate_id],
                "campaign_ids": [],
                "generation_ids": [],
                "symbols": [symbol],
                "preset_id": preset_id,
                "timeframe": timeframe,
                "oos_windows": [],
                "oos_trade_count": [],
                "oos_metrics_present": False,
                "cost_slippage_refs_present": False,
                "validation_status": "not_run",
                "lineage_metadata_completeness": "not_applicable_preregistered_window",
                "source_authority": "local_cache_candidate_scope",
                "fixture_or_test_flag": False,
                "generated_report_only_flag": False,
                "context_only_flag": False,
                "stdout_only_flag": False,
                "legacy_alias_only_flag": False,
                "approval_eligibility": classification == "eligible_but_requires_new_exact_scope_approval",
                "rejection_reasons": rejection_reasons,
                "evidence_suitability_score": 2 if classification == "eligible_but_requires_new_exact_scope_approval" else 1,
                "selection_basis": list(NON_PERFORMANCE_FIELDS),
            }
        )
    return rows


def _result_from_rows(
    *,
    existing_source_rows: Sequence[Mapping[str, Any]],
    preregisterable_rows: Sequence[Mapping[str, Any]],
) -> str:
    eligible_existing = any(_text(row.get("classification")) == "eligible_existing_structured_oos_source" for row in existing_source_rows)
    if eligible_existing:
        return "ELIGIBLE_EXISTING_SOURCE_FOUND"
    eligible_preregistered = any(
        _text(row.get("classification")) == "eligible_but_requires_new_exact_scope_approval"
        for row in preregisterable_rows
    )
    if eligible_preregistered:
        return "SAFE_LOCAL_WINDOW_GENERATION_AVAILABLE"
    if preregisterable_rows:
        return "NO_SAFE_NEXT_ACTION"
    return "NO_ELIGIBLE_LOCAL_SOURCE"


def compute_inventory_hash(report: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "inventory_result": report.get("inventory_result", ""),
        "eligible_source_count": int(report.get("eligible_source_count") or 0),
        "eligible_window_count": int(report.get("eligible_window_count") or 0),
        "blocked_source_count": int(report.get("blocked_source_count") or 0),
        "top_approval_candidates": report.get("top_approval_candidates", []),
        "exact_approval_scope_recommendation": report.get("exact_approval_scope_recommendation", {}),
        "inventory_rows": report.get("inventory_rows", []),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_local_bounded_oos_source_inventory(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    materialized_details = _materialized_source_details(repo_root)
    existing_rows = [
        _existing_source_row(
            repo_root=repo_root,
            path=path,
            payload=payload,
            materialized_details=materialized_details,
        )
        for path in _existing_source_candidate_paths(repo_root)
        if (payload := _read_json(path)) is not None
    ]
    preregisterable_rows = _distinct_window_generation_rows(
        repo_root=repo_root,
        existing_source_rows=existing_rows,
    )
    all_rows = [*existing_rows, *preregisterable_rows]
    all_rows.sort(
        key=lambda row: (
            0 if _text(row.get("classification")) == "eligible_existing_structured_oos_source" else 1,
            0 if _text(row.get("classification")) == "eligible_but_requires_new_exact_scope_approval" else 1,
            -int(row.get("evidence_suitability_score") or 0),
            SOURCE_CLASSIFICATION_ORDER.index(_text(row.get("classification")))
            if _text(row.get("classification")) in SOURCE_CLASSIFICATION_ORDER
            else len(SOURCE_CLASSIFICATION_ORDER),
            _text(row.get("preset_id")),
            ",".join(_text_list(row.get("symbols"))),
            _text(row.get("source_artifact_ref")),
        )
    )
    top_candidates = [
        {
            "classification": _text(row.get("classification")),
            "symbols": _text_list(row.get("symbols")),
            "preset_id": _text(row.get("preset_id")),
            "timeframe": _text(row.get("timeframe")),
            "source_artifact_ref": _text(row.get("source_artifact_ref")),
            "rejection_reasons": _text_list(row.get("rejection_reasons")),
        }
        for row in all_rows
        if _text(row.get("classification"))
        in {"eligible_existing_structured_oos_source", "eligible_but_requires_new_exact_scope_approval"}
    ][:3]
    inventory_result = _result_from_rows(
        existing_source_rows=existing_rows,
        preregisterable_rows=preregisterable_rows,
    )
    exact_scope_recommendation = top_candidates[0] if top_candidates else {}
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "inventory_result": inventory_result,
        "inventory_rows": all_rows,
        "eligible_source_count": sum(
            1 for row in all_rows if _text(row.get("classification")) == "eligible_existing_structured_oos_source"
        ),
        "eligible_window_count": sum(
            1 for row in all_rows if _text(row.get("classification")) == "eligible_but_requires_new_exact_scope_approval"
        ),
        "blocked_source_count": sum(
            1 for row in all_rows if _text(row.get("classification")) in BLOCKED_SOURCE_CLASSIFICATIONS
        ),
        "top_approval_candidates": top_candidates,
        "exact_approval_scope_recommendation": exact_scope_recommendation,
        "selection_ranking_fields": list(NON_PERFORMANCE_FIELDS),
        "profitability_fields_used": [],
        "safe_local_window_generation_supported_presets": sorted(SUPPORTED_LOCAL_ONLY_PRESETS),
        "safe_local_window_generation_supported_timeframes": sorted(SUPPORTED_LOCAL_ONLY_TIMEFRAMES),
    }
    report["hash"] = compute_inventory_hash(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Local Bounded OOS Source Inventory",
            "",
            f"- inventory_result: {report.get('inventory_result', '')}",
            f"- eligible_source_count: {report.get('eligible_source_count', 0)}",
            f"- eligible_window_count: {report.get('eligible_window_count', 0)}",
            f"- blocked_source_count: {report.get('blocked_source_count', 0)}",
            f"- top_approval_candidates: {len(report.get('top_approval_candidates', []))}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
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
        prog="python -m research.qre_local_bounded_oos_source_inventory",
        description="Inventory local bounded OOS sources and preregisterable windows.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_local_bounded_oos_source_inventory()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
