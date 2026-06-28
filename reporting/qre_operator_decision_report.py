from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

REPORT_KIND: Final[str] = "qre_operator_decision_report"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017u-2026-06-27"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_operator_decision_report")
LATEST_NAME: Final[str] = "latest.json"
LATEST_MARKDOWN_NAME: Final[str] = "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_operator_decision_report.md")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_EVIDENCE_PATH: Final[Path] = Path("logs/qre_behavior_thesis_evidence/latest.json")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage/latest.json")
DEFAULT_DECAY_PATH: Final[Path] = Path("logs/qre_evidence_decay/latest.json")
DEFAULT_CLOSURE_PATH: Final[Path] = Path("logs/qre_multiwindow_evidence_closure/latest.json")
DEFAULT_RUN_PATH: Final[Path] = Path(
    "logs/qre_preregistered_multiwindow_evidence_run/latest.json"
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_operator_decision_report/",
    "docs/governance/qre_operator_decision_report.md",
)
VALID_DECISIONS: Final[tuple[str, ...]] = (
    "SUPPORTED_FOR_REVIEW",
    "REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
)

_REASON_TEXT: Final[dict[str, str]] = {
    "missing_source_identity": "Source identity is missing from the lineage graph.",
    "missing_data_snapshot_identity": (
        "Data snapshot identity is missing from the lineage graph."
    ),
    "missing_campaign_identity": (
        "Campaign identity is missing from the lineage graph."
    ),
    "lineage_incomplete": "Lineage is incomplete.",
    "validation_result_missing": "No normalized validation result is available.",
    "reproducibility_unverifiable": (
        "Reproducibility cannot be verified from current artifacts."
    ),
    "reproducibility_unverifiable_without_campaign": (
        "Reproducibility cannot be verified without campaign lineage."
    ),
    "campaign_visible_but_validation_missing": (
        "Campaign lineage is visible, but normalized validation results are missing."
    ),
    "contradicting_evidence_visible": "Contradicting evidence remains visible.",
    "stale_or_superseded_artifacts_visible": (
        "Stale or superseded artifacts remain attached to the thesis."
    ),
    "authority_unverifiable_missing_source_identity": (
        "Source authority cannot be verified because source identity is missing."
    ),
    "missing_oos_plan_or_renewal": "Independent OOS planning or renewal is missing.",
    "campaign_closure:all_windows_no_oos_trades": (
        "The preregistered campaign completed with no positive OOS trades."
    ),
    "all_windows_no_oos_trades": (
        "The preregistered campaign completed with no positive OOS trades."
    ),
    "fail_closed_rejected": "The preregistered campaign already records a fail-closed rejection.",
    "non_positive_oos_trade_count": "Observed OOS trade count is non-positive.",
    "accepted_oos_count_mismatch": "Accepted OOS evidence count does not support readiness.",
    "null_controls_incomplete": "Required null controls are incomplete.",
    "controls_incomplete": "Required null controls are incomplete.",
    "regime_context_unresolved": "Regime relevance remains unresolved.",
    "blocked_missing_campaign_lineage": "Campaign lineage has not been established.",
    "context_only_visible_no_execution_authority": (
        "The current evidence remains context-only and non-authoritative."
    ),
}


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


def _normalize_sequence(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _text(item))]
    text = _text(value)
    return [text] if text else []


