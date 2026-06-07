from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_grid_candidate_campaign_lineage_bridge"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_grid_candidate_campaign_lineage_bridge")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_grid_candidate_campaign_lineage_bridge/"
MATERIALIZATION_PATH: Final[Path] = Path(
    "logs/qre_discovery_basket_grid_evidence_materialization/latest.json"
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _bridge_row(row: Mapping[str, Any]) -> dict[str, Any]:
    join_status = str(row.get("join_key_status") or "")
    matched_count = int(row.get("matched_grid_rows_count") or 0)
    lineage_status = str(row.get("candidate_lineage_status") or "missing")
    if join_status != "grid_row_match_found" or matched_count <= 0:
        bridge_status = "blocked_no_grid_match"
        exact_next_action = "restore_or_run_grid_artifacts"
        operator_explanation = "No local controlled-grid match is available, so lineage cannot be materialized."
    elif lineage_status == "visible":
        bridge_status = "lineage_visible"
        exact_next_action = "keep_fail_closed"
        operator_explanation = "Candidate and campaign lineage are both visible from the current materialized evidence."
    elif lineage_status == "candidate_visible_campaign_missing":
        bridge_status = "blocked_campaign_lineage_missing"
        exact_next_action = "materialize_campaign_lineage"
        operator_explanation = "Candidate lineage is visible but campaign lineage is still missing."
    elif lineage_status == "campaign_visible_candidate_missing":
        bridge_status = "blocked_candidate_lineage_missing"
        exact_next_action = "materialize_candidate_lineage"
        operator_explanation = "Campaign lineage is visible but candidate lineage is still missing."
    else:
        bridge_status = "blocked_candidate_and_campaign_lineage_missing"
        exact_next_action = "materialize_candidate_and_campaign_lineage"
        operator_explanation = "Neither candidate nor campaign lineage is visible from the current materialized evidence."
    return {
        "basket_id": row.get("basket_id"),
        "asset": row.get("asset"),
        "preset": row.get("preset"),
        "join_key_status": join_status or "unknown_fail_closed",
        "matched_grid_rows_count": matched_count,
        "candidate_lineage_status": lineage_status,
        "campaign_lineage_status": (
            "visible" if lineage_status in {"visible", "campaign_visible_candidate_missing"} else "missing"
        ),
        "lineage_bridge_status": bridge_status,
        "exact_next_action": exact_next_action,
        "operator_explanation": operator_explanation,
    }


def build_grid_candidate_campaign_lineage_bridge(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    payload = _read_json(repo_root / MATERIALIZATION_PATH)
    source_rows = payload.get("rows") if isinstance(payload, Mapping) else None
    rows = source_rows if isinstance(source_rows, list) else []
    bridge_rows = [_bridge_row(row) for row in rows[:max_candidates] if isinstance(row, Mapping)]
    bridge_rows.sort(key=lambda row: (str(row["lineage_bridge_status"]), str(row["asset"]), str(row["preset"])))
    status_counts = Counter(str(row["lineage_bridge_status"]) for row in bridge_rows)
    next_action_counts = Counter(str(row["exact_next_action"]) for row in bridge_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(bridge_rows),
            "lineage_bridge_status_counts": dict(sorted(status_counts.items())),
            "next_action_counts": dict(sorted(next_action_counts.items())),
            "operator_summary": (
                "Grid lineage bridge makes candidate/campaign lineage visibility explicit without changing readiness, "
                "routing, sampling, or promotion authority."
            ),
        },
        "rows": bridge_rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_candidate_lifecycle": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Grid Candidate / Campaign Lineage Bridge",
        "",
        f"- {(report.get('summary') or {}).get('operator_summary') or ''}",
        "",
        "## Basket Rows",
    ]
    for row in rows:
        lines.append(
            f"- {row['asset']} / {row['preset']}: {row['lineage_bridge_status']} -> {row['exact_next_action']}"
        )
    return "\n".join(lines) + "\n"


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_grid_candidate_campaign_lineage_bridge: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for path in (latest, summary_path):
        _validate_write_target(path)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_grid_candidate_campaign_lineage_bridge",
        description="Materialize candidate/campaign lineage visibility from grid evidence.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_grid_candidate_campaign_lineage_bridge(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
