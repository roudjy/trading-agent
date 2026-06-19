from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal

from packages.qre_data.source_quality_readiness import read_source_quality_status
from research.qre_candidate_identity_lifecycle import build_qre_candidate_identity_lifecycle
from research.qre_evidence_breadth_framework import build_evidence_breadth_framework
from research.qre_null_control_falsification_suite import evaluate_null_control_suite
from research.qre_reason_record_contract import (
    build_reason_record_contract_snapshot,
    validate_reason_record_contract,
)
from research.qre_source_identity_authority_normalization import (
    build_source_identity_authority_report,
)


QualityStatus = Literal[
    "blocked_candidate_missing",
    "blocked_evidence_incomplete",
    "blocked_missing_accepted_oos",
    "blocked_insufficient_sample",
    "blocked_window_inconsistency",
    "blocked_regime_instability",
    "blocked_cost_sensitivity",
    "blocked_slippage_sensitivity",
    "blocked_null_control_failed",
    "blocked_not_reproducible",
    "blocked_source_quality",
    "blocked_scope_mismatch",
    "eligible_for_operator_quality_review",
]

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_candidate_quality_framework"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_candidate_quality_framework")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_candidate_quality_framework/"
DEFAULT_BREADTH_PATH: Final[Path] = Path("logs/qre_evidence_breadth_framework/latest.json")
DEFAULT_LIFECYCLE_PATH: Final[Path] = Path("logs/qre_candidate_identity_lifecycle/latest.json")
DEFAULT_CLOSURE_PATH: Final[Path] = Path("logs/qre_multiwindow_evidence_closure/latest.json")
DEFAULT_DISPOSITION_MEMORY_PATH: Final[Path] = Path("logs/qre_hypothesis_disposition_memory/latest.json")
DEFAULT_NULL_CONTROL_PATH: Final[Path] = Path("logs/qre_null_control_falsification_suite/latest.json")
DEFAULT_REASON_RECORD_CONTRACT_PATH: Final[Path] = Path("logs/qre_reason_record_contract/latest.json")
DEFAULT_SOURCE_AUTHORITY_PATH: Final[Path] = Path("logs/qre_source_identity_authority_normalization/latest.json")
MIN_ACCEPTED_OOS_TRADE_COUNT: Final[int] = 1


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_breadth_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_BREADTH_PATH) or build_evidence_breadth_framework(
        repo_root=repo_root
    )


def _load_disposition_memory(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_DISPOSITION_MEMORY_PATH) or {}


def _load_closure_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_CLOSURE_PATH) or {}


def _load_lifecycle_report(
    repo_root: Path,
    *,
    breadth_report: Mapping[str, Any],
    disposition_memory: Mapping[str, Any],
    closure_report: Mapping[str, Any],
) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_LIFECYCLE_PATH) or build_qre_candidate_identity_lifecycle(
        breadth_report=breadth_report,
        disposition_memory=disposition_memory,
        closure_report=closure_report,
    )


def _load_reason_record_contract(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_REASON_RECORD_CONTRACT_PATH) or build_reason_record_contract_snapshot()


def _load_source_authority_report(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / DEFAULT_SOURCE_AUTHORITY_PATH) or build_source_identity_authority_report(
        repo_root=repo_root
    )


