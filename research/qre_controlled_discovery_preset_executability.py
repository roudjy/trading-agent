from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import controlled_discovery_grid
from research import controlled_discovery_grid_execution as execution
from research import production_discovery_catalog as catalog


REPORT_KIND: Final[str] = "qre_controlled_discovery_preset_executability"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_discovery_preset_executability")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_controlled_discovery_preset_executability/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _basket_index(max_candidates: int) -> dict[tuple[str, str], str]:
    return {
        (str(row.get("symbol") or ""), str(row.get("preset_id") or "")): str(row.get("candidate_id") or "")
        for row in catalog.build_bounded_candidate_basket(max_candidates=max_candidates)
    }


def _classify_row(
    row: Mapping[str, Any],
    mapping: execution.GridExecutionMapping,
) -> tuple[str, str]:
    source_identity_status = str(row.get("source_identity_status") or "")
    provider_symbol_status = str(row.get("provider_symbol_status") or "")
    provider_symbol = row.get("primary_data_provider_symbol")
    if source_identity_status == "candidate_alias_only":
        return "source_identity_blocked", "candidate alias remains unresolved for discovery use"
    if not provider_symbol:
        return "provider_symbol_unresolved", "primary provider symbol missing"
    if mapping.status == "ready":
        return "executable", "existing executable mapping is available"
    blocker = str(mapping.blocker_class or "")
    if blocker == execution.BLOCKER_MISSING_METADATA:
        return "mapping_missing", "required mapping metadata is missing"
    if blocker == execution.BLOCKER_REGION_MISMATCH:
        return "region_constraint_mismatch", "preset mapping excludes the asset region"
    if blocker == execution.BLOCKER_ASSET_CLASS_MISMATCH:
        return "asset_class_constraint_mismatch", "preset mapping excludes the asset class"
    if blocker == "preset_not_executable":
        return "intentionally_non_executable", "preset is seed-only and has no executable mapping"
    if blocker == execution.BLOCKER_UNSUPPORTED_MAPPING:
        return "mapping_missing", "no supported executable mapping exists"
    if blocker == execution.BLOCKER_SAFETY_VIOLATION:
        return "unknown_fail_closed", "safety invariants block execution"
    if not row.get("timeframe"):
        return "timeframe_constraint_mismatch", "timeframe metadata missing"
    return "unsupported_combination", "combination stays blocked by bounded mapping rules"


def build_preset_executability_report(*, max_candidates: int = 15) -> dict[str, Any]:
    grid_rows = controlled_discovery_grid.build_controlled_discovery_grid()
    basket_ids = _basket_index(max_candidates)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    affected_assets: set[str] = set()
    affected_presets: set[str] = set()
    for row in grid_rows:
        mapping = execution.map_grid_row_to_execution(dict(row))
        classification, explanation = _classify_row(row, mapping)
        counts.update([classification])
        symbol = str(row.get("instrument_symbol") or "")
        preset = str(row.get("behavior_preset_id") or "")
        if classification != "executable":
            affected_assets.add(symbol)
            affected_presets.add(preset)
        rows.append(
            {
                "sequence_number": int(row.get("sequence_number") or 0),
                "instrument_symbol": symbol,
                "behavior_preset_id": preset,
                "classification": classification,
                "mapping_status": mapping.status,
                "blocker_class": mapping.blocker_class,
                "region": row.get("region"),
                "asset_class": row.get("asset_class"),
                "timeframe": row.get("timeframe"),
                "provider_symbol_status": row.get("provider_symbol_status"),
                "source_identity_status": row.get("source_identity_status"),
                "primary_data_provider_symbol": row.get("primary_data_provider_symbol"),
                "affected_basket_ids": [basket_ids[(symbol, preset)]]
                if (symbol, preset) in basket_ids
                else [],
                "explanation": explanation,
            }
        )
    rows.sort(
        key=lambda row: (
            0 if row["classification"] != "executable" else 1,
            str(row["classification"]),
            str(row["instrument_symbol"]),
            str(row["behavior_preset_id"]),
        )
    )
    top_mapping_gaps = [
        {
            "instrument_symbol": row["instrument_symbol"],
            "behavior_preset_id": row["behavior_preset_id"],
            "classification": row["classification"],
        }
        for row in rows
        if row["classification"] in {"mapping_missing", "provider_symbol_unresolved", "source_identity_blocked"}
    ][:10]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "total_combinations": len(rows),
            "executable_count": counts.get("executable", 0),
            "intentionally_non_executable_count": counts.get("intentionally_non_executable", 0),
            "mapping_missing_count": counts.get("mapping_missing", 0),
            "preset_not_executable_count": counts.get("preset_not_executable", 0),
            "region_constraint_mismatch_count": counts.get("region_constraint_mismatch", 0),
            "asset_class_constraint_mismatch_count": counts.get("asset_class_constraint_mismatch", 0),
            "unsupported_combination_count": counts.get("unsupported_combination", 0),
            "unknown_fail_closed_count": counts.get("unknown_fail_closed", 0),
            "affected_presets": sorted(affected_presets),
            "affected_assets": sorted(affected_assets),
            "top_mapping_gaps": top_mapping_gaps,
            "next_action_counts": dict(
                sorted(
                    Counter(
                        "keep_blocked" if row["classification"] != "executable" else "already_bounded"
                        for row in rows
                    ).items()
                )
            ),
            "operator_summary": (
                "Preset executability classification shows whether a discovery-grid row is already "
                "supported by the bounded execution adapter or safely blocked by seed-only, region, "
                "asset-class, timeframe, or source-identity constraints."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "registry_mutation": False,
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
            ["total combinations", str(summary.get("total_combinations") or 0)],
            ["executable", str(summary.get("executable_count") or 0)],
            [
                "intentionally non-executable",
                str(summary.get("intentionally_non_executable_count") or 0),
            ],
            ["mapping missing", str(summary.get("mapping_missing_count") or 0)],
            [
                "region constraint mismatch",
                str(summary.get("region_constraint_mismatch_count") or 0),
            ],
            [
                "asset class constraint mismatch",
                str(summary.get("asset_class_constraint_mismatch_count") or 0),
            ],
            [
                "unsupported combination",
                str(summary.get("unsupported_combination_count") or 0),
            ],
        ],
    )
    row_table = _table(
        ["Instrument", "Preset", "Classification", "Mapping status", "Blocker", "Explanation"],
        [
            [
                str(row.get("instrument_symbol") or ""),
                str(row.get("behavior_preset_id") or ""),
                str(row.get("classification") or ""),
                str(row.get("mapping_status") or ""),
                str(row.get("blocker_class") or "-"),
                str(row.get("explanation") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Controlled Discovery Preset Executability",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Aggregate counts",
            count_table,
            "",
            "## 3. Row classification",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_controlled_discovery_preset_executability: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_controlled_discovery_preset_executability",
        description="Classify discovery-grid preset executability without activating execution.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_preset_executability_report(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
