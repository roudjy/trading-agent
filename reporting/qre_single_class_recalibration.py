from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_single_class_recalibration"
MODULE_VERSION: Final[str] = "ade-qre-017aa-2026-06-28"

DEFAULT_DIAGNOSIS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_funnel_diagnosis" / "latest.json"
DEFAULT_EXECUTION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_execution" / "latest.json"
DEFAULT_MANIFEST_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_campaign_manifest" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_single_class_recalibration"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_single_class_recalibration.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_single_class_recalibration/",
    "docs/governance/qre_single_class_recalibration.md",
)
DECISIONS: Final[tuple[str, ...]] = (
    "ADOPT",
    "REJECT",
    "INSUFFICIENT_EVIDENCE",
)
CHANGE_READY_RECOMMENDATIONS: Final[set[str]] = {
    "replace",
    "move_to_later_stage",
    "remove_as_redundant",
}
FORBIDDEN_CONCURRENT_CHANGES: Final[tuple[str, ...]] = (
    "hypothesis_changes_forbidden",
    "strategy_changes_forbidden",
    "preset_changes_forbidden",
    "dataset_identity_changes_forbidden",
    "universe_changes_forbidden",
    "window_changes_forbidden",
    "cost_changes_forbidden",
    "slippage_changes_forbidden",
    "null_control_changes_forbidden",
    "unrelated_criteria_changes_forbidden",
    "survivor_targeting_forbidden",
)
ADOPTION_CRITERIA: Final[tuple[str, ...]] = (
    "exactly_one_criterion_class_supported_for_change",
    "at_least_one_executable_or_eligibility_ready_cell_visible",
    "threshold_distance_or_equivalent_margin_evidence_visible",
    "change_candidate_not_a_known_survivor",
    "supporting_evidence_outweighs_regression_risk",
)
REJECTION_CRITERIA: Final[tuple[str, ...]] = (
    "primary_bottleneck_is_evidence_completeness",
    "zero_executable_cells_visible",
    "zero_eligibility_ready_cells_visible",
    "zero_oos_acceptance_visible",
    "zero_null_control_completion_visible",
    "no_threshold_distance_evidence_visible",
    "no_single_change_ready_criterion_visible",
)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _stable_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_write_target(path: Path) -> None:
    normalized = _rel(path)
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _threshold_distance_visible(diagnosis: dict[str, Any]) -> bool:
    summary = _mapping(diagnosis.get("summary"))
    if summary.get("threshold_distance_visible") is True:
        return True
    return bool(_mapping(diagnosis.get("threshold_distances")))