def _breadth_index(breadth_report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = breadth_report.get("coverage_matrix") if isinstance(breadth_report.get("coverage_matrix"), list) else []
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if _text(row.get("dimension")) != "basket":
            continue
        indexed[_text(row.get("scope_key"))] = dict(row)
    return indexed


def _candidate_scope_ref(candidate: Mapping[str, Any]) -> str:
    return _text(candidate.get("source_scope_ref")).removeprefix("coverage_matrix::")


def _reason_record(
    *,
    candidate_id: str,
    status: QualityStatus,
    blocker_codes: Sequence[str],
    evidence_refs: Sequence[str],
    inputs_digest: str,
) -> dict[str, Any]:
    record = {
        "record_id": f"rr_qre_candidate_quality::{candidate_id}",
        "record_kind": "qre_candidate_quality",
        "subject_id": candidate_id,
        "reason_codes": _unique_in_order([status, *blocker_codes]),
        "reason_text": (
            "Candidate quality remains fail-closed until accepted OOS, reproducibility, "
            "null-control, scope-consistency, and source-quality prerequisites are explicitly satisfied."
            if status != "eligible_for_operator_quality_review"
            else "Candidate quality prerequisites are satisfied for operator quality review."
        ),
        "evidence_refs": _unique_in_order(evidence_refs),
        "inputs_digest": inputs_digest,
        "accepted_evidence": status == "eligible_for_operator_quality_review",
        "negative_evidence_preservation": "preserved",
        "source_artifact_ref": "logs/qre_evidence_breadth_framework/latest.json",
        "generation_manifest_ref": "logs/qre_candidate_identity_lifecycle/latest.json",
        "approval_manifest_ref": "logs/qre_candidate_quality_framework/latest.json",
        "basket_request_ref": "logs/qre_evidence_breadth_framework/latest.json",
        "verifier_ref": "logs/qre_multiwindow_evidence_closure/latest.json",
        "closure_ref": "logs/qre_multiwindow_evidence_closure/latest.json",
    }
    record["contract_validation"] = validate_reason_record_contract(record)
    return record


def _control_rows(null_control_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    evaluation = null_control_report.get("evaluation")
    rows = evaluation.get("control_result_rows") if isinstance(evaluation, Mapping) else None
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def _find_control_family(rows: Sequence[Mapping[str, Any]], family: str) -> dict[str, Any] | None:
    for row in rows:
        if _text(row.get("control_family")) == family:
            return dict(row)
    return None


def _source_authority_index(source_authority_report: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = (
        source_authority_report.get("rows")
        if isinstance(source_authority_report, Mapping) and isinstance(source_authority_report.get("rows"), list)
        else []
    )
    return {
        _text(row.get("scope_key")): dict(row)
        for row in rows
        if isinstance(row, Mapping) and _text(row.get("scope_key"))
    }


def _quality_dimensions(
    *,
    candidate: Mapping[str, Any],
    scope_row: Mapping[str, Any] | None,
    closure_report: Mapping[str, Any],
    null_control_report: Mapping[str, Any] | None,
    source_quality_status: Mapping[str, Any],
    source_authority_row: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    accepted_lineage_count = int(candidate.get("accepted_lineage_count") or 0)
    accepted_oos_count = int(candidate.get("accepted_oos_count") or 0)
    closure_status = _text(closure_report.get("closure_status"))
    positive_oos_trade_count_total = int(closure_report.get("positive_oos_trade_count_total") or 0)
    scope_mismatch = False
    if scope_row is None:
        scope_mismatch = True
    else:
        scope_mismatch = (
            int(scope_row.get("accepted_lineage_count") or 0) != accepted_lineage_count
            or int(scope_row.get("accepted_oos_count") or 0) != accepted_oos_count
        )

    reproducibility_status = _text((scope_row or {}).get("reproducibility_status"))
    blocker_reasons = list((scope_row or {}).get("blocker_reasons") or [])
    null_status = _text(((null_control_report or {}).get("evaluation") or {}).get("status"))
    control_rows = _control_rows(null_control_report or {})
    cost_row = _find_control_family(control_rows, "cost_sensitivity")
    slippage_row = _find_control_family(control_rows, "turnover_matched_null")

    return {
        "sample_adequacy": {
            "passed": positive_oos_trade_count_total >= MIN_ACCEPTED_OOS_TRADE_COUNT,
            "observed": positive_oos_trade_count_total,
            "required_minimum": MIN_ACCEPTED_OOS_TRADE_COUNT,
            "reason_code": "accepted_oos_trade_count_below_minimum",
        },
        "accepted_oos": {
            "passed": accepted_oos_count > 0,
            "observed": accepted_oos_count,
            "reason_code": "accepted_oos_missing",
        },
        "window_consistency": {
            "passed": closure_status == "evidence_complete",
            "observed": closure_status or "missing",
            "reason_code": "closure_not_evidence_complete",
        },
        "regime_stability": {
            "passed": int((scope_row or {}).get("regime_count") or 0) > 0,
            "observed": int((scope_row or {}).get("regime_count") or 0),
            "reason_code": "regime_coverage_missing",
        },
        "cost_sensitivity": {
            "passed": bool(cost_row) and bool(cost_row.get("passed")),
            "observed": _text((cost_row or {}).get("result_status")) or "missing",
            "reason_code": "cost_sensitivity_missing_or_failed",
        },
        "slippage_sensitivity": {
            "passed": bool(slippage_row) and bool(slippage_row.get("passed")),
            "observed": _text((slippage_row or {}).get("result_status")) or "missing",
            "reason_code": "slippage_sensitivity_missing_or_failed",
        },
        "null_control_separation": {
            "passed": null_status == "controls_passed_context_only",
            "observed": null_status or "missing",
            "reason_code": "null_controls_missing_or_failed",
        },
        "reproducibility": {
            "passed": reproducibility_status == "reproducible_authoritative",
            "observed": reproducibility_status or "missing",
            "reason_code": "reproducibility_not_authoritative",
        },
        "source_quality": {
            "passed": (
                _text((source_authority_row or {}).get("authority_status")) == "normalized_context_ready"
                if source_authority_row is not None
                else bool(source_quality_status.get("research_ready"))
                and not any("source_quality" in _text(reason) for reason in blocker_reasons)
            ),
            "observed": (
                _text((source_authority_row or {}).get("authority_status"))
                or _text(source_quality_status.get("status"))
                or "missing"
            ),
            "reason_code": (
                _text(((source_authority_row or {}).get("authority_reasons") or [None])[0])
                or "source_quality_not_ready"
            ),
        },
        "artifact_completeness": {
            "passed": accepted_lineage_count > 0 and accepted_oos_count > 0,
            "observed": {
                "accepted_lineage_count": accepted_lineage_count,
                "accepted_oos_count": accepted_oos_count,
            },
            "reason_code": "accepted_evidence_incomplete",
        },
        "scope_consistency": {
            "passed": not scope_mismatch,
            "observed": "matched" if not scope_mismatch else "mismatched",
            "reason_code": "candidate_scope_mismatch",
        },
        "drawdown_behavior": {
            "passed": False,
            "observed": "missing_metric",
            "reason_code": "drawdown_metric_missing",
        },
        "turnover": {
            "passed": False,
            "observed": "missing_metric",
            "reason_code": "turnover_metric_missing",
        },
        "parameter_robustness": {
            "passed": False,
            "observed": "missing_metric",
            "reason_code": "parameter_robustness_missing",
        },
    }


def _determine_status(
    *,
    candidate: Mapping[str, Any],
    dimensions: Mapping[str, Mapping[str, Any]],
) -> tuple[QualityStatus, list[str]]:
    if candidate.get("status") != "evidence_complete":
        return "blocked_evidence_incomplete", list(candidate.get("blockers") or [])
    if not bool(dimensions["scope_consistency"]["passed"]):
        return "blocked_scope_mismatch", [str(dimensions["scope_consistency"]["reason_code"])]
    if not bool(dimensions["accepted_oos"]["passed"]):
        return "blocked_missing_accepted_oos", [str(dimensions["accepted_oos"]["reason_code"])]
    if not bool(dimensions["sample_adequacy"]["passed"]):
        return "blocked_insufficient_sample", [str(dimensions["sample_adequacy"]["reason_code"])]
    if not bool(dimensions["window_consistency"]["passed"]):
        return "blocked_window_inconsistency", [str(dimensions["window_consistency"]["reason_code"])]
    if not bool(dimensions["regime_stability"]["passed"]):
        return "blocked_regime_instability", [str(dimensions["regime_stability"]["reason_code"])]
    if not bool(dimensions["cost_sensitivity"]["passed"]):
        return "blocked_cost_sensitivity", [str(dimensions["cost_sensitivity"]["reason_code"])]
    if not bool(dimensions["slippage_sensitivity"]["passed"]):
        return "blocked_slippage_sensitivity", [str(dimensions["slippage_sensitivity"]["reason_code"])]
    if not bool(dimensions["null_control_separation"]["passed"]):
        return "blocked_null_control_failed", [str(dimensions["null_control_separation"]["reason_code"])]
    if not bool(dimensions["reproducibility"]["passed"]):
        return "blocked_not_reproducible", [str(dimensions["reproducibility"]["reason_code"])]
    if not bool(dimensions["source_quality"]["passed"]):
        return "blocked_source_quality", [str(dimensions["source_quality"]["reason_code"])]
    return "eligible_for_operator_quality_review", []


def evaluate_candidate_quality(
    *,
    candidate_report: Mapping[str, Any] | None,
    breadth_report: Mapping[str, Any],
    closure_report: Mapping[str, Any],
    null_control_report: Mapping[str, Any] | None,
    source_quality_status: Mapping[str, Any],
    reason_record_contract: Mapping[str, Any],
    source_authority_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lifecycle_rows = (
        candidate_report.get("rows")
        if isinstance(candidate_report, Mapping) and isinstance(candidate_report.get("rows"), list)
        else []
    )
    if not lifecycle_rows:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "summary": {
                "status": "blocked_candidate_missing",
                "candidate_count": 0,
                "eligible_candidate_count": 0,
                "blocked_status_counts": {"blocked_candidate_missing": 1},
                "final_recommendation": "candidate_quality_fail_closed",
                "operator_summary": (
                    "No lifecycle candidates are available. Candidate quality remains fail-closed "
                    "until deterministic candidate identities exist."
                ),
            },
            "rows": [],
            "supporting_reports": {
                "reason_record_contract": {
                    "report_kind": reason_record_contract.get("report_kind"),
                    "validation_status": (
                        (reason_record_contract.get("contract") or {})
                        .get("accepted_record_validation", {})
                        .get("validation_status")
                    ),
                },
                "source_quality_status": dict(source_quality_status),
            },
            "authority": {
                "non_authoritative": True,
                "can_promote_candidate": False,
                "can_transition_lifecycle": False,
                "can_activate_shadow": False,
            },
            "safety_invariants": {
                "read_only": True,
                "accepted_evidence_only": True,
                "fixture_evidence_not_authoritative": True,
                "candidate_promotion_forbidden": True,
                "shadow_paper_live_forbidden": True,
            },
        }

    breadth_by_scope = _breadth_index(breadth_report)
    source_authority_by_scope = _source_authority_index(source_authority_report)
    rows: list[dict[str, Any]] = []
    for raw_candidate in lifecycle_rows:
        if not isinstance(raw_candidate, Mapping):
            continue
        candidate = dict(raw_candidate)
        scope_key = _candidate_scope_ref(candidate)
        scope_row = breadth_by_scope.get(scope_key)
        source_authority_row = source_authority_by_scope.get(scope_key)
        dimensions = _quality_dimensions(
            candidate=candidate,
            scope_row=scope_row,
            closure_report=closure_report,
            null_control_report=null_control_report,
            source_quality_status=source_quality_status,
            source_authority_row=source_authority_row,
        )
        status, blocker_codes = _determine_status(candidate=candidate, dimensions=dimensions)
        digest = _digest(
            {
                "candidate_id": candidate.get("candidate_id"),
                "candidate_version": candidate.get("candidate_version"),
                "status": status,
                "dimensions": dimensions,
                "scope_key": scope_key,
            }
        )
        row = {
            "candidate_id": candidate.get("candidate_id"),
            "candidate_version": candidate.get("candidate_version"),
            "lifecycle_status": candidate.get("status"),
            "quality_status": status,
            "next_lifecycle_status": (
                "quality_review" if status == "eligible_for_operator_quality_review" else candidate.get("status")
            ),
            "scope_key": scope_key,
            "scope_signature": candidate.get("scope_signature"),
            "source_scope_ref": candidate.get("source_scope_ref"),
            "source_authority_ref": (
                f"{DEFAULT_SOURCE_AUTHORITY_PATH.as_posix()}#rows::{scope_key}" if source_authority_row else None
            ),
            "accepted_lineage_count": candidate.get("accepted_lineage_count"),
            "accepted_oos_count": candidate.get("accepted_oos_count"),
            "quality_dimensions": dimensions,
            "blocker_codes": blocker_codes,
            "evidence_requirements": _unique_in_order(
                [
                    "accepted_lineage_required",
                    "accepted_oos_required",
                    "evidence_complete_closure_required",
                    "preregistered_null_controls_required",
                    "source_quality_required",
                    "reproducibility_required",
                ]
            ),
            "reason_record": _reason_record(
                candidate_id=_text(candidate.get("candidate_id")) or "unknown_candidate",
                status=status,
                blocker_codes=blocker_codes,
                evidence_refs=_unique_in_order(
                    [
                        _text(candidate.get("source_scope_ref")),
                        _text(closure_report.get("campaign_ref")),
                        _text((null_control_report or {}).get("suite_id")),
                    ]
                ),
                inputs_digest=digest,
            ),
            "deterministic_hash": digest,
            "authority": {
                "non_authoritative": True,
                "can_promote_candidate": False,
                "can_transition_lifecycle": False,
                "operator_review_required": status == "eligible_for_operator_quality_review",
            },
        }
        rows.append(row)

    rows.sort(key=lambda row: (str(row["quality_status"]), str(row["candidate_id"])))
    status_counts = Counter(str(row["quality_status"]) for row in rows)
    summary_status: QualityStatus = (
        "eligible_for_operator_quality_review"
        if rows and all(row["quality_status"] == "eligible_for_operator_quality_review" for row in rows)
        else str(rows[0]["quality_status"])  # type: ignore[assignment]
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "status": summary_status,
            "candidate_count": len(rows),
            "eligible_candidate_count": sum(
                1 for row in rows if row["quality_status"] == "eligible_for_operator_quality_review"
            ),
            "blocked_status_counts": dict(sorted(status_counts.items())),
            "final_recommendation": "candidate_quality_fail_closed",
            "operator_summary": (
                "Candidate quality uses accepted-evidence-only fail-closed gates. "
                "No candidate may advance without accepted OOS, complete closure, "
                "null-control context, source quality, and reproducibility."
            ),
        },
        "rows": rows,
        "supporting_reports": {
            "breadth_report_kind": breadth_report.get("report_kind"),
            "closure_report_kind": closure_report.get("report_kind"),
            "null_control_report_kind": (null_control_report or {}).get("report_kind"),
            "source_quality_status": dict(source_quality_status),
            "source_authority_report_kind": (source_authority_report or {}).get("report_kind"),
            "reason_record_contract": {
                "report_kind": reason_record_contract.get("report_kind"),
                "validation_status": (
                    (reason_record_contract.get("contract") or {})
                    .get("accepted_record_validation", {})
                    .get("validation_status")
                ),
            },
        },
        "authority": {
            "non_authoritative": True,
            "can_promote_candidate": False,
            "can_transition_lifecycle": False,
            "can_activate_shadow": False,
            "can_activate_paper": False,
            "can_activate_live": False,
        },
        "safety_invariants": {
            "read_only": True,
            "accepted_evidence_only": True,
            "missing_metrics_fail_closed": True,
            "fixture_evidence_not_authoritative": True,
            "candidate_promotion_forbidden": True,
            "shadow_paper_live_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def build_candidate_quality_framework(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    breadth_report = _load_breadth_report(repo_root)
    disposition_memory = _load_disposition_memory(repo_root)
    closure_report = _load_closure_report(repo_root)
    lifecycle_report = _load_lifecycle_report(
        repo_root,
        breadth_report=breadth_report,
        disposition_memory=disposition_memory,
        closure_report=closure_report,
    )
    null_control_report = _read_json(repo_root / DEFAULT_NULL_CONTROL_PATH)
    if isinstance(null_control_report, Mapping):
        null_control_report = evaluate_null_control_suite(null_control_report)
    source_quality_status = read_source_quality_status(repo_root=repo_root)
    source_authority_report = _load_source_authority_report(repo_root)
    reason_record_contract = _load_reason_record_contract(repo_root)
    return evaluate_candidate_quality(
        candidate_report=lifecycle_report,
        breadth_report=breadth_report,
        closure_report=closure_report,
        null_control_report=null_control_report,
        source_quality_status=source_quality_status,
        reason_record_contract=reason_record_contract,
        source_authority_report=source_authority_report,
    )


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Candidate Quality Framework",
        "",
        f"- status: {summary.get('status') or 'unknown'}",
        f"- candidate_count: {summary.get('candidate_count') or 0}",
        f"- eligible_candidate_count: {summary.get('eligible_candidate_count') or 0}",
        "",
        "## Candidate Rows",
    ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- {row.get('candidate_id')} quality_status={row.get('quality_status')} next_lifecycle_status={row.get('next_lifecycle_status')}"
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
        "latest": _rel(latest, root=repo_root),
        "operator_summary": _rel(summary_path, root=repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_candidate_quality_framework",
        description="Build the read-only QRE candidate quality framework report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_candidate_quality_framework()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
