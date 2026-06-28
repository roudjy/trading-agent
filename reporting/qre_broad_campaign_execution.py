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
REPORT_KIND: Final[str] = "qre_broad_campaign_execution"
MODULE_VERSION: Final[str] = "ade-qre-017y-2026-06-28"

DEFAULT_MANIFEST_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_campaign_manifest" / "latest.json"
DEFAULT_MULTIWINDOW_RUN_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json"
DEFAULT_CLOSURE_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_multiwindow_evidence_closure" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_execution"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_broad_campaign_execution.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_broad_campaign_execution/",
    "docs/governance/qre_broad_campaign_execution.md",
)
EXECUTION_STATUSES: Final[tuple[str, ...]] = (
    "completed",
    "rejected",
    "insufficient_evidence",
    "blocked",
    "timed_out",
    "errored",
    "not_executed",
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


def _artifact_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_text(row.get("source_hypothesis_id")), _text(row.get("preset_name")))


def _manifest_key_from_scope(scope: dict[str, Any]) -> tuple[str, str]:
    return (_text(scope.get("hypothesis_id")), _text(scope.get("preset_name")))


def _index_optional_artifact(payload: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not payload:
        return {}
    scope = _mapping(payload.get("campaign_scope"))
    key = _manifest_key_from_scope(scope)
    if not key[0] and not key[1]:
        return {}
    return {key: payload}


def _stage_outcomes(*, run_row: dict[str, Any] | None, closure_row: dict[str, Any] | None) -> dict[str, Any]:
    run = run_row or {}
    closure = closure_row or {}
    null_controls = _mapping(run.get("null_control_results"))
    closure_status = _text(closure.get("closure_status")) or _text(run.get("campaign_outcome"))
    return {
        "screening": {
            "status": "not_materialized",
            "reason": "screening_stage_artifact_not_separately_materialized_in_campaign_execution_report",
        },
        "validation": {
            "status": "not_materialized",
            "reason": "validation_stage_artifact_not_separately_materialized_in_campaign_execution_report",
        },
        "oos": {
            "status": closure_status or "not_materialized",
            "accepted_oos_count": run.get("accepted_oos_count"),
            "positive_oos_trade_count_total": run.get("positive_oos_trade_count_total"),
        },
        "null_controls": {
            "status": _text(null_controls.get("status")) or "not_materialized",
            "missing_control_ids": _normalize_str_list(null_controls.get("missing_control_ids")),
            "recommended_next_action": _text(null_controls.get("recommended_next_action")),
        },
        "reproducibility": {
            "status": (
                "campaign_artifact_materialized"
                if run_row or closure_row
                else "not_materialized"
            ),
            "run_hash": _text(run.get("hash")),
            "closure_hash": _text(closure.get("hash")),
        },
        "lineage": {
            "status": (
                "lineage_visible"
                if bool(run.get("accepted_lineage_count") or closure.get("accepted_lineage_count"))
                else "lineage_not_materialized"
            ),
            "accepted_lineage_count": run.get("accepted_lineage_count") or closure.get("accepted_lineage_count"),
        },
    }


def _execution_status_for_appendix(row: dict[str, Any]) -> tuple[str, list[str]]:
    inclusion_status = _text(row.get("inclusion_status"))
    operator_decision = _text(row.get("operator_decision"))
    blockers = _normalize_str_list(row.get("blocker_reasons"))
    if operator_decision == "REJECTED":
        return ("rejected", blockers or ["operator_report_rejected_thesis"])
    if inclusion_status == "INSUFFICIENT_EVIDENCE":
        return ("insufficient_evidence", blockers or ["portfolio_cell_insufficient_evidence"])
    if inclusion_status in {"EXCLUDED_DEAD_ZONE", "EXCLUDED_DUPLICATE"}:
        default_reason = "excluded_dead_zone" if inclusion_status == "EXCLUDED_DEAD_ZONE" else "excluded_duplicate"
        return ("not_executed", blockers or [default_reason])
    return ("blocked", blockers or ["portfolio_cell_blocked"])


def _execution_status_for_executable(
    row: dict[str, Any],
    *,
    run_row: dict[str, Any] | None,
    closure_row: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    closure = closure_row or {}
    run = run_row or {}
    if not run_row and not closure_row:
        return ("not_executed", ["execution_artifact_missing_for_executable_cell"])
    timeout_status = _text(_mapping(row.get("timeout_risk")).get("status"))
    if "timeout" in timeout_status:
        return ("timed_out", [timeout_status])
    closure_status = _text(closure.get("closure_status")) or _text(run.get("campaign_outcome"))
    if closure_status in {"errored", "error"}:
        return ("errored", [closure_status])
    if _text(closure.get("hypothesis_disposition")) == "fail_closed_rejected":
        return ("rejected", _normalize_str_list(closure.get("blockers_remaining")) or ["fail_closed_rejected"])
    if bool(run.get("accepted_oos_count")) or bool(closure.get("evidence_complete_count")):
        return ("completed", ["accepted_oos_visible"])
    return ("blocked", _normalize_str_list(closure.get("blockers_remaining")) or ["campaign_completed_without_accepted_oos"])


def _row_identity(payload: dict[str, Any]) -> str:
    seed = {
        "cell_id": _text(payload.get("cell_id")),
        "status": _text(payload.get("execution_status")),
        "manifest_identity": _text(payload.get("manifest_identity")),
    }
    return "qce_" + _stable_digest(seed)[:16]


def _build_row(
    row: dict[str, Any],
    *,
    manifest_identity: str,
    replay_identity: str,
    source_kind: str,
    run_row: dict[str, Any] | None,
    closure_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if source_kind == "executable":
        execution_status, reasons = _execution_status_for_executable(row, run_row=run_row, closure_row=closure_row)
    else:
        execution_status, reasons = _execution_status_for_appendix(row)
    payload = {
        "cell_id": _text(row.get("cell_id")),
        "thesis_id": _text(row.get("thesis_id")),
        "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
        "preset_name": _text(row.get("preset_name")),
        "title": _text(row.get("title")),
        "manifest_identity": manifest_identity,
        "replay_identity": replay_identity,
        "source_kind": source_kind,
        "manifest_inclusion_status": _text(row.get("inclusion_status")) or ("READY_FOR_PREREGISTRATION" if source_kind == "executable" else ""),
        "operator_decision": _text(row.get("operator_decision")),
        "execution_status": execution_status,
        "status_reasons": reasons,
        "next_action": _text(row.get("next_action")),
        "campaign_scope": {
            "proposed_universe": row.get("proposed_universe"),
            "proposed_assets_or_basket": row.get("proposed_assets_or_basket"),
            "proposed_timeframe": _text(row.get("proposed_timeframe")),
            "proposed_regime_coverage": row.get("proposed_regime_coverage"),
        },
        "campaign_inputs": {
            "cell_manifest_identity": _text(row.get("cell_manifest_identity")),
            "available_train_window": _mapping(row.get("available_train_window")),
            "available_validation_window": _mapping(row.get("available_validation_window")),
            "available_oos_window": _mapping(row.get("available_oos_window")),
            "cost_and_slippage_readiness": _mapping(row.get("cost_and_slippage_readiness")),
            "null_control_feasibility": _mapping(row.get("null_control_feasibility")),
        },
        "stage_outcomes": _stage_outcomes(run_row=run_row, closure_row=closure_row),
        "compute_accounting": {
            "estimated_runtime_seconds_default": _mapping(row.get("compute_estimate")).get("estimated_runtime_seconds_default"),
            "actual_runtime_seconds": None,
            "status": "not_materialized",
        },
        "timeout_accounting": {
            "status": _text(_mapping(row.get("timeout_risk")).get("status")) or "not_materialized",
        },
        "historical_campaign_evidence": {
            "visible": bool(run_row or closure_row),
            "run_ref": DEFAULT_MULTIWINDOW_RUN_PATH.as_posix() if run_row else "",
            "closure_ref": DEFAULT_CLOSURE_PATH.as_posix() if closure_row else "",
            "campaign_id": _text(_mapping((run_row or closure_row or {}).get("campaign_scope")).get("campaign_id")),
            "proposal_id": _text((run_row or closure_row or {}).get("proposal_id")),
        },
        "provenance_refs": _normalize_str_list(row.get("provenance_refs"))
        + ([DEFAULT_MULTIWINDOW_RUN_PATH.as_posix()] if run_row else [])
        + ([DEFAULT_CLOSURE_PATH.as_posix()] if closure_row else []),
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_authorize_execution": False,
            "can_launch_campaign": False,
            "can_generate_executable_strategy": False,
            "can_promote_candidate": False,
        },
    }
    payload["execution_row_id"] = _row_identity(payload)
    return payload


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    counts = _mapping(summary.get("status_counts"))
    lines = [
        "# QRE Broad Campaign Execution",
        "",
        f"- campaign_execution_identity: `{_text(snapshot.get('campaign_execution_identity')) or 'not_materialized'}`",
        f"- manifest_identity: `{_text(snapshot.get('manifest_identity')) or 'not_visible'}`",
        f"- replay_identity: `{_text(snapshot.get('replay_identity')) or 'not_visible'}`",
        f"- executable_cell_count: {int(summary.get('executable_cell_count') or 0)}",
        f"- accounted_cell_count: {int(summary.get('accounted_cell_count') or 0)}",
        f"- final_recommendation: `{_text(summary.get('final_recommendation')) or 'not_visible'}`",
        "",
        "## Status Counts",
        "",
    ]
    for status in EXECUTION_STATUSES:
        lines.append(f"- {status}: {int(counts.get(status) or 0)}")
    lines.extend(["", "## Accounted Cells", ""])
    for row in _list_of_mappings(snapshot.get("rows")):
        lines.append(
            f"- `{_text(row.get('cell_id'))}` / `{_text(row.get('preset_name')) or 'thesis_only_gap'}` / `{_text(row.get('execution_status'))}`"
        )
    if not _list_of_mappings(snapshot.get("rows")):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    manifest_path: Path | None = None,
    run_artifact_path: Path | None = None,
    closure_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    manifest_source = manifest_path or DEFAULT_MANIFEST_PATH
    run_source = run_artifact_path or DEFAULT_MULTIWINDOW_RUN_PATH
    closure_source = closure_artifact_path or DEFAULT_CLOSURE_PATH
    generated = generated_at_utc or _utcnow()

    manifest = _read_json(manifest_source) or {}
    executable_cells = _list_of_mappings(manifest.get("executable_cells"))
    blocked_appendix = _list_of_mappings(manifest.get("blocked_appendix"))
    manifest_identity = _text(manifest.get("manifest_identity"))
    replay_identity = _text(manifest.get("replay_identity"))

    run_by_key = _index_optional_artifact(_read_json(run_source))
    closure_by_key = _index_optional_artifact(_read_json(closure_source))

    rows: list[dict[str, Any]] = []
    for row in executable_cells:
        key = _artifact_key(row)
        rows.append(
            _build_row(
                row,
                manifest_identity=manifest_identity,
                replay_identity=replay_identity,
                source_kind="executable",
                run_row=run_by_key.get(key),
                closure_row=closure_by_key.get(key),
            )
        )
    for row in blocked_appendix:
        key = _artifact_key(row)
        rows.append(
            _build_row(
                row,
                manifest_identity=manifest_identity,
                replay_identity=replay_identity,
                source_kind="blocked_appendix",
                run_row=run_by_key.get(key),
                closure_row=closure_by_key.get(key),
            )
        )

    rows.sort(key=lambda item: (_text(item.get("execution_status")), _text(item.get("cell_id"))))
    status_counts = {status: 0 for status in EXECUTION_STATUSES}
    for row in rows:
        status = _text(row.get("execution_status"))
        if status in status_counts:
            status_counts[status] += 1

    blocked_reasons = []
    final_recommendation = "broad_campaign_execution_accounting_ready"
    if not executable_cells:
        blocked_reasons.append("no_executable_cells_visible_in_preregistered_manifest")
        final_recommendation = "broad_campaign_execution_fail_closed_no_executable_cells"
    elif any(_text(row.get("execution_status")) == "not_executed" for row in rows if _text(row.get("source_kind")) == "executable"):
        blocked_reasons.append("executable_cell_missing_campaign_execution_artifact")
        final_recommendation = "broad_campaign_execution_incomplete_missing_execution_artifacts"

    identity_payload = {
        "manifest_identity": manifest_identity,
        "replay_identity": replay_identity,
        "row_ids": [row["execution_row_id"] for row in rows],
        "status_counts": status_counts,
    }
    campaign_execution_identity = "qcy_" + _stable_digest(identity_payload)[:16]

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "manifest_identity": manifest_identity,
        "replay_identity": replay_identity,
        "campaign_execution_identity": campaign_execution_identity,
        "source_manifest_path": _rel(manifest_source),
        "rows": rows,
        "artifact_references": {
            "qre_preregistered_campaign_manifest": _rel(manifest_source),
            "qre_preregistered_multiwindow_evidence_run": _rel(run_source),
            "qre_multiwindow_evidence_closure": _rel(closure_source),
            "governance_doc": _rel(DOC_PATH),
        },
        "summary": {
            "executable_cell_count": len(executable_cells),
            "blocked_appendix_count": len(blocked_appendix),
            "accounted_cell_count": len(rows),
            "status_counts": status_counts,
            "historical_evidence_match_count": sum(
                1 for row in rows if bool(_mapping(row.get("historical_campaign_evidence")).get("visible"))
            ),
            "final_recommendation": final_recommendation,
            "blocker_reasons": blocked_reasons,
        },
        "safety_invariants": {
            "read_only": True,
            "context_only": True,
            "mutates_campaign_queue": False,
            "mutates_strategy_or_preset": False,
            "mutates_frozen_contracts": False,
            "can_launch_campaign": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _atomic_write(path: Path, text: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_broad_campaign_execution.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(
    snapshot: dict[str, Any],
    *,
    json_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, str]:
    target_json = json_path or ARTIFACT_LATEST
    target_markdown = markdown_path or ARTIFACT_MARKDOWN
    _atomic_write(target_json, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    _atomic_write(target_markdown, _render_markdown(snapshot))
    return {
        "latest": _rel(target_json),
        "operator_summary": _rel(target_markdown),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_broad_campaign_execution",
        description="Build deterministic broad campaign accounting from the preregistered manifest.",
    )
    parser.add_argument("--source", default=_rel(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--run-artifact", default=_rel(DEFAULT_MULTIWINDOW_RUN_PATH))
    parser.add_argument("--closure-artifact", default=_rel(DEFAULT_CLOSURE_PATH))
    parser.add_argument("--frozen-utc", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot(
        manifest_path=REPO_ROOT / args.source,
        run_artifact_path=REPO_ROOT / args.run_artifact,
        closure_artifact_path=REPO_ROOT / args.closure_artifact,
        generated_at_utc=_text(args.frozen_utc) or None,
    )
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
