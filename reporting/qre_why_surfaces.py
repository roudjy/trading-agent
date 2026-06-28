from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

REPORT_KIND: Final[str] = "qre_why_surfaces"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017v-2026-06-28"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_why_surfaces")
LATEST_NAME: Final[str] = "latest.json"
LATEST_MARKDOWN_NAME: Final[str] = "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_why_surfaces.md")
DEFAULT_OPERATOR_REPORT_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage/latest.json")
DEFAULT_DECAY_PATH: Final[Path] = Path("logs/qre_evidence_decay/latest.json")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_why_surfaces/",
    "docs/governance/qre_why_surfaces.md",
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


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _normalize_sequence(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _text(item))]
    text = _text(value)
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return out


def _index_by(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _text(row.get(field))
        if key:
            indexed[key] = dict(row)
    return indexed


def _status_counter(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        section = row.get(field)
        if not isinstance(section, dict):
            continue
        status = _text(section.get("status")) or "missing"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _supporting_count(row: dict[str, Any]) -> int:
    contradictions = row.get("contradictions")
    if not isinstance(contradictions, dict):
        return 0
    count = contradictions.get("supporting_evidence_count")
    return count if isinstance(count, int) else 0


def _missing_evidence_states(
    operator_row: dict[str, Any],
    lineage_row: dict[str, Any],
    decay_row: dict[str, Any],
) -> list[str]:
    missing = [f"missing_lineage:{field}" for field in _normalize_sequence(lineage_row.get("missing_lineage_fields"))]
    missing.extend(
        f"blocking_reason:{reason}"
        for reason in _normalize_sequence((decay_row.get("blocking_reasons")))
    )
    contradictions = operator_row.get("contradictions")
    if isinstance(contradictions, dict):
        missing.extend(
            f"unresolved:{item}"
            for item in _normalize_sequence(contradictions.get("unresolved_evidence_refs"))
        )
    return _dedupe(missing)


def _why_explored(
    operator_row: dict[str, Any],
    lineage_row: dict[str, Any],
) -> dict[str, Any]:
    supporting_count = _supporting_count(operator_row)
    mechanism_visible = bool(_text(operator_row.get("mechanism")))
    evidence_refs = _dedupe(
        _normalize_sequence(lineage_row.get("supporting_evidence_refs"))
        + _normalize_sequence(operator_row.get("provenance_refs"))
    )
    if supporting_count > 0:
        explanation = (
            f"This thesis remains in scope because {supporting_count} supporting evidence "
            "reference(s) are visible and the thesis record remains present."
        )
        if mechanism_visible:
            explanation += " Mechanism text is present."
        status = "evidence_linked"
    else:
        explanation = (
            "The thesis record remains present, but no supporting evidence references are "
            "currently visible."
        )
        status = "record_present_without_supporting_evidence"
    return {
        "status": status,
        "explanation": explanation,
        "supporting_evidence_count": supporting_count,
        "mechanism_visible": mechanism_visible,
        "evidence_refs": evidence_refs,
        "missing_evidence": [] if supporting_count > 0 else ["supporting_evidence_refs"],
    }


def _why_failed(operator_row: dict[str, Any]) -> dict[str, Any]:
    decision = _text(operator_row.get("final_decision"))
    funnel_result = operator_row.get("funnel_result") if isinstance(operator_row.get("funnel_result"), dict) else {}
    null_controls = operator_row.get("null_controls") if isinstance(operator_row.get("null_controls"), dict) else {}
    reasons = _normalize_sequence(operator_row.get("primary_reasons"))
    if decision != "REJECTED":
        return {
            "status": "not_rejected",
            "explanation": "No rejected thesis outcome is visible for this row.",
            "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
            "missing_evidence": [],
        }
    details = [
        f"campaign closure status `{_text(operator_row.get('oos', {}).get('closure_status')) or _text(funnel_result.get('status'))}`",
        f"campaign outcome `{_text(funnel_result.get('campaign_outcome')) or 'not_visible'}`",
    ]
    accepted_oos_count = operator_row.get("oos", {}).get("accepted_oos_count") if isinstance(operator_row.get("oos"), dict) else None
    if accepted_oos_count is not None:
        details.append(f"accepted OOS count `{accepted_oos_count}`")
    null_control_status = _text(null_controls.get("status"))
    if null_control_status:
        details.append(f"null controls `{null_control_status}`")
    return {
        "status": "failure_explained",
        "explanation": "Failure is evidence-backed via " + ", ".join(details) + ".",
        "primary_reasons": reasons,
        "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
        "missing_evidence": [],
    }


def _why_blocked(
    operator_row: dict[str, Any],
    lineage_row: dict[str, Any],
    decay_row: dict[str, Any],
) -> dict[str, Any]:
    decision = _text(operator_row.get("final_decision"))
    missing_lineage = _normalize_sequence(lineage_row.get("missing_lineage_fields"))
    blocking_reasons = _normalize_sequence(decay_row.get("blocking_reasons"))
    if decision != "BLOCKED" and not missing_lineage:
        return {
            "status": "not_blocked",
            "explanation": "No blocked thesis state is visible for this row.",
            "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
            "missing_evidence": [],
        }
    details: list[str] = []
    if missing_lineage:
        details.append("missing lineage fields: " + ", ".join(missing_lineage))
    if blocking_reasons:
        details.append("blocking reasons: " + ", ".join(blocking_reasons[:5]))
    explanation = (
        "Blocked status is evidence-backed because " + "; ".join(details) + "."
        if details
        else "Blocked status is visible, but the specific blocker explanation is not populated."
    )
    return {
        "status": "blocked_explained" if details else "blocked_without_specific_driver",
        "explanation": explanation,
        "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
        "missing_evidence": [] if details else ["specific_blocker_driver"],
    }


def _why_no_candidate(
    operator_row: dict[str, Any],
    lineage_row: dict[str, Any],
) -> dict[str, Any]:
    funnel_result = operator_row.get("funnel_result") if isinstance(operator_row.get("funnel_result"), dict) else {}
    campaign_ids = _normalize_sequence(funnel_result.get("campaign_ids"))
    campaign_nodes = _normalize_sequence((lineage_row.get("graph_nodes") or {}).get("campaign"))
    candidate_missing = not campaign_ids and not campaign_nodes
    campaign_outcome = _text(funnel_result.get("campaign_outcome"))
    funnel_status = _text(funnel_result.get("status"))
    if candidate_missing:
        return {
            "status": "blocked_before_candidate_stage",
            "explanation": (
                "No candidate emergence is visible because campaign lineage is absent, so the "
                "thesis never reached a candidate-producing stage."
            ),
            "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
            "missing_evidence": ["campaign_identity", "funnel_result"],
        }
    if campaign_outcome or funnel_status:
        return {
            "status": "candidate_outcome_visible",
            "explanation": (
                "Candidate emergence is explained by visible funnel evidence: "
                f"status `{funnel_status or 'not_visible'}` and outcome "
                f"`{campaign_outcome or 'not_visible'}`."
            ),
            "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
            "missing_evidence": [],
        }
    return {
        "status": "candidate_state_not_visible",
        "explanation": "No explicit candidate-emergence explanation is visible in the current funnel artifacts.",
        "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
        "missing_evidence": ["candidate_outcome"],
    }


def _why_evidence_insufficient(
    operator_row: dict[str, Any],
    decay_row: dict[str, Any],
) -> dict[str, Any]:
    decision = _text(operator_row.get("final_decision"))
    blocking_reasons = _normalize_sequence(decay_row.get("blocking_reasons"))
    unresolved = _normalize_sequence(
        (operator_row.get("contradictions") or {}).get("unresolved_evidence_refs")
        if isinstance(operator_row.get("contradictions"), dict)
        else []
    )
    if decision == "INSUFFICIENT_EVIDENCE":
        return {
            "status": "insufficiency_explained",
            "explanation": (
                "Insufficient evidence is visible because readiness remains blocked by "
                + ", ".join(blocking_reasons[:5] or ["unresolved evidence"])
                + "."
            ),
            "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
            "missing_evidence": _dedupe(blocking_reasons + unresolved),
        }
    if bool((operator_row.get("evidence_completeness") or {}).get("decay_blocks_readiness")):
        return {
            "status": "insufficiency_visible_but_not_primary_decision",
            "explanation": (
                "Evidence insufficiency remains visible even though another decision class is "
                "primary for this row."
            ),
            "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
            "missing_evidence": _dedupe(blocking_reasons + unresolved),
        }
    return {
        "status": "no_visible_evidence_insufficiency",
        "explanation": "No separate evidence-insufficiency state is visible beyond the current decision row.",
        "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
        "missing_evidence": [],
    }


def _why_next_action(operator_row: dict[str, Any], decay_row: dict[str, Any]) -> dict[str, Any]:
    next_action = _text(operator_row.get("next_action")) or "not_visible"
    decision = _text(operator_row.get("final_decision")) or "not_visible"
    primary_reasons = _normalize_sequence(operator_row.get("primary_reasons"))
    blocking_reasons = _normalize_sequence(decay_row.get("blocking_reasons"))
    drivers = primary_reasons[:2] or blocking_reasons[:2]
    explanation = (
        f"Next action `{next_action}` is selected because the current decision is `{decision}`"
    )
    if drivers:
        explanation += " and the visible drivers are " + "; ".join(drivers) + "."
    else:
        explanation += "."
    return {
        "status": "next_action_evidence_linked" if next_action != "not_visible" else "next_action_not_visible",
        "explanation": explanation,
        "evidence_refs": _normalize_sequence(operator_row.get("provenance_refs")),
        "missing_evidence": [] if next_action != "not_visible" else ["next_action"],
    }


def build_why_surfaces(
    *,
    repo_root: Path | None = None,
    operator_report: dict[str, Any] | None = None,
    lineage_report: dict[str, Any] | None = None,
    decay_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    operator_report = operator_report or _read_json(root / DEFAULT_OPERATOR_REPORT_PATH) or {}
    lineage_report = lineage_report or _read_json(root / DEFAULT_LINEAGE_PATH) or {}
    decay_report = decay_report or _read_json(root / DEFAULT_DECAY_PATH) or {}

    operator_rows = _read_rows(operator_report, "rows")
    lineage_by_thesis = _index_by(_read_rows(lineage_report, "rows"), "thesis_id")
    decay_by_thesis = _index_by(_read_rows(decay_report, "rows"), "thesis_id")

    rows: list[dict[str, Any]] = []
    for operator_row in sorted(operator_rows, key=lambda row: (_text(row.get("thesis_id")), _text(row.get("source_hypothesis_id")))):
        thesis_id = _text(operator_row.get("thesis_id"))
        lineage_row = lineage_by_thesis.get(thesis_id, {})
        decay_row = decay_by_thesis.get(thesis_id, {})
        rows.append(
            {
                "thesis_id": thesis_id,
                "source_hypothesis_id": _text(operator_row.get("source_hypothesis_id")),
                "title": _text(operator_row.get("title")),
                "final_decision": _text(operator_row.get("final_decision")),
                "next_action": _text(operator_row.get("next_action")),
                "why_explored": _why_explored(operator_row, lineage_row),
                "why_failed": _why_failed(operator_row),
                "why_blocked": _why_blocked(operator_row, lineage_row, decay_row),
                "why_no_candidate_emerged": _why_no_candidate(operator_row, lineage_row),
                "why_evidence_insufficient": _why_evidence_insufficient(operator_row, decay_row),
                "why_next_action_selected": _why_next_action(operator_row, decay_row),
                "missing_evidence_states": _missing_evidence_states(operator_row, lineage_row, decay_row),
                "provenance_refs": _dedupe(
                    _normalize_sequence(operator_row.get("provenance_refs"))
                    + _normalize_sequence(lineage_row.get("provenance_refs"))
                    + _normalize_sequence(decay_row.get("provenance_refs"))
                ),
                "authority_boundary": {
                    "read_only": True,
                    "context_only": True,
                    "can_authorize_execution": False,
                    "can_launch_campaign": False,
                    "can_promote_candidate": False,
                },
            }
        )

    final_recommendation = "why_surfaces_ready" if rows else "why_surfaces_missing_inputs"
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "summary": {
            "thesis_count": len(rows),
            "decision_counts": {
                decision: sum(1 for row in rows if _text(row.get("final_decision")) == decision)
                for decision in ("SUPPORTED_FOR_REVIEW", "REJECTED", "INSUFFICIENT_EVIDENCE", "BLOCKED")
            },
            "why_blocked_status_counts": _status_counter(rows, "why_blocked"),
            "why_failed_status_counts": _status_counter(rows, "why_failed"),
            "why_no_candidate_status_counts": _status_counter(rows, "why_no_candidate_emerged"),
            "why_evidence_insufficient_status_counts": _status_counter(rows, "why_evidence_insufficient"),
            "final_recommendation": final_recommendation,
            "operator_summary": (
                "Why surfaces remain deterministic, provenance-linked, read-only, and "
                "explicit about missing evidence. They never add trading or campaign authority."
            ),
        },
        "rows": rows,
        "artifact_references": {
            "qre_operator_decision_report": DEFAULT_OPERATOR_REPORT_PATH.as_posix(),
            "qre_contradiction_hypothesis_lineage": DEFAULT_LINEAGE_PATH.as_posix(),
            "qre_evidence_decay": DEFAULT_DECAY_PATH.as_posix(),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_authorize_execution": False,
            "can_launch_campaign": False,
            "can_promote_candidate": False,
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
        "# QRE Why Surfaces",
        "",
        f"Generated by: `{MODULE_VERSION}`",
        f"Final recommendation: `{(report.get('summary') or {}).get('final_recommendation', '')}`",
        "",
        "| Thesis | Decision | Why blocked | Why failed | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        why_blocked = _text(((row.get("why_blocked") or {}).get("status")))
        why_failed = _text(((row.get("why_failed") or {}).get("status")))
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("title")),
                    _text(row.get("final_decision")),
                    why_blocked or "not_visible",
                    why_failed or "not_visible",
                    _text(row.get("next_action")),
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
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_why_surfaces.", suffix=".tmp", dir=str(path.parent))
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
        prog="python -m reporting.qre_why_surfaces",
        description="Materialize read-only QRE why-explained surfaces.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_why_surfaces()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
