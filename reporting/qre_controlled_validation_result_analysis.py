from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_controlled_validation_execution as execution

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SCREENING_EVIDENCE_LATEST: Final[Path] = (
    REPO_ROOT / "research" / "screening_evidence_latest.v1.json"
)

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_validation_result_analysis"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_validation_result_analysis"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_controlled_validation_result_analysis/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

ANALYSIS_BLOCKED_EXECUTION_NOT_AUTHORIZED: Final[str] = (
    "analysis_blocked_execution_not_authorized"
)
ANALYSIS_BLOCKED_RUNNER_NOT_CONNECTED: Final[str] = (
    "analysis_blocked_runner_not_connected"
)
ANALYSIS_BLOCKED_NO_COMPLETED_RUN: Final[str] = "analysis_blocked_no_completed_run"
ANALYSIS_READY: Final[str] = "analysis_ready"

ANALYSIS_STATUSES: Final[tuple[str, ...]] = (
    ANALYSIS_BLOCKED_EXECUTION_NOT_AUTHORIZED,
    ANALYSIS_BLOCKED_RUNNER_NOT_CONNECTED,
    ANALYSIS_BLOCKED_NO_COMPLETED_RUN,
    ANALYSIS_READY,
)


def _utcnow() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _analysis_status(execution_snapshot: dict[str, Any]) -> str:
    if execution_snapshot.get("controlled_validation_authorized") is not True:
        return ANALYSIS_BLOCKED_EXECUTION_NOT_AUTHORIZED
    if execution_snapshot.get("runner_adapter_status") != "connected":
        return ANALYSIS_BLOCKED_RUNNER_NOT_CONNECTED
    if execution_snapshot.get("executed_anything") is not True:
        return ANALYSIS_BLOCKED_NO_COMPLETED_RUN
    if execution_snapshot.get("execution_status") != "execution_completed":
        return ANALYSIS_BLOCKED_NO_COMPLETED_RUN
    return ANALYSIS_READY


def _current_git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _artifact_freshness(
    payload: dict[str, Any] | None,
    *,
    current_git_revision: str | None,
) -> dict[str, Any]:
    artifact_git_revision = (
        payload.get("git_revision") if isinstance(payload, dict) else None
    )
    if not isinstance(artifact_git_revision, str) or not artifact_git_revision:
        artifact_git_revision = None

    reason_codes: list[str] = []
    artifact_may_be_stale = False

    if artifact_git_revision is None:
        reason_codes.append("artifact_git_revision_missing")
        artifact_may_be_stale = True
    if current_git_revision is None:
        reason_codes.append("current_git_revision_unavailable")
        artifact_may_be_stale = True
    if (
        artifact_git_revision is not None
        and current_git_revision is not None
        and artifact_git_revision != current_git_revision
    ):
        reason_codes.append("artifact_git_revision_differs_from_current_head")
        artifact_may_be_stale = True
    if not reason_codes:
        reason_codes.append("artifact_git_revision_matches_current_head")

    return {
        "artifact_git_revision": artifact_git_revision,
        "current_git_revision": current_git_revision,
        "artifact_may_be_stale": artifact_may_be_stale,
        "reason_codes": reason_codes,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_controlled_eval_report_path(
    execution_snapshot: dict[str, Any],
) -> Path | None:
    result = execution_snapshot.get("controlled_eval_result")
    if not isinstance(result, dict):
        return None
    report_paths = result.get("report_paths")
    if not isinstance(report_paths, dict):
        return None
    value = report_paths.get("report_json")
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def _controlled_eval_report_summary(
    execution_snapshot: dict[str, Any],
    status: str,
    *,
    current_git_revision: str | None = None,
) -> dict[str, Any]:
    report_path = _resolve_controlled_eval_report_path(execution_snapshot)
    payload = _read_json(report_path) if report_path is not None else None
    verdict = (payload or {}).get("verdict")
    if not isinstance(verdict, dict):
        verdict = {}
    reason_codes = verdict.get("reason_codes")
    if not isinstance(reason_codes, list):
        reason_codes = []

    screening_evidence_summary = (payload or {}).get("screening_evidence_summary")
    if not isinstance(screening_evidence_summary, dict):
        screening_evidence_summary = {}

    freshness = _artifact_freshness(
        payload,
        current_git_revision=current_git_revision,
    )

    return {
        "present": payload is not None,
        "path": report_path.as_posix() if report_path is not None else None,
        "artifact_freshness": freshness,
        "verdict_status": verdict.get("status"),
        "campaigns_completed": (payload or {}).get("campaigns_completed"),
        "campaign_level_evidence_valid": (payload or {}).get(
            "campaign_level_evidence_valid"
        ),
        "recommended_next_action": (payload or {}).get("recommended_next_action"),
        "reason_codes": list(reason_codes),
        "screening_evidence_summary": screening_evidence_summary,
    }


def _screening_evidence_candidates(
    screening_evidence_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    payload = screening_evidence_payload
    if payload is None:
        payload = _read_json(SCREENING_EVIDENCE_LATEST)
    candidates = (payload or {}).get("candidates")
    if not isinstance(candidates, list):
        return []
    return [row for row in candidates if isinstance(row, dict)]


def _top_counts(values: list[str], *, limit: int = 5) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"reason": reason, "count": count} for reason, count in ordered[:limit]]


