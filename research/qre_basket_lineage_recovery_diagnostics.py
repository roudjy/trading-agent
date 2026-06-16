from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_basket_evidence_density_materialization as density
from research import qre_grid_candidate_campaign_lineage_bridge as lineage_bridge


REPORT_KIND: Final[str] = "qre_basket_lineage_recovery_diagnostics"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_basket_lineage_recovery_diagnostics")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_basket_lineage_recovery_diagnostics/"
GRID_MATERIALIZATION_PATH: Final[Path] = Path(
    "logs/qre_discovery_basket_grid_evidence_materialization/latest.json"
)
LINEAGE_BRIDGE_PATH: Final[Path] = Path("logs/qre_grid_candidate_campaign_lineage_bridge/latest.json")
_PROOF_FIELDS: Final[tuple[str, ...]] = (
    "candidate_id",
    "symbol",
    "preset_id",
    "hypothesis_id",
    "behavior_family",
    "region",
    "asset_class",
    "timeframes",
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


def _index_by_candidate(rows: Sequence[Mapping[str, Any]], *, key: str = "candidate_id") -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        subject_id = str(row.get(key) or "")
        if subject_id and subject_id not in indexed:
            indexed[subject_id] = dict(row)
    return indexed


def _row_state(
    *,
    density_row: Mapping[str, Any],
    bridge_row: Mapping[str, Any],
    density_state: str,
    grid_state: str,
    bridge_state: str,
) -> dict[str, Any]:
    candidate_refs = list(density_row.get("candidate_lineage_refs") or [])
    campaign_refs = list(density_row.get("campaign_lineage_refs") or [])
    candidate_rows = int(density_row.get("candidate_lineage_rows") or 0)
    campaign_rows = int(density_row.get("campaign_lineage_rows") or 0)
    candidate_proven = candidate_rows > 0 or bool(candidate_refs)
    campaign_proven = campaign_rows > 0 or bool(campaign_refs)
    candidate_lineage_status = str(density_row.get("candidate_lineage_status") or "missing")
    campaign_lineage_status = str(density_row.get("campaign_lineage_status") or "missing")
    bridge_lineage_status = str(bridge_row.get("lineage_bridge_status") or "blocked_no_grid_match")
    if candidate_proven and campaign_proven:
        proof_status = "lineage_visible"
        next_action = "keep_fail_closed"
        reason = "candidate_and_campaign_lineage_proven_from_local_artifacts"
    elif candidate_proven:
        proof_status = "candidate_proven_campaign_missing"
        next_action = "materialize_campaign_lineage"
        reason = "candidate_lineage_proven_campaign_lineage_missing"
    elif campaign_proven:
        proof_status = "campaign_proven_candidate_missing"
        next_action = "materialize_candidate_lineage"
        reason = "campaign_lineage_proven_candidate_lineage_missing"
    elif density_state == "missing" or grid_state == "missing" or bridge_state == "missing":
        proof_status = "artifact_missing"
        next_action = "restore_or_run_grid_artifacts"
        reason = "required_lineage_artifacts_are_missing"
    elif bridge_lineage_status == "blocked_no_grid_match":
        proof_status = "lineage_gap"
        next_action = str(bridge_row.get("exact_next_action") or "restore_or_run_grid_artifacts")
        reason = "no_local_grid_match_is_available"
    else:
        proof_status = "lineage_gap"
        next_action = str(bridge_row.get("exact_next_action") or "materialize_candidate_lineage")
        reason = "lineage_is_not_proven_by_current_local_artifacts"
    return {
        "candidate_id": density_row.get("candidate_id"),
        "symbol": density_row.get("symbol"),
        "preset_id": density_row.get("preset_id"),
        "hypothesis_id": density_row.get("hypothesis_id"),
        "behavior_family": density_row.get("behavior_family"),
        "region": density_row.get("region"),
        "asset_class": density_row.get("asset_class"),
        "timeframes": list(density_row.get("timeframes") or []),
        "density_artifact_state": density_state,
        "grid_materialization_state": grid_state,
        "bridge_artifact_state": bridge_state,
        "candidate_lineage_rows": candidate_rows,
        "campaign_lineage_rows": campaign_rows,
        "candidate_lineage_refs": candidate_refs,
        "campaign_lineage_refs": campaign_refs,
        "candidate_lineage_status": candidate_lineage_status,
        "campaign_lineage_status": campaign_lineage_status,
        "candidate_lineage_proof_status": proof_status,
        "campaign_lineage_proof_status": "proven" if campaign_proven else "gap",
        "lineage_recovery_reason": reason,
        "exact_next_action": next_action,
        "proof_fields": {field: density_row.get(field) for field in _PROOF_FIELDS},
        "proof_source_refs": {
            "density": [f"logs/qre_basket_evidence_density_materialization/latest.json#{density_row.get('candidate_id') or density_row.get('symbol') or ''}"],
            "grid_materialization": [
                f"logs/qre_discovery_basket_grid_evidence_materialization/latest.json#{density_row.get('symbol') or ''}|{density_row.get('preset_id') or ''}"
            ],
            "lineage_bridge": [
                f"logs/qre_grid_candidate_campaign_lineage_bridge/latest.json#{density_row.get('symbol') or ''}|{density_row.get('preset_id') or ''}"
            ],
        },
    }


def build_basket_lineage_recovery_diagnostics(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    density_report = _read_json(repo_root / Path("logs/qre_basket_evidence_density_materialization/latest.json"))
    if density_report is None:
        density_report = density.build_basket_evidence_density_materialization(
            repo_root=repo_root,
            max_candidates=max_candidates,
        )
    bridge_report = _read_json(repo_root / LINEAGE_BRIDGE_PATH)
    if bridge_report is None:
        bridge_report = lineage_bridge.build_grid_candidate_campaign_lineage_bridge(
            repo_root=repo_root,
            max_candidates=max_candidates,
        )
    grid_report = _read_json(repo_root / GRID_MATERIALIZATION_PATH)

    density_rows = density_report.get("rows") if isinstance(density_report.get("rows"), list) else []
    bridge_rows = bridge_report.get("rows") if isinstance(bridge_report.get("rows"), list) else []
    grid_rows = grid_report.get("rows") if isinstance(grid_report, Mapping) and isinstance(grid_report.get("rows"), list) else []

    density_by_candidate = _index_by_candidate(density_rows)
    bridge_by_key = {
        (str(row.get("asset") or ""), str(row.get("preset") or "")): dict(row)
        for row in bridge_rows
        if isinstance(row, Mapping)
    }
    grid_by_key = {
        (str(row.get("asset") or ""), str(row.get("preset") or "")): dict(row)
        for row in grid_rows
        if isinstance(row, Mapping)
    }
    candidate_ids = sorted(density_by_candidate.keys())
    density_state = "present" if density_report else "missing"
    grid_state = "present" if grid_report else "missing"
    bridge_state = "present" if bridge_report else "missing"

    rows: list[dict[str, Any]] = []
    proof_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()

    for candidate_id in candidate_ids:
        density_row = density_by_candidate.get(candidate_id, {})
        symbol = str(density_row.get("symbol") or "")
        preset_id = str(density_row.get("preset_id") or "")
        bridge_row = bridge_by_key.get((symbol, preset_id), {})
        grid_row = grid_by_key.get((symbol, preset_id), {})
        row = _row_state(
            density_row=density_row,
            bridge_row={**bridge_row, **grid_row},
            density_state=density_state,
            grid_state=grid_state,
            bridge_state=bridge_state,
        )
        rows.append(row)
        proof_counts.update([str(row["candidate_lineage_proof_status"])])
        if str(row["candidate_lineage_proof_status"]) != "lineage_visible":
            gap_counts.update([str(row["lineage_recovery_reason"])])

    rows.sort(key=lambda row: (str(row["symbol"]), str(row["preset_id"])))
    candidate_proven_count = sum(1 for row in rows if str(row["candidate_lineage_proof_status"]) in {"lineage_visible", "candidate_proven_campaign_missing"})
    campaign_proven_count = sum(1 for row in rows if str(row["campaign_lineage_proof_status"]) == "proven")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(rows),
            "density_artifact_state": density_state,
            "grid_materialization_state": grid_state,
            "bridge_artifact_state": bridge_state,
            "candidate_lineage_proven_count": candidate_proven_count,
            "campaign_lineage_proven_count": campaign_proven_count,
            "candidate_lineage_gap_count": sum(
                1 for row in rows if str(row["candidate_lineage_proof_status"]) != "lineage_visible"
            ),
            "campaign_lineage_gap_count": sum(
                1 for row in rows if str(row["campaign_lineage_proof_status"]) != "proven"
            ),
            "candidate_lineage_proof_counts": dict(sorted(proof_counts.items())),
            "lineage_gap_reason_counts": dict(sorted(gap_counts.items())),
            "final_recommendation": (
                "basket_lineage_recovery_diagnostics_ready" if rows else "basket_lineage_recovery_diagnostics_missing"
            ),
            "operator_summary": (
                "Read-only lineage diagnostics distinguish proven candidate lineage from campaign lineage gaps "
                "and keep explicit recovery reasons visible for operator review."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
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
            ["candidate lineage proven", str(summary.get("candidate_lineage_proven_count") or 0)],
            ["campaign lineage proven", str(summary.get("campaign_lineage_proven_count") or 0)],
            ["candidate lineage gap", str(summary.get("candidate_lineage_gap_count") or 0)],
            ["campaign lineage gap", str(summary.get("campaign_lineage_gap_count") or 0)],
        ],
    )
    row_table = _table(
        ["Symbol", "Candidate lineage", "Campaign lineage", "Reason", "Next action"],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("candidate_lineage_proof_status") or ""),
                str(row.get("campaign_lineage_proof_status") or ""),
                str(row.get("lineage_recovery_reason") or ""),
                str(row.get("exact_next_action") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Basket Lineage Recovery Diagnostics",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Lineage counts",
            count_table,
            "",
            "## 3. Lineage rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_basket_lineage_recovery_diagnostics: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_basket_lineage_recovery_diagnostics",
        description="Build read-only basket lineage recovery diagnostics.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_basket_lineage_recovery_diagnostics(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
