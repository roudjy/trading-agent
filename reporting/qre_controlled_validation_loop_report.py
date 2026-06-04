from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_controlled_validation_execution as execution
from reporting import qre_controlled_validation_learning_proposal as learning
from reporting import qre_controlled_validation_research_action_queue_gate as queue_gate
from reporting import qre_controlled_validation_result_analysis as analysis

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_validation_loop_report"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_validation_loop_report"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_controlled_validation_loop_report/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH


def _utcnow() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _final_recommendation(
    *,
    execution_snapshot: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    learning_snapshot: dict[str, Any],
    queue_snapshot: dict[str, Any],
) -> str:
    if queue_snapshot.get("queue_mutation_authorized") is True:
        return "controlled_validation_loop_queue_mutation_authorized_writer_not_connected"
    if learning_snapshot.get("learning_status") == "learning_ready_for_operator_review":
        return "controlled_validation_loop_learning_ready_for_operator_review"
    if analysis_snapshot.get("analysis_status") == "analysis_ready":
        return "controlled_validation_loop_analysis_ready"
    if execution_snapshot.get("controlled_validation_authorized") is True:
        return "controlled_validation_loop_execution_authorized_runner_not_connected"
    return "controlled_validation_loop_blocked_before_execution"


def _counts(
    *,
    execution_snapshot: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    learning_snapshot: dict[str, Any],
    queue_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "execution_authorized": (
            1 if execution_snapshot.get("controlled_validation_authorized") is True else 0
        ),
        "analysis_ready": (
            1 if analysis_snapshot.get("analysis_status") == "analysis_ready" else 0
        ),
        "learning_ready": (
            1
            if learning_snapshot.get("learning_status")
            == "learning_ready_for_operator_review"
            else 0
        ),
        "queue_mutation_authorized": (
            1 if queue_snapshot.get("queue_mutation_authorized") is True else 0
        ),
    }


def collect_snapshot(
    *,
    profile_name: str | None = None,
    execute_controlled_validation: bool = False,
    execution_operator_go: str | None = None,
    connect_runner_adapter: bool = False,
    timeout_seconds_per_campaign: int = execution.QRE_CONTROLLED_EVAL_DEFAULT_TIMEOUT_SECONDS,
    write_research_action_queue: bool = False,
    queue_operator_go: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()

    execution_snapshot = execution.collect_snapshot(
        profile_name=profile_name,
        execute_controlled_validation=execute_controlled_validation,
        operator_go=execution_operator_go,
        connect_runner_adapter=connect_runner_adapter,
        timeout_seconds_per_campaign=timeout_seconds_per_campaign,
        generated_at_utc=generated,
    )
    analysis_snapshot = analysis.collect_snapshot(
        profile_name=profile_name,
        execution_snapshot=execution_snapshot,
        generated_at_utc=generated,
    )
    learning_snapshot = learning.collect_snapshot(
        profile_name=profile_name,
        analysis_snapshot=analysis_snapshot,
        generated_at_utc=generated,
    )
    queue_snapshot = queue_gate.collect_snapshot(
        profile_name=profile_name,
        learning_snapshot=learning_snapshot,
        write_research_action_queue=write_research_action_queue,
        operator_go=queue_operator_go,
        generated_at_utc=generated,
    )

    final_recommendation = _final_recommendation(
        execution_snapshot=execution_snapshot,
        analysis_snapshot=analysis_snapshot,
        learning_snapshot=learning_snapshot,
        queue_snapshot=queue_snapshot,
    )

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "selection_profile_name": profile_name,
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
        "final_recommendation": final_recommendation,
        "counts": _counts(
            execution_snapshot=execution_snapshot,
            analysis_snapshot=analysis_snapshot,
            learning_snapshot=learning_snapshot,
            queue_snapshot=queue_snapshot,
        ),
        "loop_stages": {
            "execution": {
                "report_kind": execution_snapshot.get("report_kind"),
                "execution_status": execution_snapshot.get("execution_status"),
                "controlled_validation_authorized": (
                    execution_snapshot.get("controlled_validation_authorized") is True
                ),
                "runner_adapter_status": execution_snapshot.get("runner_adapter_status"),
                "final_recommendation": execution_snapshot.get("final_recommendation"),
            },
            "result_analysis": {
                "report_kind": analysis_snapshot.get("report_kind"),
                "analysis_status": analysis_snapshot.get("analysis_status"),
                "final_recommendation": analysis_snapshot.get("final_recommendation"),
            },
            "learning_proposal": {
                "report_kind": learning_snapshot.get("report_kind"),
                "learning_status": learning_snapshot.get("learning_status"),
                "proposal_available": (
                    (learning_snapshot.get("learning_proposal") or {}).get("available")
                    is True
                ),
                "final_recommendation": learning_snapshot.get("final_recommendation"),
            },
            "research_action_queue_gate": {
                "report_kind": queue_snapshot.get("report_kind"),
                "queue_status": queue_snapshot.get("queue_status"),
                "queue_mutation_authorized": (
                    queue_snapshot.get("queue_mutation_authorized") is True
                ),
                "queue_writer_adapter_status": queue_snapshot.get(
                    "queue_writer_adapter_status"
                ),
                "final_recommendation": queue_snapshot.get("final_recommendation"),
            },
        },
        "next_required_step": (
            "connect controlled validation runner adapter"
            if execution_snapshot.get("controlled_validation_authorized") is True
            else "authorize controlled validation execution with exact operator-go"
        ),
        "operator_authorizations": {
            "controlled_validation_execution": execution_snapshot.get(
                "operator_authorization"
            ),
            "research_action_queue_mutation": queue_snapshot.get("operator_authorization"),
        },
        "validation_warnings": [],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE controlled validation loop dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_validation_loop_report.",
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
        prog="reporting.qre_controlled_validation_loop_report",
        description="Summarize QRE controlled validation execution, analysis, learning, and queue gates.",
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--execute-controlled-validation", action="store_true")
    parser.add_argument("--execution-operator-go", default=None)
    parser.add_argument("--connect-runner-adapter", action="store_true")
    parser.add_argument(
        "--timeout-seconds-per-campaign",
        type=int,
        default=execution.QRE_CONTROLLED_EVAL_DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--write-research-action-queue", action="store_true")
    parser.add_argument("--queue-operator-go", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        profile_name=args.profile,
        execute_controlled_validation=bool(args.execute_controlled_validation),
        execution_operator_go=args.execution_operator_go,
        connect_runner_adapter=bool(args.connect_runner_adapter),
        timeout_seconds_per_campaign=int(args.timeout_seconds_per_campaign),
        write_research_action_queue=bool(args.write_research_action_queue),
        queue_operator_go=args.queue_operator_go,
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
    "REPORT_KIND",
    "collect_snapshot",
    "main",
    "write_outputs",
]
