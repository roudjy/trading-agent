from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_grid_candidate_campaign_lineage_bridge as lineage_bridge
from research import qre_real_basket_diagnosis as diagnosis


REPORT_KIND: Final[str] = "qre_basket_evidence_density_materialization"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_basket_evidence_density_materialization")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_basket_evidence_density_materialization/"
SCREENING_EVIDENCE_PATH: Final[Path] = Path("research/screening_evidence_latest.v1.json")

_LINKED_SCREENING_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "linked_exact_ids",
        "linked_executable_hypothesis_bridge",
        "linked_catalog_active_discovery",
    }
)
_KNOWN_OOS_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "sufficient_oos_evidence",
        "insufficient_oos_evidence",
        "no_oos_evidence",
        "no_oos_trades",
    }
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


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _bounded_ref(value: str, *, max_len: int = 180) -> str:
    text = value.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _screening_rows_by_symbol(payload: Mapping[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, Mapping):
        return {}
    rows = payload.get("candidates")
    if not isinstance(rows, list):
        return {}
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("asset") or "").strip()
        linkage_status = str(row.get("qre_validation_linkage_status") or "")
        if not symbol or linkage_status not in _LINKED_SCREENING_STATUSES:
            continue
        by_symbol.setdefault(symbol, []).append(row)
    return by_symbol


def _screening_ref(row: Mapping[str, Any]) -> str:
    candidate_id = str(row.get("candidate_id") or "").strip()
    asset = str(row.get("asset") or "").strip()
    row_id = candidate_id or asset or "unknown"
    return f"{SCREENING_EVIDENCE_PATH.as_posix()}#{_bounded_ref(row_id)}"


