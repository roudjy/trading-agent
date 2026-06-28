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
REPORT_KIND: Final[str] = "qre_preregistered_campaign_manifest"
MODULE_VERSION: Final[str] = "ade-qre-017x-2026-06-28"

DEFAULT_PORTFOLIO_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_campaign_portfolio_plan" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_campaign_manifest"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_preregistered_campaign_manifest.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_preregistered_campaign_manifest/",
    "docs/governance/qre_preregistered_campaign_manifest.md",
)
READY_STATUSES: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "READY_WITH_LIMITATIONS",
)
BLOCKED_APPENDIX_STATUSES: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "READY_WITH_LIMITATIONS",
    "BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "EXCLUDED_DUPLICATE",
    "EXCLUDED_DEAD_ZONE",
)
FINAL_DECISION_VOCAB: Final[tuple[str, ...]] = (
    "SUPPORTED_FOR_REVIEW",
    "REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
)
NEXT_ACTION_VOCAB: Final[tuple[str, ...]] = (
    "advance_to_broad_campaign_execution",
    "collect_missing_identity_evidence",
    "collect_missing_window_evidence",
    "collect_missing_null_controls",
    "establish_campaign_lineage_for_thesis",
    "preserve_suppressed_scope_boundary",
    "reject_hypothesis",
)
MISSING_STATUSES: Final[set[str]] = {
    "",
    "missing",
    "not_materialized",
    "not_scoped_to_preset",
    "insufficient_evidence",
    "needs_materialization",
    "unsupported",
}


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
        raise ValueError(f"qre_preregistered_campaign_manifest: refusing write outside allowlist: {path!r}")


def _status(row: dict[str, Any], field: str) -> str:
    return _text(_mapping(row.get(field)).get("status"))


def _has_assets(row: dict[str, Any]) -> bool:
    return bool(_normalize_str_list(row.get("proposed_assets_or_basket")))


def _has_visible_window(window_payload: dict[str, Any]) -> bool:
    status = _text(window_payload.get("status"))
    if status in MISSING_STATUSES:
        return False
    return bool(_text(window_payload.get("min_timestamp_utc")) or _text(window_payload.get("max_timestamp_utc")) or status)


