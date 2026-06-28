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
REPORT_KIND: Final[str] = "qre_repeated_independent_oos"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017ac-2026-06-28"

DEFAULT_REGISTRY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_behavior_thesis_registry" / "latest.json"
DEFAULT_OPERATOR_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_operator_decision_report" / "latest.json"
DEFAULT_LINEAGE_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_contradiction_hypothesis_lineage" / "latest.json"
DEFAULT_REPLAY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_same_input_replay" / "latest.json"
DEFAULT_RUN_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json"
DEFAULT_CLOSURE_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_multiwindow_evidence_closure" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_repeated_independent_oos"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_repeated_independent_oos.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_repeated_independent_oos/",
    "docs/governance/qre_repeated_independent_oos.md",
)
ROW_STATUS_VOCAB: Final[tuple[str, ...]] = (
    "BLOCKED_MISSING_CAMPAIGN_LINEAGE",
    "BLOCKED_REJECTED_NO_ACCEPTED_OOS",
    "BLOCKED_REPLAY_NO_EXECUTABLE_CELLS",
    "INSUFFICIENT_EVIDENCE_NO_UNUSED_INDEPENDENT_WINDOW",
    "READY_FOR_INDEPENDENT_OOS",
)
DECISION_VOCAB: Final[tuple[str, ...]] = (
    "ACCEPTED",
    "REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
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


def _rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get(field)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


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


def _index_by(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _text(row.get(field))
        if key:
            indexed[key] = dict(row)
    return indexed


def _consumed_windows(run: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(_rows(run, "window_results"), start=1):
        out.append(
            {
                "window_sequence": index,
                "bounded_input_window": _mapping(row.get("bounded_input_window")),
                "oos_window": _mapping(row.get("oos_window")),
                "accepted_oos_count": row.get("accepted_oos_count"),
                "positive_oos_trade_count_total": row.get("positive_oos_trade_count_total"),
                "window_identity_visible": False,
                "window_identity_blockers": [
                    "window_identity_not_materialized_in_source_artifact",
                ],
                "provenance_ref": f"{_rel(DEFAULT_RUN_PATH)}#window_results[{index - 1}]",
            }
        )
    return out


def _row_status(
    *,
    operator_row: dict[str, Any],
    lineage_row: dict[str, Any],
    replay: dict[str, Any],
    consumed_windows: list[dict[str, Any]],
) -> tuple[str, str, list[str], str]:
    decision = _text(operator_row.get("final_decision"))
    missing_lineage = _normalize_str_list(lineage_row.get("missing_lineage_fields"))
    replay_blockers = _normalize_str_list(_mapping(replay.get("summary")).get("blocker_reasons"))

    if missing_lineage:
        return (
            "BLOCKED_MISSING_CAMPAIGN_LINEAGE",
            "BLOCKED",
            [f"missing_lineage:{field}" for field in missing_lineage],
            "establish_campaign_lineage_for_thesis",
        )
    if decision == "REJECTED":
        blockers = [
            "operator_decision_rejected",
            "accepted_oos_count_zero",
            "accepted_window_count_zero",
            "no_positive_oos_trade_count_visible",
            "independence_not_visible",
            "consumed_oos_windows_are_already_used",
        ]
        return (
            "BLOCKED_REJECTED_NO_ACCEPTED_OOS",
            "INSUFFICIENT_EVIDENCE",
            blockers,
            "preserve_fail_closed_rejection",
        )
    if replay_blockers:
        return (
            "BLOCKED_REPLAY_NO_EXECUTABLE_CELLS",
            "INSUFFICIENT_EVIDENCE",
            ["same_input_replay_confirms_no_executable_cells", *replay_blockers],
            "preserve_blocked_synthesis_until_new_authoritative_windows_exist",
        )
    if consumed_windows:
        return (
            "INSUFFICIENT_EVIDENCE_NO_UNUSED_INDEPENDENT_WINDOW",
            "INSUFFICIENT_EVIDENCE",
            [
                "consumed_oos_windows_visible_without_unused_independent_successor",
                "independence_not_visible",
            ],
            "identify_new_preregistered_independent_window_before_repetition",
        )
    return (
        "READY_FOR_INDEPENDENT_OOS",
        "ACCEPTED",
        [],
        "run_independent_preregistered_oos_window",
    )


def _build_row(
    *,
    registry_row: dict[str, Any],
    operator_row: dict[str, Any],
    lineage_row: dict[str, Any],
    replay: dict[str, Any],
    run: dict[str, Any],
    closure: dict[str, Any],
) -> dict[str, Any]:
    source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
    applies_run = _text(_mapping(run.get("campaign_scope")).get("hypothesis_id")) == source_hypothesis_id
    consumed_windows = _consumed_windows(run) if applies_run else []
    row_status, decision, blocker_reasons, next_action = _row_status(
        operator_row=operator_row,
        lineage_row=lineage_row,
        replay=replay,
        consumed_windows=consumed_windows,
    )
    operator_oos = _mapping(operator_row.get("oos"))
    contradiction_state = _text(_mapping(operator_row.get("contradictions")).get("decay_contradiction_state")) or "not_visible"
    lineage_nodes = _mapping(lineage_row.get("graph_nodes"))
    null_controls = _mapping(operator_row.get("null_controls"))
    closure_status = _text(closure.get("closure_status")) if applies_run else ""
    closure_disposition = _text(closure.get("hypothesis_disposition")) if applies_run else ""

    contradiction_update = {
        "status": "unchanged_context_only",
        "current_contradiction_state": contradiction_state,
        "supports_new_independent_oos": False,
    }
    operator_report_update = {
        "status": "no_authoritative_change_materialized",
        "current_decision": _text(operator_row.get("final_decision")) or "not_visible",
        "current_next_action": _text(operator_row.get("next_action")) or next_action,
        "independence_visible": bool(operator_oos.get("independence_visible")),
    }
    lineage_update = {
        "status": "lineage_preserved_without_new_independent_window",
        "lineage_complete": bool(lineage_row.get("lineage_complete")),
        "campaign_ids": _normalize_str_list(lineage_nodes.get("campaign")),
        "data_snapshot_ids": _normalize_str_list(lineage_nodes.get("data_snapshot")),
        "source_ids": _normalize_str_list(lineage_nodes.get("source")),
        "missing_lineage_fields": _normalize_str_list(lineage_row.get("missing_lineage_fields")),
    }

    provenance_refs = _normalize_str_list(
        [*list(registry_row.get("provenance_refs") or [])]
        + [*list(operator_row.get("provenance_refs") or [])]
        + [*list(lineage_row.get("provenance_refs") or [])]
        + [_rel(DEFAULT_REPLAY_PATH)]
        + ([_rel(DEFAULT_RUN_PATH), _rel(DEFAULT_CLOSURE_PATH)] if applies_run else [])
    )

    return {
        "thesis_id": _text(registry_row.get("thesis_id")),
        "source_hypothesis_id": source_hypothesis_id,
        "title": _text(registry_row.get("title")),
        "behavior_family": _text(registry_row.get("behavior_family")),
        "strategy_family": _text(registry_row.get("strategy_family")),
        "registry_status": _text(registry_row.get("status")) or "not_visible",
        "operator_decision": _text(operator_row.get("final_decision")) or "not_visible",
        "independent_oos_status": row_status,
        "independent_oos_decision": decision,
        "relevant_for_independent_oos": row_status != "BLOCKED_MISSING_CAMPAIGN_LINEAGE",
        "consumed_oos_windows": consumed_windows,
        "consumed_window_count": len(consumed_windows),
        "oos_evidence": {
            "accepted_oos_count": operator_oos.get("accepted_oos_count"),
            "accepted_window_count": operator_oos.get("accepted_window_count"),
            "closure_status": _text(operator_oos.get("closure_status")),
            "independence_visible": bool(operator_oos.get("independence_visible")),
            "positive_oos_trade_count_total": operator_oos.get("positive_oos_trade_count_total"),
        },
        "null_control_linkage": {
            "status": _text(null_controls.get("status")) or "null_controls_not_visible",
            "missing_control_ids": _normalize_str_list(null_controls.get("missing_control_ids")),
            "recommended_next_action": _text(null_controls.get("recommended_next_action")),
        },
        "independent_window_assessment": {
            "unused_independent_window_visible": False,
            "independence_proven": False,
            "window_identity_visible": False,
            "blocker_reasons": [
                *blocker_reasons,
                *(
                    ["null_controls_incomplete"]
                    if applies_run and _text(null_controls.get("status")) == "controls_incomplete"
                    else []
                ),
            ],
            "closure_hypothesis_disposition": closure_disposition,
            "closure_status": closure_status,
        },
        "contradiction_update": contradiction_update,
        "operator_report_update": operator_report_update,
        "lineage_update": lineage_update,
        "next_action": next_action,
        "provenance_refs": provenance_refs,
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    lines = [
        "# QRE Repeated Independent OOS",
        "",
        f"- independent_oos_identity: `{_text(snapshot.get('independent_oos_identity')) or 'not_materialized'}`",
        f"- decision: `{_text(snapshot.get('decision')) or 'not_visible'}`",
        f"- final_recommendation: `{_text(summary.get('final_recommendation')) or 'not_visible'}`",
        f"- supported_for_review_count: `{summary.get('supported_for_review_count', 0)}`",
        f"- relevant_hypothesis_count: `{summary.get('relevant_hypothesis_count', 0)}`",
        f"- independent_ready_count: `{summary.get('independent_ready_count', 0)}`",
        "",
        "## Row Summary",
        "",
    ]
    for row in snapshot.get("rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{_text(row.get('source_hypothesis_id'))}`: `{_text(row.get('independent_oos_status'))}` -> `{_text(row.get('next_action'))}`"
        )
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    registry_path: Path | None = None,
    operator_path: Path | None = None,
    lineage_path: Path | None = None,
    replay_path: Path | None = None,
    run_path: Path | None = None,
    closure_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    registry_source = registry_path or DEFAULT_REGISTRY_PATH
    operator_source = operator_path or DEFAULT_OPERATOR_PATH
    lineage_source = lineage_path or DEFAULT_LINEAGE_PATH
    replay_source = replay_path or DEFAULT_REPLAY_PATH
    run_source = run_path or DEFAULT_RUN_PATH
    closure_source = closure_path or DEFAULT_CLOSURE_PATH
    generated = generated_at_utc or _utcnow()

    registry = _read_json(registry_source) or {}
    operator = _read_json(operator_source) or {}
    lineage = _read_json(lineage_source) or {}
    replay = _read_json(replay_source) or {}
    run = _read_json(run_source) or {}
    closure = _read_json(closure_source) or {}

    operator_by_hypothesis = _index_by(_rows(operator, "rows"), "source_hypothesis_id")
    lineage_by_hypothesis = _index_by(_rows(lineage, "rows"), "source_hypothesis_id")

    rows = [
        _build_row(
            registry_row=registry_row,
            operator_row=operator_by_hypothesis.get(_text(registry_row.get("source_hypothesis_id")), {}),
            lineage_row=lineage_by_hypothesis.get(_text(registry_row.get("source_hypothesis_id")), {}),
            replay=replay,
            run=run,
            closure=closure,
        )
        for registry_row in sorted(
            _rows(registry, "rows"),
            key=lambda row: (_text(row.get("thesis_id")), _text(row.get("source_hypothesis_id"))),
        )
    ]

    status_counts: dict[str, int] = {}
    decision_counts: dict[str, int] = {}
    for row in rows:
        status = _text(row.get("independent_oos_status"))
        decision = _text(row.get("independent_oos_decision"))
        status_counts[status] = status_counts.get(status, 0) + 1
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

    supported_for_review_count = int(_mapping(operator.get("summary")).get("decision_counts", {}).get("SUPPORTED_FOR_REVIEW") or 0)
    relevant_hypothesis_count = sum(1 for row in rows if bool(row.get("relevant_for_independent_oos")))
    independent_ready_count = status_counts.get("READY_FOR_INDEPENDENT_OOS", 0)
    consumed_window_count = sum(int(row.get("consumed_window_count") or 0) for row in rows)

    identity_seed = {
        "source_replay_identity": _text(replay.get("replay_assessment_identity")),
        "run_campaign_id": _text(_mapping(run.get("campaign_scope")).get("campaign_id")),
        "closure_status": _text(closure.get("closure_status")),
        "rows": [
            {
                "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
                "status": _text(row.get("independent_oos_status")),
                "decision": _text(row.get("independent_oos_decision")),
                "consumed_window_count": int(row.get("consumed_window_count") or 0),
            }
            for row in rows
        ],
    }

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "artifact_references": {
            "governance_doc": _rel(DOC_PATH),
            "qre_behavior_thesis_registry": _rel(registry_source),
            "qre_operator_decision_report": _rel(operator_source),
            "qre_contradiction_hypothesis_lineage": _rel(lineage_source),
            "qre_same_input_replay": _rel(replay_source),
            "qre_preregistered_multiwindow_evidence_run": _rel(run_source),
            "qre_multiwindow_evidence_closure": _rel(closure_source),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_launch_campaign": False,
            "can_authorize_execution": False,
            "can_generate_executable_strategy": False,
        },
        "safety_invariants": {
            "mutates_campaign_queue": False,
            "mutates_frozen_contracts": False,
            "mutates_strategy_or_preset": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "source_replay_identity": _text(replay.get("replay_assessment_identity")),
        "source_manifest_identity": _text(replay.get("source_manifest_identity")),
        "source_execution_identity": _text(replay.get("source_execution_identity")),
        "independent_oos_identity": "qrao_" + _stable_digest(identity_seed)[:16],
        "decision": "ACCEPTED" if independent_ready_count else "INSUFFICIENT_EVIDENCE",
        "next_action": (
            "run_independent_preregistered_oos_window"
            if independent_ready_count
            else "preserve_blocked_synthesis_until_new_authoritative_windows_exist"
        ),
        "summary": {
            "supported_for_review_count": supported_for_review_count,
            "relevant_hypothesis_count": relevant_hypothesis_count,
            "independent_ready_count": independent_ready_count,
            "consumed_window_count": consumed_window_count,
            "status_counts": dict(sorted(status_counts.items())),
            "decision_counts": dict(sorted(decision_counts.items())),
            "final_recommendation": (
                "independent_oos_ready_for_execution"
                if independent_ready_count
                else "no_valid_independent_oos_path_materialized"
            ),
            "blocked_reasons": [
                "zero_supported_for_review_hypotheses_visible",
                "replay_confirms_zero_executable_cells",
                "campaign_lineage_missing_for_blocked_theses",
                "trend_pullback_v1_consumed_two_oos_windows_without_acceptance",
                "null_controls_incomplete_for_only_campaign_with_oos_windows",
            ],
        },
        "rows": rows,
    }


def _atomic_write(path: Path, content: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    os.replace(temp_name, path)


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    _atomic_write(ARTIFACT_MARKDOWN, _render_markdown(snapshot))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize repeated independent OOS evidence.")
    parser.add_argument("--write", action="store_true", help="Persist the latest JSON and Markdown artifacts.")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot()
    if args.write:
        write_outputs(snapshot)
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
