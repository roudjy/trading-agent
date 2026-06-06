from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import production_discovery_catalog as catalog


REPORT_KIND: Final[str] = "qre_controlled_discovery_metric_consistency_audit"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_discovery_metric_consistency_audit")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_controlled_discovery_metric_consistency_audit/"
GRID_RUNS_DIR: Final[Path] = Path("research/controlled_discovery_grid_runs")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], bool]:
    if not path.is_file():
        return [], False
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
        return [], False
    return rows, True


def _latest_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest_by_sequence: dict[int, dict[str, Any]] = {}
    ordered: list[int] = []
    for row in rows:
        sequence_number = int(row.get("sequence_number") or 0)
        if sequence_number not in latest_by_sequence:
            ordered.append(sequence_number)
        latest_by_sequence[sequence_number] = dict(row)
    return [latest_by_sequence[sequence_number] for sequence_number in ordered]


def _scan_grid_rows(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / GRID_RUNS_DIR
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        run_rows, ok = _load_jsonl(run_dir / "combination_results.v1.jsonl")
        if not ok:
            continue
        for row in _latest_rows(run_rows):
            rows.append({**row, "run_id": run_dir.name})
    rows.sort(
        key=lambda row: (
            str(row.get("run_id") or ""),
            int(row.get("sequence_number") or 0),
        )
    )
    return rows


def _basket_index(max_candidates: int) -> dict[tuple[str, str], str]:
    return {
        (str(row.get("symbol") or ""), str(row.get("preset_id") or "")): str(row.get("candidate_id") or "")
        for row in catalog.build_bounded_candidate_basket(max_candidates=max_candidates)
    }


def _classify_row(row: Mapping[str, Any]) -> tuple[str, list[str], str]:
    trades_raw = row.get("trades_total")
    oos_raw = row.get("oos_trades")
    hd_raw = row.get("hd_trades")
    warnings: list[str] = []
    if trades_raw not in (None, "") and _coerce_number(trades_raw) is None:
        return "non_numeric_metric", ["non_numeric_trades_total"], "trades_total is not numeric"
    if oos_raw not in (None, "") and _coerce_number(oos_raw) is None:
        return "non_numeric_metric", ["non_numeric_oos_trades"], "oos_trades is not numeric"
    if hd_raw not in (None, "") and _coerce_number(hd_raw) is None:
        return "non_numeric_metric", ["non_numeric_hd_trades"], "hd_trades is not numeric"

    trades_total = _coerce_number(trades_raw)
    oos_trades = _coerce_number(oos_raw)
    hd_trades = _coerce_number(hd_raw)
    scope_hint = str(row.get("metric_scope_note") or row.get("aggregation_scope_hint") or "")

    if trades_total is None and (oos_trades is not None or hd_trades is not None):
        return "missing_total_trades", ["missing_total_trades"], "trades_total is missing"
    if oos_trades is None and trades_total is not None:
        return "missing_oos_trades", ["missing_oos_trades"], "oos_trades is missing"
    if trades_total is None and oos_trades is None:
        return "unknown_fail_closed", ["no_trade_metrics_present"], "trade metrics missing"
    if scope_hint == "aggregation_scope_mismatch":
        warnings.append("aggregation_scope_mismatch")
        return (
            "aggregation_scope_mismatch",
            warnings,
            "explicit aggregation scope hint prevents clean interpretation",
        )
    if (
        trades_total is not None
        and oos_trades is not None
        and oos_trades > trades_total + 0.5
    ):
        warnings.append("oos_trades_exceeds_trades_total")
        return (
            "inconsistent_oos_gt_total",
            warnings,
            "oos_trades exceeds trades_total and cannot count as clean evidence",
        )
    return "clean_consistent", warnings, "trade metrics are internally consistent"


def build_metric_consistency_audit(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    rows = _scan_grid_rows(repo_root)
    basket_ids = _basket_index(max_candidates)
    audit_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    affected_symbols: set[str] = set()
    affected_presets: set[str] = set()
    affected_baskets: set[str] = set()
    for row in rows:
        symbol = str(row.get("instrument_symbol") or "")
        preset = str(row.get("behavior_preset_id") or "")
        classification, warnings, explanation = _classify_row(row)
        counts.update([classification])
        if classification != "clean_consistent":
            affected_symbols.add(symbol)
            affected_presets.add(preset)
            basket_id = basket_ids.get((symbol, preset))
            if basket_id:
                affected_baskets.add(basket_id)
        audit_rows.append(
            {
                "run_id": str(row.get("run_id") or ""),
                "sequence_number": int(row.get("sequence_number") or 0),
                "instrument_symbol": symbol,
                "behavior_preset_id": preset,
                "trades_total": row.get("trades_total"),
                "oos_trades": row.get("oos_trades"),
                "hd_trades": row.get("hd_trades"),
                "classification": classification,
                "warnings": warnings,
                "explanation": explanation,
                "no_alpha_interpretation": classification != "clean_consistent",
                "affected_basket_ids": [basket_ids[(symbol, preset)]]
                if (symbol, preset) in basket_ids
                else [],
            }
        )
    audit_rows.sort(
        key=lambda row: (
            0 if row["classification"] != "clean_consistent" else 1,
            str(row["instrument_symbol"]),
            str(row["behavior_preset_id"]),
            int(row["sequence_number"]),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "total_rows_checked": len(audit_rows),
            "rows_consistent": counts.get("clean_consistent", 0),
            "rows_inconsistent": len(audit_rows) - counts.get("clean_consistent", 0),
            "inconsistent_oos_gt_total_count": counts.get("inconsistent_oos_gt_total", 0),
            "aggregation_scope_mismatch_count": counts.get("aggregation_scope_mismatch", 0),
            "no_alpha_interpretation_count": sum(
                bool(row["no_alpha_interpretation"]) for row in audit_rows
            ),
            "affected_symbols": sorted(affected_symbols),
            "affected_presets": sorted(affected_presets),
            "affected_baskets": sorted(affected_baskets),
            "top_inconsistent_rows": [
                {
                    "instrument_symbol": row["instrument_symbol"],
                    "behavior_preset_id": row["behavior_preset_id"],
                    "classification": row["classification"],
                    "trades_total": row["trades_total"],
                    "oos_trades": row["oos_trades"],
                }
                for row in audit_rows
                if row["classification"] != "clean_consistent"
            ][:10],
            "exact_next_action": "inspect_metric_consistency",
            "operator_summary": (
                "Controlled discovery metric audit classifies whether trade counts are clean, "
                "scope-mismatched, or inconsistent. Inconsistent rows remain diagnostic-only and "
                "cannot be treated as clean OOS evidence."
            ),
        },
        "rows": audit_rows,
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
            ["total rows checked", str(summary.get("total_rows_checked") or 0)],
            ["rows consistent", str(summary.get("rows_consistent") or 0)],
            ["rows inconsistent", str(summary.get("rows_inconsistent") or 0)],
            [
                "inconsistent oos > total",
                str(summary.get("inconsistent_oos_gt_total_count") or 0),
            ],
            [
                "aggregation scope mismatch",
                str(summary.get("aggregation_scope_mismatch_count") or 0),
            ],
            [
                "no alpha interpretation",
                str(summary.get("no_alpha_interpretation_count") or 0),
            ],
        ],
    )
    row_table = _table(
        ["Instrument", "Preset", "Trades total", "OOS trades", "HD trades", "Classification", "Warnings"],
        [
            [
                str(row.get("instrument_symbol") or ""),
                str(row.get("behavior_preset_id") or ""),
                str(row.get("trades_total") or ""),
                str(row.get("oos_trades") or ""),
                str(row.get("hd_trades") or ""),
                str(row.get("classification") or ""),
                ", ".join(str(value) for value in row.get("warnings") or []) or "-",
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Controlled Discovery Metric Consistency Audit",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Aggregate counts",
            count_table,
            "",
            "## 3. Affected rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_controlled_discovery_metric_consistency_audit: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_controlled_discovery_metric_consistency_audit",
        description="Audit trade-metric consistency for controlled discovery grid rows.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_metric_consistency_audit(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
