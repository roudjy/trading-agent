from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_selection_closed_loop_preflight as preflight

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_validation_execution"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_validation_execution"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_controlled_validation_execution/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

REQUIRED_OPERATOR_GO_PHRASE: Final[str] = (
    "I authorize QRE controlled validation execution"
)

EXECUTION_BLOCKED_NOT_REQUESTED: Final[str] = "execution_blocked_not_requested"
EXECUTION_BLOCKED_PREFLIGHT_NOT_READY: Final[str] = "execution_blocked_preflight_not_ready"
EXECUTION_BLOCKED_OPERATOR_GO_MISSING: Final[str] = "execution_blocked_operator_go_missing"
EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH: Final[str] = "execution_blocked_operator_go_mismatch"
EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED: Final[str] = (
    "execution_authorized_runner_not_connected"
)

EXECUTION_STATUSES: Final[tuple[str, ...]] = (
    EXECUTION_BLOCKED_NOT_REQUESTED,
    EXECUTION_BLOCKED_PREFLIGHT_NOT_READY,
    EXECUTION_BLOCKED_OPERATOR_GO_MISSING,
    EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH,
    EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED,
)


def _utcnow() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _authorization_status(
    *,
    execute_controlled_validation: bool,
    operator_go: str | None,
    selection_route_ready: bool,
) -> str:
    if not execute_controlled_validation:
        return EXECUTION_BLOCKED_NOT_REQUESTED
    if not selection_route_ready:
        return EXECUTION_BLOCKED_PREFLIGHT_NOT_READY
    if operator_go is None or operator_go.strip() == "":
        return EXECUTION_BLOCKED_OPERATOR_GO_MISSING
    if operator_go.strip() != REQUIRED_OPERATOR_GO_PHRASE:
        return EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH
    return EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED


def _counts(status: str) -> dict[str, Any]:
    return {
        "total": 1,
        "authorized": 1 if status == EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED else 0,
        "blocked": 0 if status == EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED else 1,
        "by_execution_status": {
            candidate: 1 if candidate == status else 0
            for candidate in EXECUTION_STATUSES
        },
    }


def _final_recommendation(status: str) -> str:
    if status == EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED:
        return "controlled_validation_execution_authorized_runner_not_connected"
    return "controlled_validation_execution_blocked"


def collect_snapshot(
    *,
    profile_name: str | None = None,
    execute_controlled_validation: bool = False,
    operator_go: str | None = None,
    preflight_snapshot: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_preflight = preflight_snapshot or preflight.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )

    selection_route = active_preflight.get("selection_route") or {}
    selection_route_ready = selection_route.get("ready") is True
    status = _authorization_status(
        execute_controlled_validation=execute_controlled_validation,
        operator_go=operator_go,
        selection_route_ready=selection_route_ready,
    )
    authorized = status == EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED

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
        "controlled_validation_authorized": authorized,
        "live_or_paper_execution_authorized": False,
        "runner_adapter_status": "not_connected",
        "execution_status": status,
        "final_recommendation": _final_recommendation(status),
        "counts": _counts(status),
        "operator_authorization": {
            "required": True,
            "provided": operator_go is not None and operator_go.strip() != "",
            "matched": operator_go is not None
            and operator_go.strip() == REQUIRED_OPERATOR_GO_PHRASE,
            "required_phrase": REQUIRED_OPERATOR_GO_PHRASE,
        },
        "preflight": {
            "report_kind": active_preflight.get("report_kind"),
            "final_recommendation": active_preflight.get("final_recommendation"),
            "selection_route_ready": selection_route_ready,
            "selection_route_counts": selection_route.get("counts") or {},
            "controlled_regeneration_can_be_considered": (
                (active_preflight.get("controlled_regeneration_preflight") or {}).get(
                    "can_be_considered"
                )
                is True
            ),
        },
        "planned_runner": {
            "module": "research.controlled_eval",
            "callable": "run_controlled_eval",
            "connected": False,
            "reason": "runner adapter intentionally not connected in authority-contract stage",
        },
        "would_write_artifacts": [
            "logs/qre_controlled_validation_execution/latest.json",
        ],
        "validation_warnings": [],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE controlled validation dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_validation_execution.",
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
        prog="reporting.qre_controlled_validation_execution",
        description="Authorize QRE controlled validation execution without connecting a runner.",
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--execute-controlled-validation", action="store_true")
    parser.add_argument("--operator-go", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        profile_name=args.profile,
        execute_controlled_validation=bool(args.execute_controlled_validation),
        operator_go=args.operator_go,
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
    "EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED",
    "EXECUTION_BLOCKED_NOT_REQUESTED",
    "EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH",
    "EXECUTION_BLOCKED_OPERATOR_GO_MISSING",
    "EXECUTION_BLOCKED_PREFLIGHT_NOT_READY",
    "REPORT_KIND",
    "REQUIRED_OPERATOR_GO_PHRASE",
    "collect_snapshot",
    "main",
    "write_outputs",
]
