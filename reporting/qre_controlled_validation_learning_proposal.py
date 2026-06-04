from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_controlled_validation_result_analysis as analysis

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_validation_learning_proposal"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_validation_learning_proposal"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_controlled_validation_learning_proposal/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

LEARNING_BLOCKED_ANALYSIS_NOT_READY: Final[str] = "learning_blocked_analysis_not_ready"
LEARNING_READY_FOR_OPERATOR_REVIEW: Final[str] = "learning_ready_for_operator_review"

LEARNING_STATUSES: Final[tuple[str, ...]] = (
    LEARNING_BLOCKED_ANALYSIS_NOT_READY,
    LEARNING_READY_FOR_OPERATOR_REVIEW,
)


def _utcnow() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _learning_status(analysis_snapshot: dict[str, Any]) -> str:
    if analysis_snapshot.get("analysis_status") != "analysis_ready":
        return LEARNING_BLOCKED_ANALYSIS_NOT_READY
    return LEARNING_READY_FOR_OPERATOR_REVIEW


def _counts(status: str) -> dict[str, Any]:
    return {
        "total": 1,
        "ready": 1 if status == LEARNING_READY_FOR_OPERATOR_REVIEW else 0,
        "blocked": 0 if status == LEARNING_READY_FOR_OPERATOR_REVIEW else 1,
        "by_learning_status": {
            candidate: 1 if candidate == status else 0
            for candidate in LEARNING_STATUSES
        },
    }


def _final_recommendation(status: str) -> str:
    if status == LEARNING_READY_FOR_OPERATOR_REVIEW:
        return "controlled_validation_learning_proposal_ready_for_operator_review"
    return "controlled_validation_learning_proposal_blocked"


def _proposal_from_analysis(analysis_snapshot: dict[str, Any], status: str) -> dict[str, Any]:
    result_summary = analysis_snapshot.get("result_summary") or {}
    evidence_refs = result_summary.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []

    if status != LEARNING_READY_FOR_OPERATOR_REVIEW:
        return {
            "available": False,
            "outcome": None,
            "hypothesis_action": None,
            "next_research_action": None,
            "evidence_refs": [],
            "reason": "result analysis is not ready",
        }

    pass_fail = result_summary.get("pass_fail")
    primary_failure_class = result_summary.get("primary_failure_class")
    if pass_fail == "pass":
        hypothesis_action = "continue_validation"
        next_research_action = "consider_bounded_followup_validation"
    elif pass_fail == "fail":
        hypothesis_action = "do_not_promote"
        next_research_action = "investigate_failure_class"
    else:
        hypothesis_action = "hold_for_operator_review"
        next_research_action = "review_inconclusive_result"

    return {
        "available": True,
        "outcome": pass_fail,
        "hypothesis_action": hypothesis_action,
        "next_research_action": next_research_action,
        "primary_failure_class": primary_failure_class,
        "evidence_refs": list(evidence_refs),
        "reason": "derived from controlled validation result analysis",
    }


def collect_snapshot(
    *,
    profile_name: str | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_analysis = analysis_snapshot or analysis.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )

    status = _learning_status(active_analysis)
    proposal = _proposal_from_analysis(active_analysis, status)

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "selection_profile_name": (
            profile_name or active_analysis.get("selection_profile_name")
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
        "learning_status": status,
        "final_recommendation": _final_recommendation(status),
        "counts": _counts(status),
        "analysis_summary": {
            "report_kind": active_analysis.get("report_kind"),
            "analysis_status": active_analysis.get("analysis_status"),
            "final_recommendation": active_analysis.get("final_recommendation"),
            "completed_run_available": (
                (active_analysis.get("result_summary") or {}).get(
                    "completed_run_available"
                )
                is True
            ),
        },
        "learning_proposal": proposal,
        "next_required_step": (
            "complete controlled validation result analysis before learning proposal"
            if status == LEARNING_BLOCKED_ANALYSIS_NOT_READY
            else "operator review learning proposal before any queue mutation"
        ),
        "validation_warnings": [],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(
            f"refusing write outside QRE controlled validation learning proposal dir: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_validation_learning_proposal.",
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
        prog="reporting.qre_controlled_validation_learning_proposal",
        description="Build a deterministic QRE learning proposal after result analysis.",
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
    "ARTIFACT_LATEST",
    "LEARNING_BLOCKED_ANALYSIS_NOT_READY",
    "LEARNING_READY_FOR_OPERATOR_REVIEW",
    "REPORT_KIND",
    "collect_snapshot",
    "main",
    "write_outputs",
]