def _oos_status(screening_rows: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    statuses: list[str] = []
    refs: list[str] = []
    for row in screening_rows:
        validation_evidence = row.get("validation_evidence")
        status = None
        if isinstance(validation_evidence, Mapping):
            status = validation_evidence.get("status")
        normalized = str(status or "unknown").strip().lower()
        if normalized not in statuses:
            statuses.append(normalized)
        refs.append(_screening_ref(row))
    if not statuses:
        return ("oos_evidence_missing", refs)
    if any(status in _KNOWN_OOS_STATUSES for status in statuses):
        if any(status == "sufficient_oos_evidence" for status in statuses):
            return ("sufficient_oos_evidence", refs)
        if any(status == "insufficient_oos_evidence" for status in statuses):
            return ("insufficient_oos_evidence", refs)
        if any(status in {"no_oos_evidence", "no_oos_trades"} for status in statuses):
            return ("no_oos_evidence", refs)
    if all(status in {"unknown", "none", ""} for status in statuses):
        return ("oos_evidence_unknown", refs)
    return ("oos_evidence_unknown", refs)


def _density_row(
    *,
    diagnosis_row: Mapping[str, Any],
    bridge_row: Mapping[str, Any],
    screening_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    evidence = diagnosis_row.get("current_evidence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    source_quality_rows = int(evidence.get("source_quality_rows") or 0)
    cache_coverage_rows = int(evidence.get("cache_coverage_rows") or 0)
    candidate_rows = int(evidence.get("candidate_rows") or 0)
    campaign_rows = int(evidence.get("campaign_rows") or 0)
    source_quality_refs = (
        ["logs/qre_data_source_quality_readiness/latest.json"]
        if source_quality_rows > 0
        else []
    )
    cache_coverage_refs = (
        ["logs/qre_data_cache_manifest/latest.json"] if cache_coverage_rows > 0 else []
    )
    screening_refs = [_screening_ref(row) for row in screening_rows]
    oos_status, oos_refs = _oos_status(screening_rows)
    candidate_lineage_status = str(bridge_row.get("candidate_lineage_status") or "missing")
    campaign_lineage_status = (
        "visible" if candidate_lineage_status == "visible" and campaign_rows > 0 else "missing"
    )
    candidate_lineage_refs = (
        [
            f"logs/qre_discovery_basket_grid_evidence_materialization/latest.json#"
            f"{_bounded_ref(str(diagnosis_row.get('symbol') or ''))}|"
            f"{_bounded_ref(str(diagnosis_row.get('preset_id') or ''))}"
        ]
        if candidate_rows > 0 or candidate_lineage_status != "missing"
        else []
    )
    campaign_lineage_refs = (
        [
            f"logs/qre_grid_candidate_campaign_lineage_bridge/latest.json#"
            f"{_bounded_ref(str(diagnosis_row.get('symbol') or ''))}|"
            f"{_bounded_ref(str(diagnosis_row.get('preset_id') or ''))}"
        ]
        if campaign_rows > 0
        else []
    )
    exact_blockers = list(diagnosis_row.get("missing_evidence_taxonomy") or [])
    return {
        "candidate_id": diagnosis_row.get("candidate_id"),
        "symbol": diagnosis_row.get("symbol"),
        "preset_id": diagnosis_row.get("preset_id"),
        "hypothesis_id": diagnosis_row.get("hypothesis_id"),
        "behavior_family": diagnosis_row.get("behavior_family"),
        "region": diagnosis_row.get("region"),
        "asset_class": diagnosis_row.get("asset_class"),
        "timeframes": list(diagnosis_row.get("timeframes") or []),
        "source_identity_status": diagnosis_row.get("source_identity_status"),
        "source_identity_blocker": diagnosis_row.get("reason_code")
        if str(diagnosis_row.get("reason_code") or "").startswith("source_identity")
        else "",
        "source_quality_rows": source_quality_rows,
        "cache_coverage_rows": cache_coverage_rows,
        "screening_evidence_rows": len(screening_rows),
        "validation_evidence_statuses": [
            str(
                row.get("validation_evidence").get("status")  # type: ignore[union-attr]
            )
            if isinstance(row.get("validation_evidence"), Mapping)
            else "unknown"
            for row in screening_rows
        ],
        "oos_evidence_status": oos_status,
        "campaign_lineage_rows": campaign_rows,
        "candidate_lineage_rows": candidate_rows,
        "campaign_lineage_status": campaign_lineage_status,
        "candidate_lineage_status": candidate_lineage_status,
        "source_quality_refs": source_quality_refs,
        "cache_coverage_refs": cache_coverage_refs,
        "screening_evidence_refs": screening_refs,
        "oos_evidence_refs": oos_refs,
        "candidate_lineage_refs": candidate_lineage_refs,
        "campaign_lineage_refs": campaign_lineage_refs,
        "expected_screening_evidence_ref": f"research/screening_evidence_latest.v1.json#{diagnosis_row.get('symbol')}",
        "expected_oos_evidence_ref": f"research/screening_evidence_latest.v1.json#{diagnosis_row.get('symbol')}",
        "expected_candidate_lineage_ref": f"logs/qre_discovery_basket_grid_evidence_materialization/latest.json#{diagnosis_row.get('symbol')}",
        "expected_campaign_artifact_ref": f"logs/qre_grid_candidate_campaign_lineage_bridge/latest.json#{diagnosis_row.get('symbol')}",
        "exact_blockers": exact_blockers,
        "exact_next_action": bridge_row.get("exact_next_action")
        or diagnosis_row.get("follow_up")
        or "keep_fail_closed",
    }


def build_basket_evidence_density_materialization(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    diagnosis_report = diagnosis.build_real_basket_diagnosis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    screening_payload = _read_json(repo_root / SCREENING_EVIDENCE_PATH)
    screening_by_symbol = _screening_rows_by_symbol(screening_payload)
    bridge_report = lineage_bridge.build_grid_candidate_campaign_lineage_bridge(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    diagnosis_rows = diagnosis_report.get("rows")
    if not isinstance(diagnosis_rows, list):
        diagnosis_rows = []
    bridge_rows = bridge_report.get("rows")
    if not isinstance(bridge_rows, list):
        bridge_rows = []
    bridge_by_key = {
        (str(row.get("asset") or ""), str(row.get("preset") or "")): row
        for row in bridge_rows
        if isinstance(row, Mapping)
    }

    rows: list[dict[str, Any]] = []
    for row in diagnosis_rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "")
        preset_id = str(row.get("preset_id") or "")
        bridge_row = bridge_by_key.get((symbol, preset_id), {})
        rows.append(
            _density_row(
                diagnosis_row=row,
                bridge_row=bridge_row,
                screening_rows=screening_by_symbol.get(symbol, []),
            )
        )

    rows.sort(key=lambda row: (str(row["symbol"]), str(row["preset_id"])))
    screening_present = sum(1 for row in rows if int(row["screening_evidence_rows"]) > 0)
    oos_known = sum(
        1
        for row in rows
        if str(row["oos_evidence_status"]) in _KNOWN_OOS_STATUSES
    )
    candidate_lineage_visible = sum(
        1
        for row in rows
        if int(row["candidate_lineage_rows"]) > 0
        or str(row["candidate_lineage_status"]) != "missing"
    )
    campaign_lineage_visible = sum(
        1 for row in rows if int(row["campaign_lineage_rows"]) > 0
    )
    identity_blocked = sum(
        1
        for row in rows
        if str(row.get("source_identity_status") or "") == "candidate_alias_only"
        or str(row.get("source_identity_blocker") or "").startswith("source_identity")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(rows),
            "screening_evidence_present_count": screening_present,
            "oos_evidence_known_count": oos_known,
            "candidate_lineage_visible_count": candidate_lineage_visible,
            "campaign_lineage_visible_count": campaign_lineage_visible,
            "source_identity_blocked_count": identity_blocked,
            "final_recommendation": (
                "basket_evidence_density_materialized_read_only"
                if rows
                else "basket_evidence_density_missing"
            ),
            "operator_summary": (
                "Read-only basket evidence density links the current bounded basket to local "
                "screening, OOS, source/cache, and lineage artifacts while preserving explicit "
                "gaps and identity blockers."
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
            ["basket inventory", str(summary.get("basket_count") or 0)],
            ["screening present", str(summary.get("screening_evidence_present_count") or 0)],
            ["OOS known", str(summary.get("oos_evidence_known_count") or 0)],
            ["candidate lineage visible", str(summary.get("candidate_lineage_visible_count") or 0)],
            ["campaign lineage visible", str(summary.get("campaign_lineage_visible_count") or 0)],
            ["identity blocked", str(summary.get("source_identity_blocked_count") or 0)],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "Screening",
            "OOS",
            "Candidate lineage",
            "Campaign lineage",
            "Identity",
            "Next action",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                str(row.get("screening_evidence_rows") or 0),
                str(row.get("oos_evidence_status") or ""),
                str(row.get("candidate_lineage_status") or ""),
                str(row.get("campaign_lineage_status") or ""),
                str(row.get("source_identity_status") or ""),
                str(row.get("exact_next_action") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Basket Evidence Density Materialization",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Evidence density counts",
            count_table,
            "",
            "## 3. Basket evidence density",
            basket_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            "qre_basket_evidence_density_materialization: refusing write outside allowlist: "
            f"{path!r}"
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
        prog="python -m research.qre_basket_evidence_density_materialization",
        description="Build read-only basket evidence density materialization.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_basket_evidence_density_materialization(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