def _materialization_blockers(row: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not _text(row.get("preset_name")):
        blockers.append("missing_preset_identity")
    if not _has_assets(row):
        blockers.append("missing_assets_or_basket")
    if not _text(row.get("proposed_timeframe")):
        blockers.append("missing_timeframe")
    if _status(row, "source_readiness") != "ready":
        blockers.append("source_readiness_unresolved")
    if _status(row, "data_readiness") != "ready":
        blockers.append("data_readiness_unresolved")
    if _status(row, "identity_readiness") != "ready":
        blockers.append("identity_readiness_unresolved")
    if not _has_visible_window(_mapping(row.get("available_train_window"))):
        blockers.append("train_window_unavailable")
    if not _has_visible_window(_mapping(row.get("available_validation_window"))):
        blockers.append("validation_window_unavailable")
    if not _has_visible_window(_mapping(row.get("available_oos_window"))):
        blockers.append("oos_window_unavailable")
    if _status(row, "null_control_feasibility") in MISSING_STATUSES:
        blockers.append("null_controls_incomplete")
    cost_payload = _mapping(row.get("cost_and_slippage_readiness"))
    if not _text(cost_payload.get("cost_mode")) or bool(cost_payload.get("slippage_visible")) is not True:
        blockers.append("cost_slippage_unproven")
    minimum_sample = _mapping(row.get("minimum_sample"))
    if _text(minimum_sample.get("status")) in MISSING_STATUSES or minimum_sample.get("value") in (None, ""):
        blockers.append("minimum_sample_unproven")
    expected_trade_count = _mapping(row.get("expected_trade_count"))
    if _text(expected_trade_count.get("status")) in MISSING_STATUSES or expected_trade_count.get("value") in (None, ""):
        blockers.append("expected_trade_count_unproven")
    return blockers


def _frozen_cell(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "cell_id": _text(row.get("cell_id")),
        "thesis_id": _text(row.get("thesis_id")),
        "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
        "title": _text(row.get("title")),
        "behavior_family": _text(row.get("behavior_family")),
        "mechanism": _text(row.get("mechanism")),
        "preset_name": _text(row.get("preset_name")),
        "proposed_universe": row.get("proposed_universe"),
        "proposed_assets_or_basket": _normalize_str_list(row.get("proposed_assets_or_basket")),
        "proposed_timeframe": _text(row.get("proposed_timeframe")),
        "proposed_regime_coverage": row.get("proposed_regime_coverage"),
        "source_readiness": _mapping(row.get("source_readiness")),
        "data_readiness": _mapping(row.get("data_readiness")),
        "identity_readiness": _mapping(row.get("identity_readiness")),
        "available_train_window": _mapping(row.get("available_train_window")),
        "available_validation_window": _mapping(row.get("available_validation_window")),
        "available_oos_window": _mapping(row.get("available_oos_window")),
        "null_control_feasibility": _mapping(row.get("null_control_feasibility")),
        "cost_and_slippage_readiness": _mapping(row.get("cost_and_slippage_readiness")),
        "minimum_sample": _mapping(row.get("minimum_sample")),
        "expected_trade_count": _mapping(row.get("expected_trade_count")),
        "compute_estimate": _mapping(row.get("compute_estimate")),
        "timeout_risk": _mapping(row.get("timeout_risk")),
        "next_action": _text(row.get("next_action")),
        "operator_decision": _text(row.get("operator_decision")),
        "provenance_refs": _normalize_str_list(row.get("provenance_refs")),
    }
    payload["cell_manifest_identity"] = "qcmc_" + _stable_digest(payload)[:16]
    return payload


def _blocked_appendix_row(row: dict[str, Any]) -> dict[str, Any]:
    appendix = {
        "cell_id": _text(row.get("cell_id")),
        "thesis_id": _text(row.get("thesis_id")),
        "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
        "preset_name": _text(row.get("preset_name")),
        "title": _text(row.get("title")),
        "inclusion_status": _text(row.get("inclusion_status")),
        "operator_decision": _text(row.get("operator_decision")),
        "next_action": _text(row.get("next_action")),
        "blocker_reasons": _normalize_str_list(row.get("blocker_reasons")),
        "available_oos_window": _mapping(row.get("available_oos_window")),
        "null_control_feasibility": _mapping(row.get("null_control_feasibility")),
        "cost_and_slippage_readiness": _mapping(row.get("cost_and_slippage_readiness")),
        "provenance_refs": _normalize_str_list(row.get("provenance_refs")),
    }
    return appendix


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    lines = [
        "# QRE Preregistered Campaign Manifest",
        "",
        f"- manifest_identity: `{_text(snapshot.get('manifest_identity')) or 'not_materialized'}`",
        f"- replay_identity: `{_text(snapshot.get('replay_identity')) or 'not_materialized'}`",
        f"- source_portfolio_identity: `{_text(snapshot.get('source_portfolio_identity')) or 'not_visible'}`",
        f"- executable_cell_count: {int(summary.get('executable_cell_count') or 0)}",
        f"- blocked_appendix_count: {int(summary.get('blocked_appendix_count') or 0)}",
        f"- final_recommendation: `{_text(summary.get('final_recommendation')) or 'not_visible'}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = _normalize_str_list(summary.get("blocker_reasons"))
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    lines.extend(["", "## Executable Cells", ""])
    executable_cells = _list_of_mappings(snapshot.get("executable_cells"))
    if executable_cells:
        for row in executable_cells:
            lines.append(
                f"- `{_text(row.get('cell_id'))}` / `{_text(row.get('preset_name'))}` / `{_text(row.get('proposed_timeframe'))}`"
            )
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    portfolio_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source = portfolio_path or DEFAULT_PORTFOLIO_PATH
    generated = generated_at_utc or _utcnow()
    portfolio = _read_json(source)
    rows = _list_of_mappings((portfolio or {}).get("rows"))
    source_portfolio_identity = _text((portfolio or {}).get("portfolio_identity"))
    blocked_appendix: list[dict[str, Any]] = []
    executable_cells: list[dict[str, Any]] = []

    for row in rows:
        inclusion_status = _text(row.get("inclusion_status"))
        if inclusion_status not in BLOCKED_APPENDIX_STATUSES:
            continue
        if inclusion_status in READY_STATUSES:
            blockers = _materialization_blockers(row)
            if not blockers:
                executable_cells.append(_frozen_cell(row))
                continue
            row = dict(row)
            row["inclusion_status"] = "BLOCKED"
            row["blocker_reasons"] = _normalize_str_list(row.get("blocker_reasons")) + blockers
        blocked_appendix.append(_blocked_appendix_row(row))

    executable_cells.sort(key=lambda item: item["cell_manifest_identity"])
    blocked_appendix.sort(key=lambda item: (item["inclusion_status"], item["cell_id"]))

    manifest_payload = {
        "source_portfolio_identity": source_portfolio_identity,
        "executable_cells": executable_cells,
        "frozen_vocabulary": {
            "final_decisions": list(FINAL_DECISION_VOCAB),
            "next_actions": list(NEXT_ACTION_VOCAB),
            "portfolio_inclusion_statuses": list(BLOCKED_APPENDIX_STATUSES),
        },
    }
    manifest_identity = "qcm_" + _stable_digest(manifest_payload)[:16]
    replay_identity = "qcr_" + _stable_digest(
        {
            "manifest_identity": manifest_identity,
            "cell_manifest_identities": [row["cell_manifest_identity"] for row in executable_cells],
        }
    )[:16]

    final_recommendation = (
        "preregistered_campaign_manifest_ready"
        if executable_cells
        else "no_executable_cells_available_for_preregistration"
    )
    blocker_reasons = [] if executable_cells else ["no_executable_cells_visible_in_portfolio_plan"]
    status_counts: dict[str, int] = {}
    for row in blocked_appendix:
        key = _text(row.get("inclusion_status")) or "unknown"
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "source_portfolio_path": _rel(source),
        "source_portfolio_identity": source_portfolio_identity,
        "manifest_identity": manifest_identity,
        "replay_identity": replay_identity,
        "executable_cells": executable_cells,
        "blocked_appendix": blocked_appendix,
        "frozen_vocabulary": {
            "final_decisions": list(FINAL_DECISION_VOCAB),
            "next_actions": list(NEXT_ACTION_VOCAB),
            "portfolio_inclusion_statuses": list(BLOCKED_APPENDIX_STATUSES),
        },
        "artifact_references": {
            "qre_campaign_portfolio_plan": _rel(source),
            "governance_doc": _rel(DOC_PATH),
        },
        "summary": {
            "source_row_count": len(rows),
            "executable_cell_count": len(executable_cells),
            "blocked_appendix_count": len(blocked_appendix),
            "blocked_appendix_status_counts": status_counts,
            "final_recommendation": final_recommendation,
            "execution_readiness": (
                "ready_for_broad_campaign_execution" if executable_cells else "blocked_no_executable_cells"
            ),
            "blocker_reasons": blocker_reasons,
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
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_preregistered_campaign_manifest.", suffix=".tmp", dir=str(path.parent))
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
        prog="python -m reporting.qre_preregistered_campaign_manifest",
        description="Build a deterministic preregistered campaign manifest from the 017W portfolio artifact.",
    )
    parser.add_argument("--source", default=_rel(DEFAULT_PORTFOLIO_PATH))
    parser.add_argument("--frozen-utc", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot(
        portfolio_path=REPO_ROOT / args.source,
        generated_at_utc=_text(args.frozen_utc) or None,
    )
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
