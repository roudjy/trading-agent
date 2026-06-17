from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_basket_evidence_recovery_plan as recovery_plan
from research import qre_basket_lineage_recovery_diagnostics as lineage_diag


REPORT_KIND: Final[str] = "qre_basket_next_action_queue"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_basket_next_action_queue")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_basket_next_action_queue/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _guarded_alias_bounded_generation_snapshot(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(
        repo_root / "logs" / "qre_guarded_alias_bounded_generation_cascade" / "latest.json"
    )
    if isinstance(payload, dict) and str(payload.get("report_kind") or "") == "qre_guarded_alias_bounded_generation_cascade":
        return payload
    return {"overall_result": "guarded_alias_bounded_generation_cascade_unavailable"}


def _generation_command_discovery_snapshot(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(
        repo_root / "logs" / "qre_bounded_aapl_nvda_current_basket_generation_discovery" / "latest.json"
    )
    if isinstance(payload, dict) and str(payload.get("report_kind") or "") == "qre_bounded_aapl_nvda_current_basket_generation_discovery":
        return payload
    return {
        "report_kind": "qre_bounded_aapl_nvda_current_basket_generation_discovery_unavailable",
        "summary": {
            "final_recommendation": "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND",
            "safe_bounded_generation_command_found": False,
        },
    }


def _candidate_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _blocker_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("blocker_rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _priority_bucket(row: Mapping[str, Any]) -> str:
    if bool(row.get("blocked_by_identity")):
        return "identity_first"
    if bool(row.get("blocked_by_lineage")) and int(row.get("candidate_score") or 0) >= 80:
        return "lineage_first"
    if bool(row.get("blocked_by_source_cache")):
        return "source_cache_first"
    if bool(row.get("blocked_by_screening")):
        return "screening_second"
    if bool(row.get("blocked_by_oos")):
        return "oos_second"
    if bool(row.get("blocked_by_lineage")):
        return "lineage_followup"
    return "operator_review"


def _priority_rank(row: Mapping[str, Any]) -> int:
    bucket = _priority_bucket(row)
    return {
        "identity_first": 0,
        "lineage_first": 1,
        "source_cache_first": 2,
        "screening_second": 3,
        "oos_second": 4,
        "lineage_followup": 5,
        "operator_review": 6,
    }.get(bucket, 99)


def _recommended_batch(row: Mapping[str, Any]) -> str:
    if bool(row.get("blocked_by_identity")):
        return "batch_identity_review"
    if bool(row.get("blocked_by_lineage")) and int(row.get("candidate_score") or 0) >= 80:
        return "batch_lineage_oos"
    if bool(row.get("blocked_by_source_cache")):
        return "batch_source_cache_expansion"
    if bool(row.get("blocked_by_screening")) or bool(row.get("blocked_by_oos")):
        return "batch_screening_oos_collection"
    if bool(row.get("blocked_by_lineage")):
        return "batch_lineage_repair"
    return "batch_operator_review"


def _safe_command_template(row: Mapping[str, Any]) -> str:
    if bool(row.get("blocked_by_identity")):
        return "python -m research.qre_discovery_source_identity_diagnostics --write"
    if bool(row.get("blocked_by_lineage")):
        return "python -m research.qre_basket_lineage_recovery_diagnostics --write"
    if bool(row.get("blocked_by_source_cache")):
        return "python -m research.qre_basket_evidence_density_materialization --write"
    if bool(row.get("blocked_by_screening")) or bool(row.get("blocked_by_oos")):
        return "python -m research.qre_evidence_complete_basket_closure --write"
    return "python -m research.qre_basket_next_action_queue --write"


def build_basket_next_action_queue(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    report = recovery_plan.build_basket_evidence_recovery_plan(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    lineage_report = lineage_diag.build_basket_lineage_recovery_diagnostics(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    candidate_rows = {
        str(row.get("candidate_id") or ""): dict(row)
        for row in _candidate_rows(report)
    }
    blocker_rows = _blocker_rows(report)
    lineage_rows = {
        str(row.get("candidate_id") or ""): dict(row)
        for row in _candidate_rows(lineage_report)
    }
    guarded_report = _guarded_alias_bounded_generation_snapshot(repo_root)
    generation_discovery_report = _generation_command_discovery_snapshot(repo_root)
    generation_discovery_summary = (
        generation_discovery_report.get("summary") if isinstance(generation_discovery_report.get("summary"), Mapping) else {}
    )
    guarded_ready = str(guarded_report.get("overall_result") or "") == "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"
    generation_command_found = bool(generation_discovery_summary.get("safe_bounded_generation_command_found"))
    queue_rows: list[dict[str, Any]] = []
    for row in blocker_rows:
        lineage_row = lineage_rows.get(str(row.get("candidate_id") or ""), {})
        candidate_score = int(
            candidate_rows.get(str(row.get("candidate_id") or ""), {}).get(
                "evidence_completeness_score_pct",
                row.get("evidence_completeness_score_pct") or 0,
            )
            or 0
        )
        symbol = str(row.get("symbol") or "")
        exact_next_action = str(row.get("exact_next_action") or "")
        allowed_command_template = _safe_command_template({**row, "candidate_score": candidate_score})
        operator_explanation = str(row.get("operator_explanation") or "")
        if guarded_ready and symbol in {"AAPL", "NVDA"} and generation_command_found:
            exact_next_action = "operator_approve_bounded_aapl_nvda_current_basket_grid_generation"
            allowed_command_template = "python -m research.qre_bounded_first_batch_generation_decision --write"
            operator_explanation = (
                "Bounded current-basket generation decision packet is ready; "
                "operator approval is required before any generation run."
            )
        elif guarded_ready and symbol in {"AAPL", "NVDA"}:
            exact_next_action = "investigate_no_safe_bounded_command"
            allowed_command_template = "python -m research.qre_bounded_aapl_nvda_current_basket_generation_discovery --write"
            operator_explanation = (
                "No repo-local exact-scope bounded generation command can be proven safe and executable; "
                "stop for operator review."
            )
        queue_rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "symbol": symbol,
                "region": row.get("region"),
                "asset_class": row.get("asset_class"),
                "preset_id": row.get("preset_id"),
                "hypothesis_id": row.get("hypothesis_id"),
                "blocker_code": row.get("blocker_code"),
                "blocker_family": row.get("blocker_family"),
                "current_status": row.get("current_status"),
                "exact_next_action": exact_next_action,
                "required_artifact": row.get("required_artifact"),
                "safe_action_type": row.get("safe_action_type"),
                "allowed_to_auto_run": False,
                "blocked_by_identity": bool(row.get("blocked_by_identity")),
                "blocked_by_source_cache": bool(row.get("blocked_by_source_cache")),
                "blocked_by_lineage": bool(row.get("blocked_by_lineage")),
                "blocked_by_screening": bool(row.get("blocked_by_screening")),
                "blocked_by_oos": bool(row.get("blocked_by_oos")),
                "candidate_score": candidate_score,
                "lineage_proof_status": str(lineage_row.get("candidate_lineage_proof_status") or ""),
                "campaign_lineage_proof_status": str(lineage_row.get("campaign_lineage_proof_status") or ""),
                "generation_command_discovery_found": generation_command_found,
                "priority_bucket": _priority_bucket({**row, "candidate_score": candidate_score}),
                "priority_rank": _priority_rank({**row, "candidate_score": candidate_score}),
                "dependency_order": (
                    0
                    if bool(row.get("blocked_by_identity"))
                    else 1
                    if bool(row.get("blocked_by_lineage")) and candidate_score >= 80
                    else 2
                    if bool(row.get("blocked_by_source_cache"))
                    else 3
                    if bool(row.get("blocked_by_screening"))
                    else 4
                    if bool(row.get("blocked_by_oos"))
                    else 5
                ),
                "is_top_candidate": str(row.get("symbol") or "") in {"AAPL", "NVDA"},
                "blocks_evidence_complete": True,
                "recommended_batch": _recommended_batch({**row, "candidate_score": candidate_score}),
                "rationale": (
                    "identity before all else"
                    if bool(row.get("blocked_by_identity"))
                    else "lineage is the closest recoverable evidence chain"
                    if bool(row.get("blocked_by_lineage")) and candidate_score >= 80
                    else "source/cache coverage should precede deeper evidence collection"
                    if bool(row.get("blocked_by_source_cache"))
                    else "screening and OOS remain explicit evidence gaps"
                ),
                "allowed_command_template": allowed_command_template,
                "requires_operator_review": True,
                "evidence_refs": list(row.get("potential_clear_refs") or []),
                "reason_record_refs": dict(row.get("reason_record_refs") or {}),
                "operator_explanation": operator_explanation,
            }
        )
    queue_rows.sort(
        key=lambda row: (
            int(row.get("priority_rank") or 99),
            -int(row.get("candidate_score") or 0),
            int(row.get("dependency_order") or 99),
            str(row.get("symbol") or ""),
            str(row.get("preset_id") or ""),
            str(row.get("blocker_code") or ""),
        )
    )
    action_counts = Counter(str(row["exact_next_action"]) for row in queue_rows)
    blocker_counts = Counter(str(row["blocker_code"]) for row in queue_rows)
    priority_counts = Counter(str(row["priority_bucket"]) for row in queue_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "row_count": len(queue_rows),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "exact_next_action_counts": dict(sorted(action_counts.items())),
            "priority_bucket_counts": dict(sorted(priority_counts.items())),
            "top_candidate_symbols": list(
                dict.fromkeys(
                    str(row.get("symbol") or "")
                    for row in queue_rows
                    if bool(row.get("is_top_candidate"))
                )
            ),
            "operator_summary": (
                "Deterministic next-action queue enumerates every remaining basket blocker "
                "as a read-only operator review item with lineage-first priority ordering."
            ),
            "guarded_alias_bounded_generation_cascade_result": str(guarded_report.get("overall_result") or ""),
            "generation_command_discovery_result": str(generation_discovery_report.get("report_kind") or ""),
            "generation_command_discovery_safe_command_found": generation_command_found,
            "generation_command_discovery_final_recommendation": str(
                generation_discovery_summary.get("final_recommendation") or ""
            ),
            "final_recommendation": "basket_next_action_queue_ready" if queue_rows else "basket_next_action_queue_missing",
        },
        "rows": queue_rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
            "mutates_queues": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["rows", str(summary.get("row_count") or 0)],
            ["collect_screening_evidence", str(summary.get("exact_next_action_counts", {}).get("collect_screening_evidence") or 0)],
            ["collect_oos_evidence", str(summary.get("exact_next_action_counts", {}).get("collect_oos_evidence") or 0)],
            ["expand_basket_coverage", str(summary.get("exact_next_action_counts", {}).get("expand_basket_coverage") or 0)],
            ["materialize_lineage_from_existing_artifacts", str(summary.get("exact_next_action_counts", {}).get("materialize_lineage_from_existing_artifacts") or 0)],
            ["require_identity_resolution", str(summary.get("exact_next_action_counts", {}).get("require_identity_resolution") or 0)],
        ],
    )
    row_table = _table(
        ["Symbol", "Blocker", "Priority", "Batch", "Action", "Artifact", "Auto-run"],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("blocker_code") or ""),
                str(row.get("priority_bucket") or ""),
                str(row.get("recommended_batch") or ""),
                str(row.get("exact_next_action") or ""),
                str(row.get("required_artifact") or ""),
                str(bool(row.get("allowed_to_auto_run"))).lower(),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Basket Next-Action Queue",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Action counts",
            count_table,
            "",
            "## 3. Queue rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_basket_next_action_queue: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_basket_next_action_queue",
        description="Build the read-only basket next-action queue.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_basket_next_action_queue(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