def _candidate_row(
    row: dict[str, Any],
    *,
    execution_summary: dict[str, Any],
    diagnosis_summary: dict[str, Any],
    threshold_distance_visible: bool,
) -> dict[str, Any]:
    criterion_id = _text(row.get("criterion_id"))
    recommendation = _text(row.get("recommendation"))
    affected_count = int(row.get("affected_cell_count") or 0)
    blockers: list[str] = []
    if recommendation not in CHANGE_READY_RECOMMENDATIONS:
        blockers.append(f"diagnosis_recommendation_not_change_ready:{recommendation or 'missing'}")
    if int(execution_summary.get("executable_cell_count") or 0) == 0:
        blockers.append("zero_executable_cells")
    if int(_mapping(diagnosis_summary.get("funnel_counts")).get("eligibility_ready_count") or 0) == 0:
        blockers.append("zero_eligibility_ready_cells")
    if int(_mapping(diagnosis_summary.get("funnel_counts")).get("oos_accepted_count") or 0) == 0:
        blockers.append("zero_oos_acceptance")
    if int(_mapping(diagnosis_summary.get("funnel_counts")).get("null_control_complete_count") or 0) == 0:
        blockers.append("zero_null_control_completion")
    if not threshold_distance_visible:
        blockers.append("threshold_distance_evidence_absent")
    if affected_count == 0:
        blockers.append("criterion_has_no_affected_cells")
    return {
        "criterion_id": criterion_id,
        "diagnosis_recommendation": recommendation,
        "affected_cell_count": affected_count,
        "affected_cell_ids": _normalize_str_list(row.get("affected_cell_ids")),
        "eligible_for_recalibration": not blockers,
        "blocker_reasons": blockers,
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    prereg = _mapping(snapshot.get("preregistration"))
    lines = [
        "# QRE Single-Class Recalibration",
        "",
        f"- recalibration_identity: `{_text(snapshot.get('recalibration_identity')) or 'not_materialized'}`",
        f"- source_diagnosis_identity: `{_text(snapshot.get('source_diagnosis_identity')) or 'not_visible'}`",
        f"- source_execution_identity: `{_text(snapshot.get('source_execution_identity')) or 'not_visible'}`",
        f"- source_manifest_identity: `{_text(snapshot.get('source_manifest_identity')) or 'not_visible'}`",
        f"- source_replay_identity: `{_text(snapshot.get('source_replay_identity')) or 'not_visible'}`",
        f"- decision: `{_text(snapshot.get('decision')) or 'not_visible'}`",
        f"- selected_criterion_class: `{_text(snapshot.get('selected_criterion_class')) or 'none'}`",
        f"- next_action: `{_text(snapshot.get('next_action')) or 'not_visible'}`",
        f"- final_recommendation: `{_text(summary.get('final_recommendation')) or 'not_visible'}`",
        "",
        "## Decision Basis",
        "",
        f"- primary_bottleneck: `{_text(summary.get('primary_bottleneck')) or 'not_visible'}`",
        f"- executable_cell_count: {int(summary.get('executable_cell_count') or 0)}",
        f"- eligibility_ready_count: {int(summary.get('eligibility_ready_count') or 0)}",
        f"- oos_accepted_count: {int(summary.get('oos_accepted_count') or 0)}",
        f"- null_control_complete_count: {int(summary.get('null_control_complete_count') or 0)}",
        "",
        "## Candidate Criteria",
        "",
    ]
    for row in _list_of_mappings(snapshot.get("candidate_rows")):
        blockers = ", ".join(_normalize_str_list(row.get("blocker_reasons"))) or "none"
        lines.append(
            f"- `{_text(row.get('criterion_id'))}`: `{_text(row.get('diagnosis_recommendation'))}` / eligible=`{str(bool(row.get('eligible_for_recalibration'))).lower()}` / blockers={blockers}"
        )
    lines.extend(["", "## Preregistration", ""])
    lines.append(f"- expected_effect: `{_text(prereg.get('expected_effect')) or 'not_visible'}`")
    lines.append(f"- reversal_plan: `{_text(prereg.get('reversal_plan')) or 'not_visible'}`")
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    diagnosis_path: Path | None = None,
    execution_path: Path | None = None,
    manifest_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    diagnosis_source = diagnosis_path or DEFAULT_DIAGNOSIS_PATH
    execution_source = execution_path or DEFAULT_EXECUTION_PATH
    manifest_source = manifest_path or DEFAULT_MANIFEST_PATH
    generated = generated_at_utc or _utcnow()

    diagnosis = _read_json(diagnosis_source) or {}
    execution = _read_json(execution_source) or {}
    manifest = _read_json(manifest_source) or {}

    diagnosis_summary = _mapping(diagnosis.get("summary"))
    execution_summary = _mapping(execution.get("summary"))
    funnel_counts = _mapping(diagnosis.get("funnel_counts"))
    threshold_visible = _threshold_distance_visible(diagnosis)

    candidate_rows = [
        _candidate_row(
            row,
            execution_summary=execution_summary,
            diagnosis_summary=diagnosis,
            threshold_distance_visible=threshold_visible,
        )
        for row in _list_of_mappings(diagnosis.get("criterion_rows"))
    ]
    candidate_rows.sort(key=lambda row: (_text(row.get("criterion_id")), _text(row.get("diagnosis_recommendation"))))
    selected = next((row for row in candidate_rows if bool(row.get("eligible_for_recalibration"))), None)

    decision = "ADOPT" if selected else "INSUFFICIENT_EVIDENCE"
    selected_class = _text(_mapping(selected).get("criterion_id"))
    supporting_evidence = []
    if selected:
        supporting_evidence = [
            f"criterion:{selected_class}",
            f"recommendation:{_text(selected.get('diagnosis_recommendation'))}",
        ]
    else:
        supporting_evidence = [
            "state:primary_bottleneck:evidence_completeness",
            "state:zero_executable_cells_visible",
            "state:zero_eligibility_ready_cells_visible",
            "state:zero_oos_acceptance_visible",
            "state:zero_null_control_completion_visible",
            "state:threshold_distance_evidence_absent",
        ]

    preregistration = {
        "selected_criterion_class": selected_class,
        "supporting_evidence": supporting_evidence,
        "expected_effect": (
            f"bounded adjustment of {selected_class} only"
            if selected_class
            else "no criterion change; preserve current preregistered inputs and fail closed into control replay"
        ),
        "forbidden_concurrent_changes": list(FORBIDDEN_CONCURRENT_CHANGES),
        "regression_conditions": [
            "any_input_identity_drift",
            "any_second_criterion_change",
            "any_survivor_targeting_signal",
            "any_false_positive_increase_without_supporting_oos",
        ],
        "adoption_criteria": list(ADOPTION_CRITERIA),
        "rejection_criteria": list(REJECTION_CRITERIA),
        "reversal_plan": (
            f"revert {selected_class} to the pre-017AA baseline before any additional replay"
            if selected_class
            else "retain the current criteria unchanged and use the canonical no-change control replay in ADE-QRE-017AB"
        ),
    }

    summary = {
        "primary_bottleneck": _text(diagnosis_summary.get("primary_bottleneck")),
        "secondary_bottlenecks": _normalize_str_list(diagnosis_summary.get("secondary_bottlenecks")),
        "executable_cell_count": int(execution_summary.get("executable_cell_count") or 0),
        "eligibility_ready_count": int(funnel_counts.get("eligibility_ready_count") or 0),
        "oos_accepted_count": int(funnel_counts.get("oos_accepted_count") or 0),
        "null_control_complete_count": int(funnel_counts.get("null_control_complete_count") or 0),
        "threshold_distance_visible": threshold_visible,
        "change_ready_candidate_count": sum(1 for row in candidate_rows if bool(row.get("eligible_for_recalibration"))),
        "final_recommendation": (
            "single_class_recalibration_not_justified"
            if decision != "ADOPT"
            else "single_class_recalibration_preregistered"
        ),
    }

    identity_seed = {
        "decision": decision,
        "selected_criterion_class": selected_class,
        "source_diagnosis_identity": _text(diagnosis.get("diagnosis_identity")),
        "source_execution_identity": _text(execution.get("campaign_execution_identity")),
        "source_manifest_identity": _text(manifest.get("manifest_identity")),
        "source_replay_identity": _text(execution.get("replay_identity")) or _text(manifest.get("replay_identity")),
        "candidate_rows": candidate_rows,
        "preregistration": preregistration,
    }

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "artifact_references": {
            "governance_doc": _rel(DOC_PATH),
            "qre_broad_campaign_funnel_diagnosis": _rel(diagnosis_source),
            "qre_broad_campaign_execution": _rel(execution_source),
            "qre_preregistered_campaign_manifest": _rel(manifest_source),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_launch_campaign": False,
            "can_authorize_execution": False,
            "can_generate_executable_strategy": False,
            "mutates_strategy_or_preset": False,
        },
        "source_diagnosis_identity": _text(diagnosis.get("diagnosis_identity")),
        "source_execution_identity": _text(execution.get("campaign_execution_identity")),
        "source_manifest_identity": _text(manifest.get("manifest_identity")),
        "source_replay_identity": _text(execution.get("replay_identity")) or _text(manifest.get("replay_identity")),
        "recalibration_identity": "qraa_" + _stable_digest(identity_seed)[:16],
        "decision": decision,
        "selected_criterion_class": selected_class,
        "candidate_rows": candidate_rows,
        "preregistration": preregistration,
        "next_action": "run_no_change_control_replay" if decision != "ADOPT" else "run_single_class_replay",
        "summary": summary,
        "safety_invariants": {
            "read_only": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "mutates_frozen_contracts": False,
            "mutates_campaign_queue": False,
            "mutates_strategy_or_preset": False,
        },
    }


def _atomic_write(path: Path, text: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    _atomic_write(ARTIFACT_MARKDOWN, _render_markdown(snapshot))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=REPORT_KIND)
    parser.add_argument("--write", action="store_true", help="write latest artifacts")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot()
    if args.write:
        write_outputs(snapshot)
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