def _index_by(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _text(row.get(field))
        if key:
            indexed[key] = dict(row)
    return indexed


def _match_campaign(
    source_hypothesis_id: str,
    closure_report: dict[str, Any] | None,
    run_report: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    raw_closure_scope = (
        closure_report.get("campaign_scope") if isinstance(closure_report, dict) else {}
    )
    raw_run_scope = run_report.get("campaign_scope") if isinstance(run_report, dict) else {}
    closure_scope = raw_closure_scope if isinstance(raw_closure_scope, dict) else {}
    run_scope = raw_run_scope if isinstance(raw_run_scope, dict) else {}
    if _text(closure_scope.get("hypothesis_id")) == source_hypothesis_id:
        return closure_report, run_report
    if _text(run_scope.get("hypothesis_id")) == source_hypothesis_id:
        return closure_report, run_report
    return None, None


def _quality_state(
    *,
    registry_row: dict[str, Any],
    lineage_row: dict[str, Any],
    decay_row: dict[str, Any],
) -> str:
    blocking_reasons = set(_normalize_sequence(decay_row.get("blocking_reasons")))
    missing_lineage = bool(lineage_row.get("missing_lineage_fields"))
    source_requirements = _normalize_sequence(registry_row.get("source_requirements"))
    if missing_lineage or {
        "missing_source_identity",
        "missing_data_snapshot_identity",
    } & blocking_reasons:
        return "quality_blocked_missing_identity_chain"
    if any(item.startswith("blocked:") for item in source_requirements):
        return "quality_blocked_by_source_requirements"
    if "stale_or_superseded_artifacts_visible" in blocking_reasons:
        return "quality_degraded_by_stale_or_superseded_artifacts"
    return "quality_visible_context_only"


def _funnel_result(
    *,
    lineage_row: dict[str, Any],
    closure_report: dict[str, Any] | None,
    run_report: dict[str, Any] | None,
) -> dict[str, Any]:
    graph_nodes = lineage_row.get("graph_nodes") if isinstance(lineage_row.get("graph_nodes"), dict) else {}
    campaign_nodes = graph_nodes.get("campaign") if isinstance(graph_nodes.get("campaign"), list) else []
    funnel_nodes = graph_nodes.get("funnel_result") if isinstance(graph_nodes.get("funnel_result"), list) else []
    if not closure_report and not run_report:
        return {
            "status": "no_campaign_closure_visible",
            "campaign_ids": [str(item) for item in campaign_nodes if _text(item)],
            "funnel_result_refs": [str(item) for item in funnel_nodes if _text(item)],
        }
    closure_report = closure_report or {}
    run_report = run_report or {}
    return {
        "status": _text(closure_report.get("closure_status"))
        or _text(run_report.get("campaign_outcome"))
        or "campaign_visible_without_closure_status",
        "campaign_id": _text((closure_report.get("campaign_scope") or {}).get("campaign_id"))
        or _text((run_report.get("campaign_scope") or {}).get("campaign_id")),
        "campaign_ref": _text(closure_report.get("campaign_ref"))
        or _text(run_report.get("campaign_id")),
        "campaign_outcome": _text(closure_report.get("campaign_outcome"))
        or _text(run_report.get("campaign_outcome")),
        "accepted_lineage_count": run_report.get("accepted_lineage_count"),
        "accepted_oos_count": run_report.get("accepted_oos_count"),
        "accepted_window_count": run_report.get("accepted_window_count"),
        "failed_window_count": run_report.get("failed_window_count"),
        "positive_oos_trade_count_total": run_report.get("positive_oos_trade_count_total"),
        "funnel_result_refs": [str(item) for item in funnel_nodes if _text(item)],
    }


def _decision(
    *,
    registry_row: dict[str, Any],
    lineage_row: dict[str, Any],
    decay_row: dict[str, Any],
    closure_report: dict[str, Any] | None,
) -> str:
    closure_disposition = _text((closure_report or {}).get("hypothesis_disposition"))
    if closure_disposition == "fail_closed_rejected":
        return "REJECTED"
    blocking_reasons = set(_normalize_sequence(decay_row.get("blocking_reasons")))
    if bool(lineage_row.get("missing_lineage_fields")) or {
        "missing_source_identity",
        "missing_data_snapshot_identity",
        "missing_campaign_identity",
    } & blocking_reasons:
        return "BLOCKED"
    registry_status = _text(registry_row.get("status"))
    if registry_status == "blocked":
        return "BLOCKED"
    if bool(decay_row.get("decay_blocks_readiness")):
        return "INSUFFICIENT_EVIDENCE"
    return "SUPPORTED_FOR_REVIEW"


def _reason_candidates(
    *,
    decision: str,
    registry_row: dict[str, Any],
    lineage_row: dict[str, Any],
    decay_row: dict[str, Any],
    closure_report: dict[str, Any] | None,
    run_report: dict[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    blocking_reasons = _normalize_sequence(decay_row.get("blocking_reasons"))
    if decision == "REJECTED":
        reasons.extend(_normalize_sequence((closure_report or {}).get("rejection_reasons")))
        reasons.append(_text((closure_report or {}).get("closure_status")))
        reasons.append(_text((closure_report or {}).get("hypothesis_disposition")))
        null_controls = (run_report or {}).get("null_control_results")
        if isinstance(null_controls, dict):
            reasons.extend(_normalize_sequence(null_controls.get("blockers")))
            reasons.append(_text(null_controls.get("status")))
        reasons.extend(blocking_reasons)
    elif decision == "BLOCKED":
        reasons.extend(
            [f"missing:{field}" for field in lineage_row.get("missing_lineage_fields") or []]
        )
        reasons.extend(blocking_reasons)
        reasons.append(_text((lineage_row.get("graph_nodes") or {}).get("policy_decision")))
        reasons.append(_text(registry_row.get("status")))
    elif decision == "INSUFFICIENT_EVIDENCE":
        reasons.extend(blocking_reasons)
        reasons.append(_text((lineage_row.get("graph_nodes") or {}).get("policy_decision")))
    else:
        reasons.append("readiness_supported_by_visible_lineage_and_non_blocked_evidence")
    return _dedupe(reasons)


def _format_reason(reason: str) -> str:
    if reason.startswith("missing:"):
        field = reason.split(":", 1)[1].replace("_", " ")
        return f"Required lineage field is missing: {field}."
    return _REASON_TEXT.get(reason, reason.replace("_", " ").strip().capitalize() + ".")


def _primary_reasons(candidates: list[str]) -> list[str]:
    formatted: list[str] = []
    for candidate in candidates:
        reason = _format_reason(candidate)
        if reason not in formatted:
            formatted.append(reason)
        if len(formatted) >= 5:
            break
    return formatted


def _next_action(
    *,
    decision: str,
    lineage_row: dict[str, Any],
    closure_report: dict[str, Any] | None,
) -> str:
    if decision == "REJECTED":
        action = _text((closure_report or {}).get("recommended_next_action"))
        return action or "reject_hypothesis"
    action = _text((lineage_row.get("graph_nodes") or {}).get("next_action"))
    if action:
        return action
    if decision == "SUPPORTED_FOR_REVIEW":
        return "prepare_operator_review"
    if decision == "INSUFFICIENT_EVIDENCE":
        return "collect_missing_evidence"
    return "keep_blocked"


def _reproducibility_state(decay_row: dict[str, Any]) -> str:
    return _text((decay_row.get("dimension_statuses") or {}).get("reproducibility")) or (
        "reproducibility_not_visible"
    )


def _oos_state(
    *,
    decay_row: dict[str, Any],
    closure_report: dict[str, Any] | None,
    run_report: dict[str, Any] | None,
) -> dict[str, Any]:
    status = _text((decay_row.get("dimension_statuses") or {}).get("missing_oos_renewal"))
    run_report = run_report or {}
    closure_report = closure_report or {}
    return {
        "status": status or "oos_state_not_visible",
        "accepted_oos_count": run_report.get("accepted_oos_count"),
        "accepted_window_count": run_report.get("accepted_window_count"),
        "positive_oos_trade_count_total": run_report.get("positive_oos_trade_count_total"),
        "closure_status": _text(closure_report.get("closure_status")),
        "independence_visible": False,
    }


def _null_control_state(run_report: dict[str, Any] | None) -> dict[str, Any]:
    null_controls = (run_report or {}).get("null_control_results")
    if not isinstance(null_controls, dict):
        return {
            "status": "null_controls_not_visible",
            "missing_control_ids": [],
            "recommended_next_action": "",
        }
    return {
        "status": _text(null_controls.get("status")) or "null_controls_not_visible",
        "missing_control_ids": [
            _text(item) for item in null_controls.get("missing_control_ids") or [] if _text(item)
        ],
        "recommended_next_action": _text(null_controls.get("recommended_next_action")),
    }


def _contradictions_state(
    *,
    evidence_row: dict[str, Any],
    lineage_row: dict[str, Any],
    decay_row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "supporting_evidence_count": evidence_row.get("supporting_evidence_count", 0),
        "contradicting_evidence_count": evidence_row.get("contradicting_evidence_count", 0),
        "unresolved_evidence_count": evidence_row.get("unresolved_evidence_count", 0),
        "contradicting_evidence_refs": _normalize_sequence(
            lineage_row.get("contradicting_evidence_refs")
        ),
        "unresolved_evidence_refs": _normalize_sequence(
            lineage_row.get("unresolved_evidence_refs")
        ),
        "decay_contradiction_state": _text(
            (decay_row.get("dimension_statuses") or {}).get("contradiction_state")
        ),
    }


def build_operator_decision_report(
    *,
    repo_root: Path | None = None,
    registry_report: dict[str, Any] | None = None,
    evidence_report: dict[str, Any] | None = None,
    lineage_report: dict[str, Any] | None = None,
    decay_report: dict[str, Any] | None = None,
    closure_report: dict[str, Any] | None = None,
    run_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry_report = registry_report or _read_json(root / DEFAULT_REGISTRY_PATH) or {}
    evidence_report = evidence_report or _read_json(root / DEFAULT_EVIDENCE_PATH) or {}
    lineage_report = lineage_report or _read_json(root / DEFAULT_LINEAGE_PATH) or {}
    decay_report = decay_report or _read_json(root / DEFAULT_DECAY_PATH) or {}
    closure_report = closure_report or _read_json(root / DEFAULT_CLOSURE_PATH) or {}
    run_report = run_report or _read_json(root / DEFAULT_RUN_PATH) or {}

    registry_by_thesis = _index_by(_read_rows(registry_report, "rows"), "thesis_id")
    evidence_by_thesis = _index_by(_read_rows(evidence_report, "rows"), "thesis_id")
    lineage_by_thesis = _index_by(_read_rows(lineage_report, "rows"), "thesis_id")
    decay_by_thesis = _index_by(_read_rows(decay_report, "rows"), "thesis_id")

    rows: list[dict[str, Any]] = []
    decision_counts = {decision: 0 for decision in VALID_DECISIONS}
    for thesis_id in sorted(registry_by_thesis):
        registry_row = registry_by_thesis[thesis_id]
        evidence_row = evidence_by_thesis.get(thesis_id, {})
        lineage_row = lineage_by_thesis.get(thesis_id, {})
        decay_row = decay_by_thesis.get(thesis_id, {})
        source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
        matched_closure, matched_run = _match_campaign(
            source_hypothesis_id,
            closure_report,
            run_report,
        )
        decision = _decision(
            registry_row=registry_row,
            lineage_row=lineage_row,
            decay_row=decay_row,
            closure_report=matched_closure,
        )
        decision_counts[decision] += 1
        reason_candidates = _reason_candidates(
            decision=decision,
            registry_row=registry_row,
            lineage_row=lineage_row,
            decay_row=decay_row,
            closure_report=matched_closure,
            run_report=matched_run,
        )
        rows.append(
            {
                "thesis_id": thesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "title": _text(registry_row.get("title")),
                "research_question": (
                    f"Does {_text(registry_row.get('title'))} produce reproducible "
                    "bounded evidence under its explicit research scope?"
                ),
                "mechanism": _text(registry_row.get("mechanism")),
                "source_data_quality": {
                    "quality_state": _quality_state(
                        registry_row=registry_row,
                        lineage_row=lineage_row,
                        decay_row=decay_row,
                    ),
                    "source_requirements": _normalize_sequence(
                        registry_row.get("source_requirements")
                    ),
                    "source_freshness": _text(
                        (decay_row.get("dimension_statuses") or {}).get("source_freshness")
                    ),
                    "source_authority_loss": _text(
                        (decay_row.get("dimension_statuses") or {}).get(
                            "source_authority_loss"
                        )
                    ),
                    "data_age": _text(
                        (decay_row.get("dimension_statuses") or {}).get("data_age")
                    ),
                    "stale_artifact_ref_count": len(
                        _normalize_sequence(decay_row.get("stale_artifact_refs"))
                    ),
                },
                "test_plan": {
                    "screening_plan": _normalize_sequence(registry_row.get("screening_plan")),
                    "validation_plan": _normalize_sequence(registry_row.get("validation_plan")),
                    "oos_plan": _normalize_sequence(registry_row.get("oos_plan")),
                    "null_controls": _normalize_sequence(registry_row.get("null_controls")),
                    "minimum_sample": _normalize_sequence(
                        registry_row.get("minimum_sample")
                    ),
                    "falsification_plan": _normalize_sequence(
                        registry_row.get("falsification_plan")
                    ),
                },
                "funnel_result": _funnel_result(
                    lineage_row=lineage_row,
                    closure_report=matched_closure,
                    run_report=matched_run,
                ),
                "final_decision": decision,
                "primary_reasons": _primary_reasons(reason_candidates),
                "next_action": _next_action(
                    decision=decision,
                    lineage_row=lineage_row,
                    closure_report=matched_closure,
                ),
                "reproducibility": _reproducibility_state(decay_row),
                "oos": _oos_state(
                    decay_row=decay_row,
                    closure_report=matched_closure,
                    run_report=matched_run,
                ),
                "null_controls": _null_control_state(matched_run),
                "contradictions": _contradictions_state(
                    evidence_row=evidence_row,
                    lineage_row=lineage_row,
                    decay_row=decay_row,
                ),
                "evidence_completeness": {
                    "thesis_status": _text(registry_row.get("status")),
                    "summary_status": _text(evidence_row.get("summary_status")),
                    "decay_blocks_readiness": bool(decay_row.get("decay_blocks_readiness")),
                    "blocking_reasons": _normalize_sequence(decay_row.get("blocking_reasons")),
                },
                "lineage_completeness": {
                    "lineage_complete": bool(lineage_row.get("lineage_complete")),
                    "missing_lineage_fields": list(
                        lineage_row.get("missing_lineage_fields") or []
                    ),
                    "orphan_status": dict(lineage_row.get("orphan_status") or {}),
                },
                "evidence_based_readiness": (
                    "readiness_supported_for_review"
                    if decision == "SUPPORTED_FOR_REVIEW"
                    else "not_ready_for_review"
                ),
                "provenance_refs": _dedupe(
                    _normalize_sequence(registry_row.get("provenance_refs"))
                    + _normalize_sequence(evidence_row.get("provenance_refs"))
                    + _normalize_sequence(lineage_row.get("provenance_refs"))
                    + _normalize_sequence(decay_row.get("provenance_refs"))
                ),
                "authority_boundary": {
                    "read_only": True,
                    "context_only": True,
                    "can_authorize_execution": False,
                    "can_promote_candidate": False,
                    "can_launch_campaign": False,
                },
            }
        )

    final_recommendation = (
        "operator_decision_report_ready" if rows else "operator_decision_report_missing_inputs"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "summary": {
            "thesis_count": len(rows),
            "decision_counts": decision_counts,
            "final_recommendation": final_recommendation,
            "operator_summary": (
                "Operator decision rows remain read-only and evidence-linked. "
                "They never promote trading authority and fail closed when lineage, "
                "reproducibility, null controls, or OOS evidence are incomplete."
            ),
        },
        "rows": rows,
        "artifact_references": {
            "qre_behavior_thesis_registry": DEFAULT_REGISTRY_PATH.as_posix(),
            "qre_behavior_thesis_evidence": DEFAULT_EVIDENCE_PATH.as_posix(),
            "qre_contradiction_hypothesis_lineage": DEFAULT_LINEAGE_PATH.as_posix(),
            "qre_evidence_decay": DEFAULT_DECAY_PATH.as_posix(),
            "qre_multiwindow_evidence_closure": DEFAULT_CLOSURE_PATH.as_posix(),
            "qre_preregistered_multiwindow_evidence_run": DEFAULT_RUN_PATH.as_posix(),
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


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Operator Decision Report",
        "",
        f"Generated by: `{MODULE_VERSION}`",
        f"Final recommendation: `{(report.get('summary') or {}).get('final_recommendation', '')}`",
        "",
        "| Thesis | Decision | Next action | Primary reasons |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        reasons = "; ".join(_normalize_sequence(row.get("primary_reasons"))) or "None recorded."
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("title")),
                    _text(row.get("final_decision")),
                    _text(row.get("next_action")),
                    reasons.replace("|", "/"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_operator_decision_report.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(
    report: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, str]:
    root = repo_root or Path.cwd()
    base = root / DEFAULT_OUTPUT_DIR
    latest = base / LATEST_NAME
    latest_md = base / LATEST_MARKDOWN_NAME
    doc = root / DOC_PATH
    for target in (latest, latest_md, doc):
        _validate_write_target(target)
    _atomic_write(latest, json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown = render_markdown(report)
    _atomic_write(latest_md, markdown)
    _atomic_write(doc, markdown)
    return {
        "latest": latest.relative_to(root).as_posix(),
        "latest_md": latest_md.relative_to(root).as_posix(),
        "doc": DOC_PATH.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_operator_decision_report",
        description="Materialize read-only per-thesis QRE operator decision reports.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_operator_decision_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