def _candidate_operator_row(row: dict[str, Any]) -> dict[str, Any]:
    validation = row.get("validation_evidence")
    if not isinstance(validation, dict):
        validation = {}
    promotion_guard = row.get("promotion_guard")
    if not isinstance(promotion_guard, dict):
        promotion_guard = {}
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    failure_reasons = row.get("failure_reasons")
    if not isinstance(failure_reasons, list):
        failure_reasons = []
    return {
        "asset": str(row.get("asset") or ""),
        "preset_name": row.get("preset_name"),
        "strategy_name": row.get("strategy_name"),
        "interval": row.get("interval"),
        "stage_result": row.get("stage_result"),
        "qre_validation_linkage_status": row.get("qre_validation_linkage_status"),
        "validation_evidence_status": validation.get("status"),
        "oos_trade_count": validation.get("oos_trade_count"),
        "min_oos_trades": validation.get("min_oos_trades"),
        "promotion_allowed": promotion_guard.get("promotion_allowed") is True,
        "blocked_by": list(promotion_guard.get("blocked_by") or []),
        "failure_reasons": list(failure_reasons),
        "near_pass": bool((row.get("near_pass") or {}).get("is_near_pass")),
        "metrics": {
            "win_rate": metrics.get("win_rate"),
            "trades_per_maand": metrics.get("trades_per_maand"),
            "consistentie": metrics.get("consistentie"),
            "deflated_sharpe": metrics.get("deflated_sharpe"),
        },
    }


