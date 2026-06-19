from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import candidate_lifecycle


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_candidate_identity_lifecycle"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_candidate_identity_lifecycle")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_candidate_identity_lifecycle/"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_scope_rows(breadth_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = breadth_report.get("coverage_matrix") if isinstance(breadth_report.get("coverage_matrix"), list) else []
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and _text(row.get("dimension")) == "basket"
    ]


def _build_scope(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hypothesis_id": _text(row.get("hypothesis_id")) or "unknown_hypothesis",
        "behavior_id": _text(row.get("behavior_id")) or "unknown_behavior",
        "preset_id": _text(row.get("scope_key")) or _text(row.get("preset_id")) or "unknown_preset",
        "timeframe": _text(row.get("timeframe")) or "unknown_timeframe",
        "universe_or_basket_scope": _text(row.get("scope_label")) or _text(row.get("scope_key")),
        "region": _text(row.get("region")),
        "symbol": _text(row.get("symbol")),
        "sampling_plan_ref": _text(row.get("sampling_plan_ref")),
    }


def build_qre_candidate_identity_lifecycle(
    *,
    breadth_report: Mapping[str, Any],
    disposition_memory: Mapping[str, Any] | None = None,
    closure_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scope_rows = _load_scope_rows(breadth_report)
    disposition_record = disposition_memory.get("record") if isinstance(disposition_memory, Mapping) and isinstance(disposition_memory.get("record"), Mapping) else {}
    rejected_scope_key = _text((disposition_record.get("disposition_scope") or {}).get("preset_id")) or _text(disposition_record.get("preset_id"))
    evidence_complete_count = int(((closure_report or {}).get("evidence_complete_count")) or 0)

    records: list[dict[str, Any]] = []
    for row in scope_rows:
        scope = _build_scope(row)
        suppressed = _text(row.get("scope_key")) == rejected_scope_key and int(row.get("accepted_oos_count") or 0) == 0
        context = candidate_lifecycle.QRETransitionContext(
            accepted_lineage_count=int(row.get("accepted_lineage_count") or 0),
            accepted_oos_count=int(row.get("accepted_oos_count") or 0),
            evidence_complete=evidence_complete_count > 0 and int(row.get("accepted_oos_count") or 0) > 0,
            rejected_scope=suppressed and evidence_complete_count == 0,
            suppressed_scope=suppressed,
        )
        record = candidate_lifecycle.build_qre_candidate_record(scope, context=context)
        record["source_scope_ref"] = f"coverage_matrix::{_text(row.get('scope_key'))}"
        records.append(record)

    candidate_lifecycle.assert_unique_qre_scope(records)
    records.sort(key=lambda row: (str(row["status"]), str(row["candidate_id"])))
    status_counts = Counter(str(row["status"]) for row in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "candidate_count": len(records),
            "status_counts": dict(sorted(status_counts.items())),
            "evidence_complete_count": sum(1 for row in records if row["status"] == "evidence_complete"),
            "suppressed_count": sum(1 for row in records if row["status"] == "suppressed"),
            "rejected_count": sum(1 for row in records if row["status"] == "rejected"),
            "final_recommendation": "qre_candidate_lifecycle_fail_closed",
            "operator_summary": (
                "Candidate identity and lifecycle remain fail-closed: rejected or duplicate scopes are blocked, "
                "and no candidate advances beyond evidence completeness without explicit prerequisite gates."
            ),
        },
        "rows": records,
        "authority": {
            "non_authoritative": True,
            "can_promote_candidate": False,
            "can_activate_shadow": False,
            "can_activate_paper": False,
            "can_activate_live": False,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "candidate_promotion_forbidden": True,
            "shadow_paper_live_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Candidate Identity Lifecycle",
        "",
        f"- candidate_count: {summary.get('candidate_count', 0)}",
        f"- evidence_complete_count: {summary.get('evidence_complete_count', 0)}",
        f"- suppressed_count: {summary.get('suppressed_count', 0)}",
        f"- rejected_count: {summary.get('rejected_count', 0)}",
        "",
        "## Candidates",
    ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- {row.get('candidate_id')} status={row.get('status')} blockers={','.join(row.get('blockers', [])) or 'none'}"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
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
        prog="python -m research.qre_candidate_identity_lifecycle",
        description="Build a fail-closed QRE candidate identity and lifecycle report.",
    )
    parser.add_argument("--breadth-report", required=True)
    parser.add_argument("--disposition-memory", default="")
    parser.add_argument("--closure-report", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    breadth_report = _read_json(Path(args.breadth_report)) or {}
    disposition_memory = _read_json(Path(args.disposition_memory)) if args.disposition_memory else {}
    closure_report = _read_json(Path(args.closure_report)) if args.closure_report else {}
    report = build_qre_candidate_identity_lifecycle(
        breadth_report=breadth_report,
        disposition_memory=disposition_memory,
        closure_report=closure_report,
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0

