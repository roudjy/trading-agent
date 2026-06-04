from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_controlled_validation_execution as execution

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

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
    return ANALYSIS_READY


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
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_execution = execution_snapshot or execution.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )

    status = _analysis_status(active_execution)

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
        "execution_summary": {
            "report_kind": active_execution.get("report_kind"),
            "execution_status": active_execution.get("execution_status"),
            "controlled_validation_authorized": (
                active_execution.get("controlled_validation_authorized") is True
            ),
            "runner_adapter_status": active_execution.get("runner_adapter_status"),
            "executed_anything": active_execution.get("executed_anything") is True,
            "final_recommendation": active_execution.get("final_recommendation"),
        },
        "result_summary": {
            "completed_run_available": status == ANALYSIS_READY,
            "pass_fail": None,
            "trade_count": None,
            "primary_failure_class": None,
            "evidence_refs": [],
        },
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
