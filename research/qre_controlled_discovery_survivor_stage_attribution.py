from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_controlled_discovery_metric_consistency_audit as metric_audit
from research import qre_controlled_discovery_preset_executability as executability


REPORT_KIND: Final[str] = "qre_controlled_discovery_survivor_stage_attribution"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_discovery_survivor_stage_attribution")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_controlled_discovery_survivor_stage_attribution/"
GRID_RUNS_DIR: Final[Path] = Path("research/controlled_discovery_grid_runs")
METRIC_AUDIT_PATH: Final[Path] = Path("logs/qre_controlled_discovery_metric_consistency_audit/latest.json")
PRESET_EXECUTABILITY_PATH: Final[Path] = Path("logs/qre_controlled_discovery_preset_executability/latest.json")
DEGENERATE_STAGE_CLASSES: Final[set[str]] = {
    "no_candidates_generated",
    "screening_stage_no_survivors",
    "oos_stage_no_survivors",
    "criteria_stage_no_survivors",
    "metric_consistency_stage_no_survivors",
    "source_identity_stage_blocked",
    "preset_mapping_stage_blocked",
    "artifact_missing_stage_blocked",
    "adapter_join_stage_blocked",
    "degenerate_legitimate_no_survivors",
    "unknown_fail_closed",
}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
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
        return []
    return rows


def _latest_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest_by_sequence: dict[int, dict[str, Any]] = {}
    ordered_sequences: list[int] = []
    for row in rows:
        sequence_number = int(row.get("sequence_number") or 0)
        if sequence_number not in latest_by_sequence:
            ordered_sequences.append(sequence_number)
        latest_by_sequence[sequence_number] = dict(row)
    return [latest_by_sequence[sequence_number] for sequence_number in ordered_sequences]


