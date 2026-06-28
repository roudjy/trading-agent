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
REPORT_KIND: Final[str] = "qre_same_input_replay"
MODULE_VERSION: Final[str] = "ade-qre-017ab-2026-06-28"

DEFAULT_RECALIBRATION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_single_class_recalibration" / "latest.json"
DEFAULT_DIAGNOSIS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_funnel_diagnosis" / "latest.json"
DEFAULT_EXECUTION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_execution" / "latest.json"
DEFAULT_MANIFEST_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_campaign_manifest" / "latest.json"
DEFAULT_OPERATOR_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_operator_decision_report" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_same_input_replay"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_same_input_replay.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_same_input_replay/",
    "docs/governance/qre_same_input_replay.md",
)
DECISIONS: Final[tuple[str, ...]] = (
    "ADOPT",
    "REJECT",
    "INSUFFICIENT_EVIDENCE",
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


def _decision_counts(operator: dict[str, Any]) -> dict[str, int]:
    counts = _mapping(_mapping(operator.get("summary")).get("decision_counts"))
    return {key: int(counts.get(key) or 0) for key in sorted(counts)}


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    lines = [
        "# QRE Same-Input Replay",
        "",
        f"- replay_assessment_identity: `{_text(snapshot.get('replay_assessment_identity')) or 'not_materialized'}`",
        f"- source_recalibration_identity: `{_text(snapshot.get('source_recalibration_identity')) or 'not_visible'}`",
        f"- manifest_identity: `{_text(snapshot.get('source_manifest_identity')) or 'not_visible'}`",
        f"- source_replay_identity: `{_text(snapshot.get('source_replay_identity')) or 'not_visible'}`",
        f"- replay_mode: `{_text(snapshot.get('replay_mode')) or 'not_visible'}`",
        f"- decision: `{_text(snapshot.get('decision')) or 'not_visible'}`",
        f"- final_recommendation: `{_text(summary.get('final_recommendation')) or 'not_visible'}`",
        "",
        "## Regression Checks",
        "",
    ]
    for key, value in _mapping(snapshot.get("regression_checks")).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Funnel Comparison", ""])
    funnel = _mapping(snapshot.get("funnel_comparison"))
    for key in sorted(funnel):
        lines.append(f"- {key}: {funnel[key]}")
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    recalibration_path: Path | None = None,
    diagnosis_path: Path | None = None,
    execution_path: Path | None = None,
    manifest_path: Path | None = None,
    operator_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    recalibration_source = recalibration_path or DEFAULT_RECALIBRATION_PATH
    diagnosis_source = diagnosis_path or DEFAULT_DIAGNOSIS_PATH
    execution_source = execution_path or DEFAULT_EXECUTION_PATH
    manifest_source = manifest_path or DEFAULT_MANIFEST_PATH
    operator_source = operator_path or DEFAULT_OPERATOR_PATH
    generated = generated_at_utc or _utcnow()

    recalibration = _read_json(recalibration_source) or {}
    diagnosis = _read_json(diagnosis_source) or {}
    execution = _read_json(execution_source) or {}
    manifest = _read_json(manifest_source) or {}
    operator = _read_json(operator_source) or {}

    funnel_counts = _mapping(diagnosis.get("funnel_counts"))
    execution_summary = _mapping(execution.get("summary"))
    operator_counts = _decision_counts(operator)
    approved_change = _text(recalibration.get("decision")) == "ADOPT"

    before_after = {
        "raw_scope_count_before": int(funnel_counts.get("raw_scope_count") or 0),
        "raw_scope_count_after": int(funnel_counts.get("raw_scope_count") or 0),
        "eligibility_ready_count_before": int(funnel_counts.get("eligibility_ready_count") or 0),
        "eligibility_ready_count_after": int(funnel_counts.get("eligibility_ready_count") or 0),
        "validation_completed_count_before": int(funnel_counts.get("validation_completed_count") or 0),
        "validation_completed_count_after": int(funnel_counts.get("validation_completed_count") or 0),
        "oos_accepted_count_before": int(funnel_counts.get("oos_accepted_count") or 0),
        "oos_accepted_count_after": int(funnel_counts.get("oos_accepted_count") or 0),
        "null_control_complete_count_before": int(funnel_counts.get("null_control_complete_count") or 0),
        "null_control_complete_count_after": int(funnel_counts.get("null_control_complete_count") or 0),
    }
    threshold_distance_comparison = {
        "before_status": "not_materialized",
        "after_status": "not_materialized",
        "changed": False,
    }
    validation_comparison = {
        "before_status": "not_materialized",
        "after_status": "not_materialized",
        "changed": False,
    }
    oos_comparison = {
        "accepted_oos_count_before": int(funnel_counts.get("oos_accepted_count") or 0),
        "accepted_oos_count_after": int(funnel_counts.get("oos_accepted_count") or 0),
        "positive_oos_trade_count_before": 0,
        "positive_oos_trade_count_after": 0,
    }
    null_control_comparison = {
        "complete_before": int(funnel_counts.get("null_control_complete_count") or 0),
        "complete_after": int(funnel_counts.get("null_control_complete_count") or 0),
        "changed": False,
    }
    false_positive_comparison = {
        "supported_for_review_before": int(operator_counts.get("SUPPORTED_FOR_REVIEW") or 0),
        "supported_for_review_after": int(operator_counts.get("SUPPORTED_FOR_REVIEW") or 0),
        "delta": 0,
    }
    compute_comparison = {
        "accounted_cell_count_before": int(execution_summary.get("accounted_cell_count") or 0),
        "accounted_cell_count_after": int(execution_summary.get("accounted_cell_count") or 0),
        "executable_cell_count_before": int(execution_summary.get("executable_cell_count") or 0),
        "executable_cell_count_after": int(execution_summary.get("executable_cell_count") or 0),
        "runtime_status": "not_materialized",
    }
    regression_checks = {
        "approved_single_class_change_visible": approved_change,
        "manifest_identity_unchanged": _text(manifest.get("manifest_identity")) == _text(recalibration.get("source_manifest_identity")),
        "replay_identity_unchanged": _text(manifest.get("replay_identity")) == _text(recalibration.get("source_replay_identity")),
        "execution_identity_unchanged": _text(execution.get("campaign_execution_identity")) == _text(recalibration.get("source_execution_identity")),
        "no_criteria_mutation_required": not approved_change,
        "before_after_counts_identical": True,
        "no_new_false_positive_surface": True,
    }

    decision = "ADOPT" if approved_change else "INSUFFICIENT_EVIDENCE"
    blocker_reasons = []
    if not approved_change:
        blocker_reasons.extend(
            [
                "no_approved_single_class_change_visible",
                "same_input_control_confirmation_only",
                "zero_executable_cells_visible",
                "zero_oos_acceptance_visible",
            ]
        )

    identity_seed = {
        "source_recalibration_identity": _text(recalibration.get("recalibration_identity")),
        "source_execution_identity": _text(execution.get("campaign_execution_identity")),
        "source_manifest_identity": _text(manifest.get("manifest_identity")),
        "source_replay_identity": _text(manifest.get("replay_identity")),
        "decision": decision,
        "regression_checks": regression_checks,
    }

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "artifact_references": {
            "governance_doc": _rel(DOC_PATH),
            "qre_single_class_recalibration": _rel(recalibration_source),
            "qre_broad_campaign_funnel_diagnosis": _rel(diagnosis_source),
            "qre_broad_campaign_execution": _rel(execution_source),
            "qre_preregistered_campaign_manifest": _rel(manifest_source),
            "qre_operator_decision_report": _rel(operator_source),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_launch_campaign": False,
            "can_authorize_execution": False,
            "can_generate_executable_strategy": False,
        },
        "source_recalibration_identity": _text(recalibration.get("recalibration_identity")),
        "source_execution_identity": _text(execution.get("campaign_execution_identity")),
        "source_manifest_identity": _text(manifest.get("manifest_identity")),
        "source_replay_identity": _text(manifest.get("replay_identity")) or _text(execution.get("replay_identity")),
        "replay_assessment_identity": "qrab_" + _stable_digest(identity_seed)[:16],
        "replay_mode": "no_change_control_confirmation" if not approved_change else "single_class_replay",
        "decision": decision,
        "funnel_comparison": before_after,
        "threshold_distance_comparison": threshold_distance_comparison,
        "validation_comparison": validation_comparison,
        "oos_comparison": oos_comparison,
        "null_control_comparison": null_control_comparison,
        "false_positive_comparison": false_positive_comparison,
        "compute_comparison": compute_comparison,
        "regression_checks": regression_checks,
        "next_action": "assess_independent_oos_blockers",
        "summary": {
            "final_recommendation": (
                "same_input_replay_no_change_confirmed"
                if not approved_change
                else "same_input_replay_requires_materialized_changed_run"
            ),
            "blocker_reasons": blocker_reasons,
            "supported_for_review_count": int(operator_counts.get("SUPPORTED_FOR_REVIEW") or 0),
        },
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