def _operator_summary(
    *,
    controlled_eval_summary: dict[str, Any],
    execution_summary: dict[str, Any],
    screening_evidence_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = _screening_evidence_candidates(screening_evidence_payload)
    screening_summary = controlled_eval_summary.get("screening_evidence_summary")
    if not isinstance(screening_summary, dict):
        screening_summary = {}

    linked_count = 0
    sufficient_oos_count = 0
    promotion_allowed_count = 0
    near_pass_count = 0
    blocked_reasons: list[str] = []
    failure_reasons: list[str] = []
    asset_rows: list[dict[str, Any]] = []
    runtime_gate_failed_assets: list[str] = []
    public_result_criteria_blocked_assets: list[str] = []
    near_pass_assets: list[str] = []

    for row in sorted(candidates, key=lambda item: str(item.get("asset") or "")):
        op_row = _candidate_operator_row(row)
        asset_rows.append(op_row)
        asset = op_row["asset"]
        if op_row["qre_validation_linkage_status"] == "linked_catalog_active_discovery":
            linked_count += 1
        if op_row["validation_evidence_status"] == "sufficient_oos_evidence":
            sufficient_oos_count += 1
        if op_row["promotion_allowed"]:
            promotion_allowed_count += 1
        else:
            blocked_reasons.extend(str(reason) for reason in op_row["blocked_by"])
        if op_row["failure_reasons"]:
            runtime_gate_failed_assets.append(asset)
        if (
            op_row["stage_result"] == "screening_pass"
            and op_row["promotion_allowed"] is False
        ):
            public_result_criteria_blocked_assets.append(asset)
        if op_row["near_pass"]:
            near_pass_count += 1
            near_pass_assets.append(asset)
        failure_reasons.extend(str(reason) for reason in op_row["failure_reasons"])

    total_candidates = int(screening_summary.get("total_candidates") or len(candidates))
    promotion_blocked_count = max(total_candidates - promotion_allowed_count, 0)
    verdict_status = controlled_eval_summary.get("verdict_status")
    next_recommendation = (
        controlled_eval_summary.get("recommended_next_action")
        or execution_summary.get("final_recommendation")
    )
    freshness = controlled_eval_summary.get("artifact_freshness")
    if not isinstance(freshness, dict):
        freshness = {}

    return {
        "total_candidates": total_candidates,
        "linked_catalog_active_discovery_count": linked_count,
        "sufficient_oos_evidence_count": sufficient_oos_count,
        "promotion_allowed_count": promotion_allowed_count,
        "promotion_blocked_count": promotion_blocked_count,
        "near_pass_count": near_pass_count,
        "top_promotion_blockers": _top_counts(blocked_reasons),
        "top_failure_reasons": _top_counts(failure_reasons),
        "runtime_gate_failed_assets": runtime_gate_failed_assets,
        "public_result_criteria_blocked_assets": public_result_criteria_blocked_assets,
        "near_pass_assets": near_pass_assets,
        "selected_asset_explanations": asset_rows,
        "campaign_verdict": verdict_status,
        "next_recommendation": next_recommendation,
        "safety_flags": {
            "artifact_may_be_stale": freshness.get("artifact_may_be_stale") is True,
            "controlled_validation_authorized": (
                execution_summary.get("controlled_validation_authorized") is True
            ),
            "runner_adapter_status": execution_summary.get("runner_adapter_status"),
            "mutates_paper_shadow_live_runtime": False,
            "writes_development_work_queue": False,
            "writes_research_action_queue": False,
        },
    }


def _evidence_quality_bottleneck(
    *,
    controlled_eval_summary: dict[str, Any],
) -> dict[str, Any]:
    artifact_freshness = controlled_eval_summary.get("artifact_freshness")
    if not isinstance(artifact_freshness, dict):
        artifact_freshness = {}
    screening_summary = controlled_eval_summary.get("screening_evidence_summary")
    if not isinstance(screening_summary, dict):
        screening_summary = {}
    reason_codes = controlled_eval_summary.get("reason_codes")
    if not isinstance(reason_codes, list):
        reason_codes = []

    bottleneck_reason_codes: list[str] = []

    if artifact_freshness.get("artifact_may_be_stale") is True:
        bottleneck_reason_codes.append("controlled_eval_artifact_may_be_stale")
        return {
            "primary_bottleneck": "stale_artifact",
            "reason_codes": bottleneck_reason_codes,
            "artifact_freshness": artifact_freshness,
            "screening_evidence_summary": screening_summary,
        }

    if "registry_ledger_invariant_violation" in reason_codes:
        bottleneck_reason_codes.append("registry_ledger_invariant_violation")
        return {
            "primary_bottleneck": "registry_ledger_invariant_violation",
            "reason_codes": bottleneck_reason_codes,
            "artifact_freshness": artifact_freshness,
            "screening_evidence_summary": screening_summary,
        }

    sufficient_oos_but_unlinked = int(
        screening_summary.get("sufficient_oos_but_unlinked_candidates") or 0
    )
    qre_linkage_blocked = int(screening_summary.get("qre_linkage_blocked_candidates") or 0)
    sufficient_oos = int(screening_summary.get("sufficient_oos_evidence_candidates") or 0)
    passed_screening = int(screening_summary.get("passed_screening") or 0)
    rejected_screening = int(screening_summary.get("rejected_screening") or 0)

    if sufficient_oos_but_unlinked > 0 or qre_linkage_blocked > 0:
        bottleneck_reason_codes.append("sufficient_oos_evidence_blocked_by_qre_linkage")
        return {
            "primary_bottleneck": "linkage_blocker",
            "reason_codes": bottleneck_reason_codes,
            "artifact_freshness": artifact_freshness,
            "screening_evidence_summary": screening_summary,
        }

    if passed_screening > 0 and sufficient_oos == 0:
        bottleneck_reason_codes.append("screening_passed_without_sufficient_oos_evidence")
        return {
            "primary_bottleneck": "no_oos_evidence",
            "reason_codes": bottleneck_reason_codes,
            "artifact_freshness": artifact_freshness,
            "screening_evidence_summary": screening_summary,
        }

    if rejected_screening > 0 and passed_screening == 0:
        bottleneck_reason_codes.append("screening_rejected_candidates_before_validation")
        return {
            "primary_bottleneck": "insufficient_trades",
            "reason_codes": bottleneck_reason_codes,
            "artifact_freshness": artifact_freshness,
            "screening_evidence_summary": screening_summary,
        }

    bottleneck_reason_codes.append("no_evidence_quality_bottleneck_detected")
    return {
        "primary_bottleneck": "no_bottleneck_detected",
        "reason_codes": bottleneck_reason_codes,
        "artifact_freshness": artifact_freshness,
        "screening_evidence_summary": screening_summary,
    }


def _pass_fail_from_report(summary: dict[str, Any]) -> str | None:
    verdict_status = summary.get("verdict_status")
    campaigns_completed = int(summary.get("campaigns_completed") or 0)
    if verdict_status in {"technical_failure"}:
        return "fail"
    if campaigns_completed > 0:
        return "pass"
    if verdict_status in {"no_campaign_completed"}:
        return "fail"
    return None


def _failure_class_from_report(summary: dict[str, Any]) -> str | None:
    if _pass_fail_from_report(summary) != "fail":
        return None
    reason_codes = summary.get("reason_codes")
    if isinstance(reason_codes, list) and reason_codes:
        return str(reason_codes[0])
    verdict_status = summary.get("verdict_status")
    return str(verdict_status) if verdict_status else "unknown_failure"


def _counts(status: str) -> dict[str, Any]:
    return {
        "total": 1,
        "ready": 1 if status == ANALYSIS_READY else 0,
        "blocked": 0 if status == ANALYSIS_READY else 1,
        "by_analysis_status": {
            candidate: 1 if candidate == status else 0
            for candidate in ANALYSIS_STATUSES
        },
    }


def _final_recommendation(status: str) -> str:
    if status == ANALYSIS_READY:
        return "controlled_validation_result_analysis_ready"
    return "controlled_validation_result_analysis_blocked"


def collect_snapshot(
    *,
    profile_name: str | None = None,
    execution_snapshot: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
    current_git_revision: str | None = None,
    screening_evidence_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_execution = execution_snapshot or execution.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )
    resolved_current_git_revision = (
        current_git_revision
        if current_git_revision is not None
        else _current_git_revision()
    )

    status = _analysis_status(active_execution)
    controlled_eval_summary = _controlled_eval_report_summary(
        active_execution,
        status,
        current_git_revision=resolved_current_git_revision,
    )
    campaigns_completed = int(controlled_eval_summary.get("campaigns_completed") or 0)
    evidence_valid = controlled_eval_summary.get("campaign_level_evidence_valid") is True
    if status == ANALYSIS_READY and (campaigns_completed < 1 or not evidence_valid):
        status = ANALYSIS_BLOCKED_NO_COMPLETED_RUN
    pass_fail = _pass_fail_from_report(controlled_eval_summary)
    primary_failure_class = _failure_class_from_report(controlled_eval_summary)
    evidence_quality_bottleneck = _evidence_quality_bottleneck(
        controlled_eval_summary=controlled_eval_summary
    )
    evidence_refs = []
    if controlled_eval_summary.get("path"):
        evidence_refs.append(str(controlled_eval_summary["path"]))
    execution_summary = {
        "report_kind": active_execution.get("report_kind"),
        "execution_status": active_execution.get("execution_status"),
        "controlled_validation_authorized": (
            active_execution.get("controlled_validation_authorized") is True
        ),
        "runner_adapter_status": active_execution.get("runner_adapter_status"),
        "executed_anything": active_execution.get("executed_anything") is True,
        "final_recommendation": active_execution.get("final_recommendation"),
    }
    operator_summary = _operator_summary(
        controlled_eval_summary=controlled_eval_summary,
        execution_summary=execution_summary,
        screening_evidence_payload=screening_evidence_payload,
    )

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "selection_profile_name": (
            profile_name or active_execution.get("selection_profile_name")
        ),
        "safe_to_execute": False,
        "read_only": True,
        "eligible_for_direct_execution": False,
        "launches_subprocess": False,
        "launches_codex": False,
        "executed_anything": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "writes_research_action_queue": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "analysis_status": status,
        "final_recommendation": _final_recommendation(status),
        "counts": _counts(status),
        "execution_summary": execution_summary,
        "controlled_eval_report": controlled_eval_summary,
        "result_summary": {
            "completed_run_available": status == ANALYSIS_READY,
            "pass_fail": pass_fail,
            "trade_count": controlled_eval_summary.get("campaigns_completed"),
            "primary_failure_class": primary_failure_class,
            "artifact_freshness": controlled_eval_summary.get(
                "artifact_freshness", {}
            ),
            "screening_evidence_summary": controlled_eval_summary.get(
                "screening_evidence_summary", {}
            ),
            "evidence_quality_bottleneck": evidence_quality_bottleneck,
            "evidence_refs": evidence_refs,
        },
        "operator_summary": operator_summary,
        "next_required_step": (
            "connect controlled validation runner before result analysis"
            if status == ANALYSIS_BLOCKED_RUNNER_NOT_CONNECTED
            else (
                "authorize and complete controlled validation execution"
                if status == ANALYSIS_BLOCKED_EXECUTION_NOT_AUTHORIZED
                else (
                    "materialize completed controlled validation run artifacts"
                    if status == ANALYSIS_BLOCKED_NO_COMPLETED_RUN
                    else "review controlled validation result analysis"
                )
            )
        ),
        "validation_warnings": [],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(
            f"refusing write outside QRE controlled validation result analysis dir: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_validation_result_analysis.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        Path(tmp_name).replace(path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_controlled_validation_result_analysis",
        description="Analyze QRE controlled validation results when a completed run exists.",
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        profile_name=args.profile,
        generated_at_utc=args.frozen_utc,
    )
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    if not args.no_write:
        write_outputs(snapshot)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "ANALYSIS_BLOCKED_EXECUTION_NOT_AUTHORIZED",
    "ANALYSIS_BLOCKED_NO_COMPLETED_RUN",
    "ANALYSIS_BLOCKED_RUNNER_NOT_CONNECTED",
    "ANALYSIS_READY",
    "ARTIFACT_LATEST",
    "REPORT_KIND",
    "collect_snapshot",
    "main",
    "write_outputs",
]