def _scan_rows(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / GRID_RUNS_DIR
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        run_rows = _load_jsonl(run_dir / "combination_results.v1.jsonl")
        for row in _latest_rows(run_rows):
            rows.append({**row, "run_id": run_dir.name})
    rows.sort(
        key=lambda row: (
            str(row.get("run_id") or ""),
            int(row.get("sequence_number") or 0),
        )
    )
    return rows


def _execution_sidecar(repo_root: Path, row: Mapping[str, Any]) -> dict[str, Any] | None:
    artifact_paths = row.get("artifact_paths")
    if isinstance(artifact_paths, Mapping):
        execution_path = artifact_paths.get("execution_result")
        if isinstance(execution_path, str) and execution_path:
            payload = _load_json(repo_root / execution_path)
            if payload:
                return payload
    result_path = row.get("result_path")
    if isinstance(result_path, str) and result_path:
        return _load_json(repo_root / result_path)
    return None


def _metric_index(repo_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    report = _load_json(repo_root / METRIC_AUDIT_PATH) or metric_audit.build_metric_consistency_audit(
        repo_root=repo_root
    )
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    return {
        (str(row.get("instrument_symbol") or ""), str(row.get("behavior_preset_id") or "")): row
        for row in rows
    }


def _preset_index(repo_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    report = _load_json(repo_root / PRESET_EXECUTABILITY_PATH) or executability.build_preset_executability_report(
        max_candidates=15
    )
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    return {
        (str(row.get("instrument_symbol") or ""), str(row.get("behavior_preset_id") or "")): row
        for row in rows
    }


def _classify_stage(
    *,
    row: Mapping[str, Any],
    sidecar: Mapping[str, Any] | None,
    metric_row: Mapping[str, Any] | None,
    preset_row: Mapping[str, Any] | None,
) -> tuple[str, str]:
    hint = str(row.get("degenerate_stage_hint") or "")
    if hint in DEGENERATE_STAGE_CLASSES:
        return hint, "explicit degenerate stage hint present"

    preset_classification = str((preset_row or {}).get("classification") or "")
    if preset_classification in {"source_identity_blocked", "provider_symbol_unresolved"}:
        return "source_identity_stage_blocked", "source identity prevented survivorship"
    if preset_classification in {
        "mapping_missing",
        "intentionally_non_executable",
        "region_constraint_mismatch",
        "asset_class_constraint_mismatch",
        "timeframe_constraint_mismatch",
        "unsupported_combination",
    }:
        return "preset_mapping_stage_blocked", "preset mapping prevented survivorship"

    metric_classification = str((metric_row or {}).get("classification") or "")
    if metric_classification in {
        "inconsistent_oos_gt_total",
        "missing_total_trades",
        "missing_oos_trades",
        "non_numeric_metric",
        "aggregation_scope_mismatch",
    }:
        return "metric_consistency_stage_no_survivors", "metric audit prevents clean survivor interpretation"

    if sidecar is None:
        return "artifact_missing_stage_blocked", "execution sidecar is missing"

    observation = sidecar.get("observation") if isinstance(sidecar.get("observation"), Mapping) else {}
    artifact_snapshot = (
        sidecar.get("artifact_snapshot") if isinstance(sidecar.get("artifact_snapshot"), Mapping) else {}
    )
    matching_rows = (
        artifact_snapshot.get("matching_screening_rows")
        if isinstance(artifact_snapshot.get("matching_screening_rows"), list)
        else []
    )
    candidate_count = int(observation.get("candidate_count") or 0)

    join_status = str(sidecar.get("adapter_join_status") or "")
    if join_status == "blocked":
        return "adapter_join_stage_blocked", "adapter join remained blocked despite available artifacts"
    if candidate_count == 0 and not matching_rows:
        return "no_candidates_generated", "execution completed without any matching candidate rows"
    if not matching_rows:
        return "screening_stage_no_survivors", "screening produced no surviving rows"

    validation_statuses = {
        str((item.get("validation_evidence") or {}).get("status") or "")
        for item in matching_rows
        if isinstance(item, Mapping)
    }
    blocked_by = {
        str(blocker)
        for item in matching_rows
        if isinstance(item, Mapping)
        for blocker in list((item.get("promotion_guard") or {}).get("blocked_by") or [])
    }
    stage_results = {
        str(item.get("stage_result") or "")
        for item in matching_rows
        if isinstance(item, Mapping)
    }
    if blocked_by:
        return "criteria_stage_no_survivors", "criteria filters removed all surviving rows"
    if validation_statuses & {"no_oos_trades", "insufficient_oos_trades"}:
        return "oos_stage_no_survivors", "OOS validation removed all surviving rows"
    if "screening_reject" in stage_results:
        return "screening_stage_no_survivors", "screening rejected all rows"
    return "degenerate_legitimate_no_survivors", "no explicit earlier stage blocker was found"


def build_survivor_stage_attribution(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    grid_rows = _scan_rows(repo_root)
    metric_index = _metric_index(repo_root)
    preset_index = _preset_index(repo_root)
    rows: list[dict[str, Any]] = []
    stage_counts: Counter[str] = Counter()
    affected_symbols: set[str] = set()
    affected_presets: set[str] = set()
    affected_baskets: set[str] = set()

    for row in grid_rows:
        blocker_class = str(row.get("blocker_class") or "")
        hint = str(row.get("degenerate_stage_hint") or "")
        if blocker_class != "degenerate_no_survivors" and hint not in DEGENERATE_STAGE_CLASSES:
            continue
        symbol = str(row.get("instrument_symbol") or "")
        preset = str(row.get("behavior_preset_id") or "")
        sidecar = _execution_sidecar(repo_root, row)
        metric_row = metric_index.get((symbol, preset))
        preset_row = preset_index.get((symbol, preset))
        stage_classification, explanation = _classify_stage(
            row=row,
            sidecar=sidecar,
            metric_row=metric_row,
            preset_row=preset_row,
        )
        stage_counts.update([stage_classification])
        affected_symbols.add(symbol)
        affected_presets.add(preset)
        for basket_id in list((metric_row or {}).get("affected_basket_ids") or []) + list(
            (preset_row or {}).get("affected_basket_ids") or []
        ):
            if basket_id:
                affected_baskets.add(str(basket_id))
        rows.append(
            {
                "run_id": str(row.get("run_id") or ""),
                "sequence_number": int(row.get("sequence_number") or 0),
                "instrument_symbol": symbol,
                "behavior_preset_id": preset,
                "stage_classification": stage_classification,
                "explanation": explanation,
                "metric_classification": str((metric_row or {}).get("classification") or ""),
                "preset_classification": str((preset_row or {}).get("classification") or ""),
                "affected_basket_ids": sorted(affected_baskets),
            }
        )
    rows.sort(
        key=lambda row: (
            str(row["stage_classification"]),
            str(row["instrument_symbol"]),
            str(row["behavior_preset_id"]),
            int(row["sequence_number"]),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "total_degenerate_rows": len(rows),
            "attributed_degenerate_rows": sum(
                row["stage_classification"] != "unknown_fail_closed" for row in rows
            ),
            "unknown_degenerate_rows": stage_counts.get("unknown_fail_closed", 0),
            "stage_counts": dict(sorted(stage_counts.items())),
            "affected_symbols": sorted(affected_symbols),
            "affected_presets": sorted(affected_presets),
            "affected_baskets": sorted(affected_baskets),
            "top_stage_blockers": [
                {"stage_classification": key, "count": value}
                for key, value in stage_counts.most_common(10)
            ],
            "next_action_counts": dict(
                sorted(
                    Counter(
                        "inspect_stage_blocker"
                        if row["stage_classification"] != "degenerate_legitimate_no_survivors"
                        else "keep_blocked"
                        for row in rows
                    ).items()
                )
            ),
            "operator_summary": (
                "Degenerate no-survivor attribution shows which stage removed the remaining rows "
                "instead of collapsing every case into a single coarse blocker."
            ),
        },
        "rows": rows,
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
            ["total degenerate rows", str(summary.get("total_degenerate_rows") or 0)],
            ["attributed", str(summary.get("attributed_degenerate_rows") or 0)],
            ["unknown", str(summary.get("unknown_degenerate_rows") or 0)],
        ],
    )
    row_table = _table(
        ["Instrument", "Preset", "Stage classification", "Metric", "Preset", "Explanation"],
        [
            [
                str(row.get("instrument_symbol") or ""),
                str(row.get("behavior_preset_id") or ""),
                str(row.get("stage_classification") or ""),
                str(row.get("metric_classification") or "-"),
                str(row.get("preset_classification") or "-"),
                str(row.get("explanation") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Controlled Discovery Survivor Stage Attribution",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Aggregate counts",
            count_table,
            "",
            "## 3. Stage attribution",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_controlled_discovery_survivor_stage_attribution: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_controlled_discovery_survivor_stage_attribution",
        description="Attribute degenerate no-survivor rows to explicit research stages.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_survivor_stage_attribution()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
