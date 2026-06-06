from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_candidate_explanation_rows as candidate_rows
from research import qre_real_basket_evidence_coverage as evidence_coverage


REPORT_KIND: Final[str] = "qre_oos_evidence_blockers"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_oos_evidence_blockers")
LATEST_NAME: Final[str] = "latest.json"
_WRITE_PREFIX: Final[str] = "logs/qre_oos_evidence_blockers/"


def _classify_oos_blocker(row: Mapping[str, Any]) -> str:
    status = str(row.get("oos_status") or "oos_evidence_missing")
    next_action = str(row.get("safe_next_action") or "keep_blocked")
    if status == "sufficient_oos_evidence":
        if next_action == "eligible_for_readonly_routing":
            return "oos_evidence_present_readonly_only"
        return "oos_evidence_present_but_other_blockers"
    if status == "insufficient_oos_evidence":
        return "oos_evidence_insufficient"
    if status == "no_oos_evidence":
        return "oos_evidence_absent"
    if status == "oos_evidence_unknown":
        return "oos_evidence_unknown"
    return "oos_evidence_missing"


def build_oos_evidence_blockers(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    coverage = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    explanations = candidate_rows.build_candidate_explanation_rows(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    coverage_rows = coverage.get("rows")
    if not isinstance(coverage_rows, list):
        coverage_rows = []
    explanation_rows = explanations.get("rows")
    if not isinstance(explanation_rows, list):
        explanation_rows = []
    explanation_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in explanation_rows
        if isinstance(row, Mapping)
    }

    rows: list[dict[str, Any]] = []
    for row in coverage_rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("candidate_id") or "")
        explanation = explanation_by_subject.get(subject_id, {})
        oos_status = str(explanation.get("oos_status") or "oos_evidence_missing")
        rows.append(
            {
                "candidate_id": subject_id,
                "symbol": row.get("symbol"),
                "preset_id": row.get("preset_id"),
                "oos_status": oos_status,
                "oos_trade_count_max": int(
                    (row.get("evidence_counts") or {}).get("oos_trade_count_max") or 0
                ),
                "oos_blocker_class": _classify_oos_blocker(explanation),
                "safe_next_action": explanation.get("safe_next_action"),
                "reason_record_refs": explanation.get("reason_record_refs"),
            }
        )

    rows.sort(key=lambda item: (str(item["symbol"]), str(item["preset_id"])))
    counts = Counter(str(row["oos_blocker_class"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "row_count": len(rows),
            "oos_blocker_counts": dict(sorted(counts.items())),
            "final_recommendation": (
                "oos_evidence_blockers_ready" if rows else "oos_evidence_blockers_missing"
            ),
            "operator_summary": (
                "OOS blocker rows classify current read-only OOS evidence states without "
                "promoting candidates or mutating lifecycle state."
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
            f"qre_oos_evidence_blockers: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_oos_evidence_blockers",
        description="Build read-only QRE OOS blocker explanation rows.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_oos_evidence_blockers(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
