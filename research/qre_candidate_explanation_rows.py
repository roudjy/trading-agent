from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_failure_action_from_basket as failure_action
from research import qre_real_basket_evidence_coverage as evidence_coverage
from research import qre_reason_records_v1 as reason_records


REPORT_KIND: Final[str] = "qre_candidate_explanation_rows"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_candidate_explanation_rows")
LATEST_NAME: Final[str] = "latest.json"
_WRITE_PREFIX: Final[str] = "logs/qre_candidate_explanation_rows/"
_PAPER_READINESS_PATH: Final[Path] = Path("research/paper_readiness_latest.v1.json")
_SYNTHESIS_GATE_PATH: Final[Path] = Path("research/synthesis_gate_latest.v1.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _reason_ref_index(records: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    by_subject: dict[str, dict[str, list[str]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        subject_id = str(record.get("subject_id") or "")
        if not subject_id:
            continue
        item = by_subject.setdefault(
            subject_id,
            {"record_ids": [], "record_families": [], "evidence_refs": []},
        )
        for key, values in (
            ("record_ids", [record.get("record_id")]),
            ("record_families", [record.get("record_family")]),
            ("evidence_refs", record.get("evidence_refs") or []),
        ):
            for value in values:
                text = str(value or "").strip()
                if text and text not in item[key]:
                    item[key].append(text[:160])
    return by_subject


def _paper_indices(
    payload: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(payload, Mapping):
        return {}, {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {}, {}
    by_candidate: dict[str, dict[str, Any]] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in entries:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            by_candidate[candidate_id] = row
        symbol = str(row.get("asset") or row.get("asset_symbol") or "")
        if symbol:
            by_symbol[symbol] = row
    return by_candidate, by_symbol


def _synthesis_state(payload: dict[str, Any] | None) -> tuple[str, bool]:
    if not isinstance(payload, Mapping):
        return ("not_available_fail_closed", False)
    return (str(payload.get("synthesis_gate_state") or "not_available_fail_closed"), False)


def _oos_status(row: Mapping[str, Any]) -> str:
    counts = row.get("validation_evidence_status_counts")
    if not isinstance(counts, Mapping):
        return "oos_evidence_missing"
    if int(counts.get("sufficient_oos_evidence") or 0) > 0:
        return "sufficient_oos_evidence"
    if int(counts.get("insufficient_oos_trades") or 0) > 0:
        return "insufficient_oos_evidence"
    if int(counts.get("no_oos_trades") or 0) > 0:
        return "no_oos_evidence"
    if counts:
        return "oos_evidence_unknown"
    return "oos_evidence_missing"


def build_candidate_explanation_rows(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    coverage = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    paper_by_candidate, paper_by_symbol = _paper_indices(
        _read_json(repo_root / _PAPER_READINESS_PATH)
    )
    synthesis_state, synthesis_allowed = _synthesis_state(
        _read_json(repo_root / _SYNTHESIS_GATE_PATH)
    )

    coverage_rows = coverage.get("rows")
    if not isinstance(coverage_rows, list):
        coverage_rows = []
    failure_rows = failure.get("rows")
    if not isinstance(failure_rows, list):
        failure_rows = []
    failure_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in failure_rows
        if isinstance(row, Mapping)
    }
    reason_index = _reason_ref_index(
        [row for row in reason_snapshot.get("records") or [] if isinstance(row, dict)]
    )

    rows: list[dict[str, Any]] = []
    for row in coverage_rows:
        if not isinstance(row, Mapping):
            continue
        candidate_id = str(row.get("candidate_id") or "")
        failure_row = failure_by_subject.get(candidate_id, {})
        paper_row = paper_by_candidate.get(candidate_id) or paper_by_symbol.get(
            str(row.get("symbol") or ""),
            {},
        )
        paper_status = str(paper_row.get("readiness_status") or "not_available_fail_closed")
        bridge_status = str(
            ((row.get("grid_readiness_bridge") or {}).get("readiness_bridge_status"))
            or "blocked_no_grid_match"
        )
        primary_blocker = (
            bridge_status
            if bridge_status.startswith("blocked_")
            else str(
                failure_row.get("blocker_code")
                or ((row.get("grid_readiness_bridge") or {}).get("readiness_blocker_category"))
                or row.get("diagnosis_reason_code")
                or "unknown"
            )
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                "symbol": row.get("symbol"),
                "preset_id": row.get("preset_id"),
                "hypothesis_id": row.get("hypothesis_id"),
                "behavior_family": row.get("behavior_family"),
                "campaign_lineage_status": (
                    "present"
                    if int((row.get("evidence_counts") or {}).get("campaign_lineage_rows") or 0) > 0
                    else "missing"
                ),
                "screening_status": (
                    "present"
                    if int((row.get("evidence_counts") or {}).get("screening_rows") or 0) > 0
                    else "missing"
                ),
                "oos_status": _oos_status(row),
                "grid_readiness_bridge_status": str(
                    ((row.get("grid_readiness_bridge") or {}).get("readiness_bridge_status"))
                    or "blocked_no_grid_match"
                ),
                "grid_readiness_bridge_explanation": str(
                    ((row.get("grid_readiness_bridge") or {}).get("bridge_explanation")) or ""
                ),
                "paper_readiness_status": paper_status,
                "paper_readiness_blockers": list(paper_row.get("blocking_reasons") or []),
                "synthesis_gate_state": synthesis_state,
                "synthesis_allowed": synthesis_allowed,
                "reason_record_refs": reason_index.get(
                    candidate_id,
                    {"record_ids": [], "record_families": [], "evidence_refs": []},
                ),
                "safe_next_action": str(
                    failure_row.get("recommended_action") or "keep_blocked"
                ),
                "primary_blocker": primary_blocker,
                "operator_explanation": (
                    f"{row.get('symbol')} remains {paper_status} for paper and "
                    f"{synthesis_state} for synthesis; next action is "
                    f"{failure_row.get('recommended_action') or 'keep_blocked'}."
                ),
            }
        )

    rows.sort(key=lambda item: (str(item["symbol"]), str(item["preset_id"])))
    counts = Counter(str(row["safe_next_action"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "candidate_count": len(rows),
            "safe_next_action_counts": dict(sorted(counts.items())),
            "paper_blocked_count": sum(
                1 for row in rows if str(row.get("paper_readiness_status") or "") == "blocked"
            ),
            "synthesis_blocked_count": sum(
                1
                for row in rows
                if str(row.get("synthesis_gate_state") or "").startswith("blocked")
            ),
            "final_recommendation": (
                "candidate_explanations_ready" if rows else "candidate_explanations_missing"
            ),
            "operator_summary": (
                "Candidate explanation rows combine basket evidence, failure actions, "
                "paper blockers, synthesis blockers, and durable reason refs without "
                "changing candidate lifecycle state."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_candidate_lifecycle": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_candidate_explanation_rows: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    _validate_write_target(latest)
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, latest)
    return {"latest": latest.relative_to(repo_root).as_posix()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_candidate_explanation_rows",
        description="Build read-only QRE candidate explanation rows.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_candidate_explanation_rows(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
