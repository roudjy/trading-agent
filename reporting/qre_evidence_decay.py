from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Final

REPORT_KIND: Final[str] = "qre_evidence_decay"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017t-2026-06-27"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_evidence_decay")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_evidence_decay.md")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage/latest.json")
DEFAULT_CONTRADICTION_PATH: Final[Path] = Path(
    "logs/qre_contradiction_staleness_intelligence/latest.json"
)
DEFAULT_VALIDATION_RESULTS_PATH: Final[Path] = Path(
    "logs/qre_hypothesis_validation_results/latest.json"
)
DEFAULT_OOS_BLOCKERS_PATH: Final[Path] = Path("logs/qre_oos_evidence_blockers/latest.json")
DEFAULT_MULTIWINDOW_CLOSURE_PATH: Final[Path] = Path(
    "logs/qre_multiwindow_evidence_closure/latest.json"
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_evidence_decay/",
    "docs/governance/qre_evidence_decay.md",
)


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


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return out


def _index_validation_results(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        hypothesis_id = _text(row.get("hypothesis_id"))
        if not hypothesis_id:
            continue
        indexed.setdefault(hypothesis_id, []).append(dict(row))
    return indexed


def _index_oos_blockers(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for key in (_text(row.get("candidate_id")), _text(row.get("hypothesis_id"))):
            if not key:
                continue
            indexed.setdefault(key, []).append(dict(row))
    return indexed


def _artifact_paths_from_stale_rows(rows: list[dict[str, Any]]) -> set[str]:
    return {_text(row.get("artifact_path")) for row in rows if _text(row.get("artifact_path"))}


def _match_stale_refs(provenance_refs: list[str], stale_paths: set[str]) -> list[str]:
    matches: list[str] = []
    for ref in provenance_refs:
        text = _text(ref)
        if not text:
            continue
        if any(path and path in text for path in stale_paths):
            matches.append(text)
    return _dedupe(matches)


def _dimension_statuses(
    *,
    row: dict[str, Any],
    validation_rows: list[dict[str, Any]],
    matched_oos_rows: list[dict[str, Any]],
    stale_refs: list[str],
    closure_status: str,
) -> tuple[dict[str, str], list[str]]:
    graph_nodes = row.get("graph_nodes") if isinstance(row.get("graph_nodes"), dict) else {}
    unresolved_refs = [_text(value) for value in row.get("unresolved_evidence_refs", []) if _text(value)]
    contradiction_rows = row.get("contradiction_rows") if isinstance(row.get("contradiction_rows"), list) else []
    contradicting_refs = [
        _text(value) for value in row.get("contradicting_evidence_refs", []) if _text(value)
    ]
    blocking_reasons: list[str] = []

    if graph_nodes.get("source"):
        source_freshness = (
            "stale_or_superseded_visible"
            if stale_refs
            else "freshness_unverifiable_no_source_timestamp"
        )
    else:
        source_freshness = "missing_source_identity"
        blocking_reasons.append("missing_source_identity")

    if graph_nodes.get("data_snapshot"):
        data_age = "age_unverifiable_no_snapshot_timestamp"
    else:
        data_age = "missing_data_snapshot_identity"
        blocking_reasons.append("missing_data_snapshot_identity")

    if graph_nodes.get("campaign"):
        campaign_age = "age_unverifiable_no_campaign_timestamp"
    else:
        campaign_age = "missing_campaign_identity"
        blocking_reasons.append("missing_campaign_identity")

    if validation_rows:
        reproducibility = "validation_result_present"
    elif graph_nodes.get("campaign"):
        reproducibility = "campaign_visible_but_validation_missing"
        blocking_reasons.append("validation_result_missing")
    else:
        reproducibility = "reproducibility_unverifiable_without_campaign"
        blocking_reasons.append("reproducibility_unverifiable")

    if contradiction_rows or contradicting_refs:
        contradiction_state = "contradicting_evidence_visible"
        blocking_reasons.append("contradicting_evidence_visible")
    elif unresolved_refs:
        contradiction_state = "unresolved_evidence_visible"
        blocking_reasons.append("unresolved_evidence_visible")
    else:
        contradiction_state = "no_visible_contradiction_or_unresolved_evidence"

    if graph_nodes.get("source"):
        source_authority_loss = (
            "authority_loss_or_staleness_visible"
            if stale_refs
            else "authority_unverifiable_without_source_recency"
        )
    else:
        source_authority_loss = "authority_unverifiable_missing_source_identity"
        blocking_reasons.append("authority_unverifiable_missing_source_identity")

    if stale_refs:
        superseded_evidence = "stale_or_superseded_artifacts_visible"
        blocking_reasons.append("stale_or_superseded_artifacts_visible")
    else:
        superseded_evidence = "no_visible_superseded_artifact_binding"

    if any("state:regime_context:blocked" in ref for ref in unresolved_refs):
        regime_relevance = "regime_context_unresolved"
        blocking_reasons.append("regime_context_unresolved")
    elif any("regime" in ref.lower() for ref in stale_refs):
        regime_relevance = "regime_context_stale_or_superseded"
        blocking_reasons.append("regime_context_stale_or_superseded")
    else:
        regime_relevance = "regime_context_not_visible"

    if bool(row.get("lineage_complete")):
        incomplete_lineage = "lineage_complete"
    else:
        incomplete_lineage = "lineage_incomplete"
        blocking_reasons.append("lineage_incomplete")

    if matched_oos_rows:
        oos_statuses = {_text(item.get("oos_status")) for item in matched_oos_rows if _text(item.get("oos_status"))}
        missing_oos_renewal = ",".join(sorted(oos_statuses)) or "oos_status_present"
        if any(status != "sufficient_oos_evidence" for status in oos_statuses):
            blocking_reasons.append("oos_evidence_not_sufficient")
    elif any("state:oos_plan:blocked" in ref for ref in unresolved_refs):
        missing_oos_renewal = "missing_oos_plan_or_renewal"
        blocking_reasons.append("missing_oos_plan_or_renewal")
    elif closure_status:
        missing_oos_renewal = f"campaign_closure:{closure_status}"
        if closure_status != "evidence_complete":
            blocking_reasons.append(f"campaign_closure:{closure_status}")
    else:
        missing_oos_renewal = "no_visible_oos_renewal_evidence"
        blocking_reasons.append("no_visible_oos_renewal_evidence")

    return (
        {
            "source_freshness": source_freshness,
            "data_age": data_age,
            "campaign_age": campaign_age,
            "reproducibility": reproducibility,
            "contradiction_state": contradiction_state,
            "source_authority_loss": source_authority_loss,
            "superseded_evidence": superseded_evidence,
            "regime_relevance": regime_relevance,
            "incomplete_lineage": incomplete_lineage,
            "missing_oos_renewal": missing_oos_renewal,
        },
        _dedupe(blocking_reasons),
    )


def build_evidence_decay(
    *,
    repo_root: Path | None = None,
    lineage_report: dict[str, Any] | None = None,
    contradiction_report: dict[str, Any] | None = None,
    validation_results_report: dict[str, Any] | None = None,
    oos_blockers_report: dict[str, Any] | None = None,
    multiwindow_closure_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    lineage_report = lineage_report or _read_json(root / DEFAULT_LINEAGE_PATH) or {}
    contradiction_report = contradiction_report or _read_json(root / DEFAULT_CONTRADICTION_PATH) or {}
    validation_results_report = validation_results_report or _read_json(root / DEFAULT_VALIDATION_RESULTS_PATH) or {}
    oos_blockers_report = oos_blockers_report or _read_json(root / DEFAULT_OOS_BLOCKERS_PATH) or {}
    multiwindow_closure_report = (
        multiwindow_closure_report or _read_json(root / DEFAULT_MULTIWINDOW_CLOSURE_PATH) or {}
    )

    lineage_rows = _read_rows(lineage_report, "rows")
    validation_by_hypothesis = _index_validation_results(
        _read_rows(validation_results_report, "validation_results")
    )
    oos_by_key = _index_oos_blockers(_read_rows(oos_blockers_report, "rows"))
    stale_rows = _read_rows(contradiction_report, "stale_or_superseded")
    stale_paths = _artifact_paths_from_stale_rows(stale_rows)
    closure_status = _text(multiwindow_closure_report.get("closure_status"))

    rows: list[dict[str, Any]] = []
    blocking_counter: Counter[str] = Counter()

    for row in sorted(lineage_rows, key=lambda item: (_text(item.get("thesis_id")), _text(item.get("source_hypothesis_id")))):
        source_hypothesis_id = _text(row.get("source_hypothesis_id"))
        validation_rows = validation_by_hypothesis.get(source_hypothesis_id, [])
        matched_oos_rows = oos_by_key.get(source_hypothesis_id, [])
        provenance_refs = [_text(value) for value in row.get("provenance_refs", []) if _text(value)]
        stale_refs = _match_stale_refs(provenance_refs, stale_paths)
        dimensions, blocking_reasons = _dimension_statuses(
            row=row,
            validation_rows=validation_rows,
            matched_oos_rows=matched_oos_rows,
            stale_refs=stale_refs,
            closure_status=closure_status,
        )
        for reason in blocking_reasons:
            blocking_counter[reason] += 1
        rows.append(
            {
                "thesis_id": _text(row.get("thesis_id")),
                "source_hypothesis_id": source_hypothesis_id,
                "title": _text(row.get("title")),
                "behavior_family": _text(row.get("behavior_family")),
                "lineage_complete": bool(row.get("lineage_complete")),
                "missing_lineage_fields": list(row.get("missing_lineage_fields") or []),
                "stale_artifact_refs": stale_refs,
                "validation_result_count": len(validation_rows),
                "oos_blocker_row_count": len(matched_oos_rows),
                "dimension_statuses": dimensions,
                "blocking_reasons": blocking_reasons,
                "decay_blocks_readiness": bool(blocking_reasons),
                "readiness_support_state": (
                    "not_readiness_authoritative_due_to_decay_or_incompleteness"
                    if blocking_reasons
                    else "context_only_no_decay_blocker_visible"
                ),
                "provenance_refs": provenance_refs,
            }
        )

    blocked_count = sum(1 for row in rows if row["decay_blocks_readiness"])
    summary = {
        "thesis_count": len(rows),
        "blocked_count": blocked_count,
        "clear_count": len(rows) - blocked_count,
        "blocking_reason_counts": dict(sorted(blocking_counter.items())),
        "final_recommendation": (
            "evidence_decay_visible_fail_closed" if rows else "missing_lineage_inputs_fail_closed"
        ),
        "operator_summary": (
            "Evidence decay keeps stale, contradicted, incomplete, unreproducible, "
            "and non-renewed evidence from silently supporting readiness."
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "summary": summary,
        "rows": rows,
        "artifact_references": {
            "qre_contradiction_hypothesis_lineage": DEFAULT_LINEAGE_PATH.as_posix(),
            "qre_contradiction_staleness_intelligence": DEFAULT_CONTRADICTION_PATH.as_posix(),
            "qre_hypothesis_validation_results": DEFAULT_VALIDATION_RESULTS_PATH.as_posix(),
            "qre_oos_evidence_blockers": DEFAULT_OOS_BLOCKERS_PATH.as_posix(),
            "qre_multiwindow_evidence_closure": DEFAULT_MULTIWINDOW_CLOSURE_PATH.as_posix(),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
        },
        "safety_invariants": {
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "mutates_frozen_contracts": False,
            "uses_local_artifacts_only": True,
        },
    }


def write_outputs(
    report: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, str]:
    root = repo_root or Path.cwd()
    base = root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    _validate_write_target(latest)
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, latest)
    return {"latest": latest.relative_to(root).as_posix(), "doc": DOC_PATH.as_posix()}


def read_status(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    path = root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    report = _read_json(path)
    if report is None:
        return {"status": "missing", "path": path.relative_to(root).as_posix()}
    return {
        "status": _text((report.get("summary") or {}).get("final_recommendation")) or "present",
        "path": path.relative_to(root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_evidence_decay",
        description="Materialize read-only QRE evidence decay semantics.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_evidence_decay()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
