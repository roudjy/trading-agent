from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_grid_evidence_readiness_bridge"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_grid_evidence_readiness_bridge")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_grid_evidence_readiness_bridge/"
MATERIALIZATION_PATH: Final[Path] = Path(
    "logs/qre_discovery_basket_grid_evidence_materialization/latest.json"
)
_CLEAN_METRIC_STATUSES: Final[set[str]] = {"clean_consistent", "consistent"}
_BLOCKED_METRIC_STATUSES: Final[set[str]] = {
    "metric_inconsistent",
    "inconsistent_oos_gt_total",
    "missing_total_trades",
    "missing_oos_trades",
    "non_numeric_metric",
    "aggregation_scope_mismatch",
}
_BLOCKED_PRESET_CLASSES: Final[set[str]] = {
    "mapping_missing",
    "preset_not_executable",
    "region_constraint_mismatch",
    "asset_class_constraint_mismatch",
    "timeframe_constraint_mismatch",
    "provider_symbol_unresolved",
    "source_identity_blocked",
    "unsupported_combination",
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


def _criteria_failure_classes(matched_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    values: list[str] = []
    for row in matched_rows:
        criteria_status = str(row.get("criteria_status") or "")
        for part in criteria_status.split(","):
            item = part.strip()
            if item and item not in values:
                values.append(item)
    return values


def _grid_screening_present(matched_rows: Sequence[Mapping[str, Any]]) -> bool:
    for row in matched_rows:
        outcome = str(row.get("outcome_class") or "")
        status = str(row.get("status") or "")
        if outcome in {
            "screening_pass_no_oos",
            "sufficient_oos_evidence",
            "source_identity_provider_lookup_failed",
            "source_identity_provider_symbol_verified",
        }:
            return True
        if status == "completed":
            return True
    return False


def _grid_oos_present(
    matched_rows: Sequence[Mapping[str, Any]],
    *,
    oos_evidence_status: str,
) -> bool:
    if oos_evidence_status in {
        "sufficient_oos_evidence_present",
        "completed_without_sufficient_oos",
        "no_oos_evidence",
    }:
        return True
    return _grid_screening_present(matched_rows)


def _source_identity_blocked(row: Mapping[str, Any]) -> bool:
    return str(row.get("source_identity_status") or "") in {
        "candidate_alias_only",
        "missing_provider_symbol",
    } or str(row.get("source_identity_blocker") or "").startswith("source_identity")


def _metric_clean_for_readiness(metric_status: str) -> bool:
    return metric_status in _CLEAN_METRIC_STATUSES


def _preset_executable_for_readiness(preset_status: str) -> bool:
    return preset_status == "executable"


def _bridge_status(row: Mapping[str, Any]) -> tuple[str, str]:
    matched_rows = row.get("matched_grid_rows")
    if not isinstance(matched_rows, list):
        matched_rows = []
    join_status = str(row.get("join_key_status") or "")
    metric_status = str(row.get("metric_consistency_status") or "unknown_fail_closed")
    preset_status = str(row.get("preset_executability_classification") or "unknown_fail_closed")
    candidate_lineage_status = str(row.get("candidate_lineage_status") or "missing")
    criteria_failures = _criteria_failure_classes(matched_rows)
    sufficient_oos_present = bool(row.get("grid_sufficient_oos_evidence_present"))
    oos_present = bool(row.get("grid_oos_evidence_present"))
    screening_present = bool(row.get("grid_screening_evidence_present"))

    if join_status == "grid_artifact_missing":
        return ("blocked_malformed_artifact", "grid artifact missing or unreadable")
    if join_status in {"no_grid_run_found", "grid_row_match_not_found", "join_key_mismatch"} or not bool(
        row.get("grid_evidence_present")
    ):
        return ("blocked_no_grid_match", "no matching controlled-grid evidence was found")
    if _source_identity_blocked(row):
        return ("blocked_source_identity", "source identity remains unresolved")
    if metric_status in _BLOCKED_METRIC_STATUSES or not _metric_clean_for_readiness(metric_status):
        return ("blocked_metric_inconsistent", "metric consistency blocks clean readiness evidence")
    if preset_status == "intentionally_non_executable":
        return (
            "blocked_intentionally_non_executable",
            "preset is intentionally non-executable for bounded discovery",
        )
    if preset_status in _BLOCKED_PRESET_CLASSES:
        return ("blocked_preset_not_executable", "preset mapping blocks clean readiness evidence")
    if sufficient_oos_present:
        if candidate_lineage_status == "missing":
            return ("blocked_candidate_lineage_missing", "candidate lineage is still missing")
        if candidate_lineage_status in {
            "candidate_visible_campaign_missing",
            "campaign_visible_candidate_missing",
        }:
            return ("blocked_campaign_lineage_missing", "campaign lineage is still missing")
        if criteria_failures:
            return (
                "bridged_sufficient_oos_but_not_promotion_ready",
                "sufficient OOS evidence is visible, but criteria still block promotion",
            )
        return (
            "bridged_sufficient_oos_but_not_promotion_ready",
            "sufficient OOS evidence is visible for readiness only; promotion remains governed elsewhere",
        )
    if oos_present:
        if str(row.get("oos_evidence_status") or "") == "no_oos_evidence":
            return ("blocked_no_oos_evidence", "screening evidence exists but no OOS evidence is present")
        return ("bridged_clean_oos_evidence", "clean OOS evidence is visible to readiness surfaces")
    if screening_present:
        return (
            "bridged_clean_screening_evidence",
            "clean screening evidence is visible to readiness surfaces",
        )
    return ("unknown_fail_closed", "bridge could not classify the readiness evidence state")


def build_grid_evidence_readiness_bridge(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    materialization = _read_json(repo_root / MATERIALIZATION_PATH)
    rows = materialization.get("rows") if isinstance(materialization, Mapping) else None
    if not isinstance(rows, list):
        rows = []

    bridged_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    next_action_counts: Counter[str] = Counter()

    for row in rows[:max_candidates]:
        if not isinstance(row, Mapping):
            continue
        matched_rows = row.get("matched_grid_rows")
        if not isinstance(matched_rows, list):
            matched_rows = []
        metric_status = str(row.get("metric_consistency_status") or "unknown_fail_closed")
        preset_status = str(row.get("preset_executability_classification") or "unknown_fail_closed")
        grid_screening_present = _grid_screening_present(matched_rows)
        grid_oos_present = _grid_oos_present(
            matched_rows,
            oos_evidence_status=str(row.get("oos_evidence_status") or ""),
        )
        grid_sufficient_oos_present = str(row.get("sufficient_oos_evidence_status") or "") == "present"
        clean_for_readiness = (
            _metric_clean_for_readiness(metric_status)
            and not _source_identity_blocked(row)
            and _preset_executable_for_readiness(preset_status)
        )
        candidate_lineage_status = str(row.get("candidate_lineage_status") or "missing")
        readiness_screening_visible = grid_screening_present and clean_for_readiness
        readiness_oos_visible = grid_oos_present and clean_for_readiness
        readiness_sufficient_visible = (
            grid_sufficient_oos_present
            and clean_for_readiness
            and candidate_lineage_status == "visible"
        )

        bridged_row = {
            "basket_id": row.get("basket_id"),
            "asset": row.get("asset"),
            "canonical_symbol": row.get("canonical_symbol"),
            "provider_symbol": row.get("provider_symbol"),
            "timeframe": row.get("timeframe"),
            "preset": row.get("preset"),
            "matched_grid_rows_count": int(row.get("matched_grid_rows_count") or 0),
            "matched_grid_rows": matched_rows,
            "grid_evidence_present": bool(row.get("evidence_exists_in_grid")),
            "grid_screening_evidence_present": grid_screening_present,
            "grid_oos_evidence_present": grid_oos_present,
            "grid_sufficient_oos_evidence_present": grid_sufficient_oos_present,
            "readiness_screening_evidence_visible": readiness_screening_visible,
            "readiness_oos_evidence_visible": readiness_oos_visible,
            "readiness_sufficient_oos_visible": readiness_sufficient_visible,
            "candidate_lineage_status": candidate_lineage_status,
            "candidate_lineage_available": candidate_lineage_status == "visible",
            "campaign_lineage_available": candidate_lineage_status == "visible",
            "source_identity_status": row.get("source_identity_status"),
            "source_identity_blocker": row.get("source_identity_blocker"),
            "metric_consistency_status": metric_status,
            "metric_clean_for_readiness": clean_for_readiness and _metric_clean_for_readiness(metric_status),
            "preset_executability_status": preset_status,
            "survivor_stage_attribution": row.get("survivor_stage_classification"),
            "criteria_status": ",".join(_criteria_failure_classes(matched_rows)),
            "criteria_failure_classes": _criteria_failure_classes(matched_rows),
            "promotion_candidate_from_grid": False,
            "near_pass_from_grid": False,
            "promotion_allowed": False,
            "readiness_evidence_status": (
                "sufficient_oos_visible"
                if readiness_sufficient_visible
                else "oos_visible"
                if readiness_oos_visible
                else "screening_visible"
                if readiness_screening_visible
                else "blocked"
            ),
            "readiness_blocker_category": "",
            "readiness_bridge_status": "",
            "exact_next_action": row.get("exact_next_action") or "keep_fail_closed",
        }
        status, explanation = _bridge_status(bridged_row)
        bridged_row["readiness_bridge_status"] = status
        bridged_row["readiness_blocker_category"] = status
        bridged_row["bridge_explanation"] = explanation
        status_counts.update([status])
        next_action_counts.update([str(bridged_row["exact_next_action"])])
        bridged_rows.append(bridged_row)

    bridged_rows.sort(
        key=lambda row: (
            0 if str(row["readiness_bridge_status"]).startswith("bridged_") else 1,
            str(row["readiness_bridge_status"]),
            str(row["asset"]),
            str(row["preset"]),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(bridged_rows),
            "readiness_bridge_status_counts": dict(sorted(status_counts.items())),
            "grid_screening_visible_count": sum(
                1 for row in bridged_rows if row["readiness_screening_evidence_visible"]
            ),
            "grid_oos_visible_count": sum(
                1 for row in bridged_rows if row["readiness_oos_evidence_visible"]
            ),
            "grid_sufficient_oos_visible_count": sum(
                1 for row in bridged_rows if row["readiness_sufficient_oos_visible"]
            ),
            "next_action_counts": dict(sorted(next_action_counts.items())),
            "operator_summary": (
                "Grid-evidence readiness bridge exposes which controlled-grid findings can safely "
                "count as readiness-visible screening or OOS evidence without relaxing promotion gates."
            ),
        },
        "rows": bridged_rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket count", str(summary.get("basket_count") or 0)],
            ["screening visible", str(summary.get("grid_screening_visible_count") or 0)],
            ["OOS visible", str(summary.get("grid_oos_visible_count") or 0)],
            ["sufficient OOS visible", str(summary.get("grid_sufficient_oos_visible_count") or 0)],
        ],
    )
    bridge_table = _table(
        [
            "Asset",
            "Preset",
            "Bridge status",
            "Screening visible",
            "OOS visible",
            "Sufficient OOS visible",
            "Next action",
        ],
        [
            [
                str(row.get("asset") or ""),
                str(row.get("preset") or ""),
                str(row.get("readiness_bridge_status") or ""),
                "yes" if row.get("readiness_screening_evidence_visible") else "no",
                "yes" if row.get("readiness_oos_evidence_visible") else "no",
                "yes" if row.get("readiness_sufficient_oos_visible") else "no",
                str(row.get("exact_next_action") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Grid Evidence Readiness Bridge",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Aggregate counts",
            count_table,
            "",
            "## 3. Basket bridge status",
            bridge_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_grid_evidence_readiness_bridge: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_grid_evidence_readiness_bridge",
        description="Bridge controlled discovery grid evidence into read-only readiness surfaces.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_grid_evidence_readiness_bridge(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
