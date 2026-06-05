from __future__ import annotations

import argparse
import datetime as dt
import importlib
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_executable_hypothesis_identity_bridge_diagnostics as bridge_diagnostics
from reporting import qre_selection_closed_loop_preflight as preflight

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_validation_execution"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_controlled_validation_execution"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_controlled_validation_execution/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH
CONTROLLED_EVAL_REPORT_JSON: Final[Path] = (
    ARTIFACT_DIR / "controlled_eval_latest.v1.json"
)
CONTROLLED_EVAL_REPORT_MD: Final[Path] = ARTIFACT_DIR / "controlled_eval_latest.md"

QRE_CONTROLLED_EVAL_MAX_CAMPAIGNS: Final[int] = 1
QRE_CONTROLLED_EVAL_MIN_TIMEOUT_SECONDS: Final[int] = 60
QRE_CONTROLLED_EVAL_MAX_TIMEOUT_SECONDS: Final[int] = 3600
QRE_CONTROLLED_EVAL_DEFAULT_TIMEOUT_SECONDS: Final[int] = 60
QRE_CONTROLLED_EVAL_DEFAULT_POLL_SECONDS: Final[int] = 0

REQUIRED_OPERATOR_GO_PHRASE: Final[str] = (
    "I authorize QRE controlled validation execution"
)

EXECUTION_BLOCKED_NOT_REQUESTED: Final[str] = "execution_blocked_not_requested"
EXECUTION_BLOCKED_PREFLIGHT_NOT_READY: Final[str] = "execution_blocked_preflight_not_ready"
EXECUTION_BLOCKED_BRIDGE_NOT_READY: Final[str] = "execution_blocked_bridge_not_ready"
EXECUTION_BLOCKED_CAMPAIGN_INVARIANT_VIOLATION: Final[str] = (
    "execution_blocked_campaign_invariant_violation"
)
EXECUTION_BLOCKED_OPERATOR_GO_MISSING: Final[str] = "execution_blocked_operator_go_missing"
EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH: Final[str] = "execution_blocked_operator_go_mismatch"
EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED: Final[str] = (
    "execution_authorized_runner_not_connected"
)
EXECUTION_COMPLETED: Final[str] = "execution_completed"
EXECUTION_FAILED: Final[str] = "execution_failed"

EXECUTION_STATUSES: Final[tuple[str, ...]] = (
    EXECUTION_BLOCKED_NOT_REQUESTED,
    EXECUTION_BLOCKED_PREFLIGHT_NOT_READY,
    EXECUTION_BLOCKED_BRIDGE_NOT_READY,
    EXECUTION_BLOCKED_CAMPAIGN_INVARIANT_VIOLATION,
    EXECUTION_BLOCKED_OPERATOR_GO_MISSING,
    EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH,
    EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED,
    EXECUTION_COMPLETED,
    EXECUTION_FAILED,
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
    controlled_validation_bridge_ready: bool,
) -> str:
    if not execute_controlled_validation:
        return EXECUTION_BLOCKED_NOT_REQUESTED
    if not selection_route_ready:
        return EXECUTION_BLOCKED_PREFLIGHT_NOT_READY
    if operator_go is None or operator_go.strip() == "":
        return EXECUTION_BLOCKED_OPERATOR_GO_MISSING
    if operator_go.strip() != REQUIRED_OPERATOR_GO_PHRASE:
        return EXECUTION_BLOCKED_OPERATOR_GO_MISMATCH
    if not controlled_validation_bridge_ready:
        return EXECUTION_BLOCKED_BRIDGE_NOT_READY
    return EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED


def _counts(status: str) -> dict[str, Any]:
    completed = status == EXECUTION_COMPLETED
    authorized = status in {
        EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED,
        EXECUTION_COMPLETED,
        EXECUTION_FAILED,
    }
    return {
        "total": 1,
        "authorized": 1 if authorized else 0,
        "blocked": 0 if authorized else 1,
        "completed": 1 if completed else 0,
        "failed": 1 if status == EXECUTION_FAILED else 0,
        "by_execution_status": {
            candidate: 1 if candidate == status else 0
            for candidate in EXECUTION_STATUSES
        },
    }


def _final_recommendation(status: str) -> str:
    if status == EXECUTION_COMPLETED:
        return "controlled_validation_execution_completed"
    if status == EXECUTION_FAILED:
        return "controlled_validation_execution_failed"
    if status == EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED:
        return "controlled_validation_execution_authorized_runner_not_connected"
    if status == EXECUTION_BLOCKED_BRIDGE_NOT_READY:
        return "controlled_validation_execution_blocked_bridge_not_ready"
    if status == EXECUTION_BLOCKED_CAMPAIGN_INVARIANT_VIOLATION:
        return "controlled_validation_execution_blocked_campaign_invariant_violation"
    return "controlled_validation_execution_blocked"


def _bounded_timeout_seconds(value: int) -> int:
    if value < QRE_CONTROLLED_EVAL_MIN_TIMEOUT_SECONDS:
        raise ValueError(
            "timeout_seconds_per_campaign must be at least "
            f"{QRE_CONTROLLED_EVAL_MIN_TIMEOUT_SECONDS}"
        )
    if value > QRE_CONTROLLED_EVAL_MAX_TIMEOUT_SECONDS:
        raise ValueError(
            "timeout_seconds_per_campaign must be at most "
            f"{QRE_CONTROLLED_EVAL_MAX_TIMEOUT_SECONDS}"
        )
    return int(value)


def _runner_report_paths() -> dict[str, str]:
    return {
        "report_json": _rel(CONTROLLED_EVAL_REPORT_JSON),
        "report_md": _rel(CONTROLLED_EVAL_REPORT_MD),
    }


def _campaign_invariant_preflight() -> dict[str, Any]:
    try:
        import importlib

        registry_module = importlib.import_module("research.campaign_registry")
        ledger_module = importlib.import_module("research.campaign_evidence_ledger")
    except Exception as exc:  # pragma: no cover - defensive diagnostic guard
        return {
            "status": "unknown",
            "reason": f"campaign_invariant_preflight_unavailable:{type(exc).__name__}",
            "completed_campaign_count": 0,
            "campaign_completed_ledger_event_count": 0,
            "missing_completed_ledger_event_ids": [],
        }

    registry_path = getattr(registry_module, "REGISTRY_ARTIFACT_PATH", None)
    load_registry = getattr(registry_module, "load_registry", None)
    load_events = getattr(ledger_module, "load_events", None)
    if registry_path is None or load_registry is None or load_events is None:
        return {
            "status": "unknown",
            "reason": "campaign_invariant_preflight_api_unavailable",
            "completed_campaign_count": 0,
            "campaign_completed_ledger_event_count": 0,
            "missing_completed_ledger_event_ids": [],
        }

    try:
        registry = load_registry(registry_path)
        ledger_events = load_events(Path("research/campaign_evidence_ledger_latest.v1.jsonl"))
    except Exception as exc:  # pragma: no cover - defensive diagnostic guard
        return {
            "status": "unknown",
            "reason": f"campaign_invariant_preflight_load_failed:{type(exc).__name__}",
            "completed_campaign_count": 0,
            "campaign_completed_ledger_event_count": 0,
            "missing_completed_ledger_event_ids": [],
        }

    campaigns = registry.get("campaigns") if isinstance(registry, dict) else {}
    if not isinstance(campaigns, dict):
        campaigns = {}

    completed_campaign_ids = {
        str(campaign_id)
        for campaign_id, record in campaigns.items()
        if isinstance(record, dict) and record.get("state") == "completed"
    }

    campaign_completed_ledger_ids: set[str] = set()
    for event in ledger_events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type") or event.get("type")
        if event_type != "campaign_completed":
            continue
        campaign_id = event.get("campaign_id")
        if campaign_id:
            campaign_completed_ledger_ids.add(str(campaign_id))

    missing_completed_ledger_event_ids = sorted(
        completed_campaign_ids - campaign_completed_ledger_ids
    )
    status = "failed" if missing_completed_ledger_event_ids else "passed"
    return {
        "status": status,
        "completed_campaign_count": len(completed_campaign_ids),
        "campaign_completed_ledger_event_count": len(campaign_completed_ledger_ids),
        "missing_completed_ledger_event_ids": missing_completed_ledger_event_ids,
    }


def _load_controlled_eval_module() -> Any:
    # Keep reporting/ADE import graph free of static research/QRE edges.
    # The real runner is loaded only after explicit operator authorization
    # and --connect-runner-adapter.
    return importlib.import_module("research.controlled_eval")


def _run_controlled_eval_adapter(
    *,
    profile_name: str,
    timeout_seconds_per_campaign: int,
) -> dict[str, Any]:
    timeout_seconds = _bounded_timeout_seconds(timeout_seconds_per_campaign)
    output = io.StringIO()
    controlled_eval = _load_controlled_eval_module()
    rc = controlled_eval.run_controlled_eval(
        profile=profile_name,
        max_campaigns=QRE_CONTROLLED_EVAL_MAX_CAMPAIGNS,
        timeout_seconds_per_campaign=timeout_seconds,
        poll_seconds=QRE_CONTROLLED_EVAL_DEFAULT_POLL_SECONDS,
        report_json=CONTROLLED_EVAL_REPORT_JSON,
        report_md=CONTROLLED_EVAL_REPORT_MD,
        out=output,
    )
    stdout = output.getvalue()
    return {
        "returncode": int(rc),
        "stdout_tail": stdout[-2000:],
        "report_paths": _runner_report_paths(),
    }


def collect_snapshot(
    *,
    profile_name: str | None = None,
    execute_controlled_validation: bool = False,
    operator_go: str | None = None,
    connect_runner_adapter: bool = False,
    timeout_seconds_per_campaign: int = QRE_CONTROLLED_EVAL_DEFAULT_TIMEOUT_SECONDS,
    preflight_snapshot: dict[str, Any] | None = None,
    controlled_validation_bridge_snapshot: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_preflight = preflight_snapshot or preflight.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )

    active_bridge_snapshot = (
        controlled_validation_bridge_snapshot
        or bridge_diagnostics.collect_snapshot(generated_at_utc=generated)
    )
    bridge_readiness = (
        active_bridge_snapshot.get("controlled_validation_bridge_readiness")
        if isinstance(active_bridge_snapshot, dict)
        else {}
    )
    if not isinstance(bridge_readiness, dict):
        bridge_readiness = {}
    controlled_validation_bridge_ready = bridge_readiness.get("ready") is True

    selection_route = active_preflight.get("selection_route") or {}
    selection_route_ready = selection_route.get("ready") is True
    status = _authorization_status(
        execute_controlled_validation=execute_controlled_validation,
        operator_go=operator_go,
        selection_route_ready=selection_route_ready,
        controlled_validation_bridge_ready=controlled_validation_bridge_ready,
    )
    campaign_invariant_preflight: dict[str, Any] = {
        "status": "not_checked",
        "completed_campaign_count": 0,
        "campaign_completed_ledger_event_count": 0,
        "missing_completed_ledger_event_ids": [],
    }

    runner_result: dict[str, Any] | None = None
    if status == EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED and connect_runner_adapter:
        if profile_name is None:
            raise ValueError("profile_name is required when connecting the runner adapter")
        _bounded_timeout_seconds(timeout_seconds_per_campaign)
        campaign_invariant_preflight = _campaign_invariant_preflight()
        if campaign_invariant_preflight.get("status") == "failed":
            status = EXECUTION_BLOCKED_CAMPAIGN_INVARIANT_VIOLATION
        else:
            runner_result = _run_controlled_eval_adapter(
                profile_name=profile_name,
                timeout_seconds_per_campaign=timeout_seconds_per_campaign,
            )
            status = (
                EXECUTION_COMPLETED
                if runner_result["returncode"] == 0
                else EXECUTION_FAILED
            )

    authorized = status in {
        EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED,
        EXECUTION_COMPLETED,
        EXECUTION_FAILED,
    }
    runner_connected = status in {EXECUTION_COMPLETED, EXECUTION_FAILED}
    executed_anything = runner_connected

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "selection_profile_name": profile_name,
        "safe_to_execute": False,
        "read_only": not executed_anything,
        "eligible_for_direct_execution": False,
        "launches_subprocess": executed_anything,
        "launches_codex": False,
        "executed_anything": executed_anything,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "writes_research_action_queue": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "controlled_validation_authorized": authorized,
        "live_or_paper_execution_authorized": False,
        "runner_adapter_status": "connected" if runner_connected else "not_connected",
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
        "controlled_validation_bridge": {
            "report_kind": active_bridge_snapshot.get("report_kind")
            if isinstance(active_bridge_snapshot, dict)
            else None,
            "final_recommendation": active_bridge_snapshot.get("final_recommendation")
            if isinstance(active_bridge_snapshot, dict)
            else None,
            "ready": controlled_validation_bridge_ready,
            "readiness": bridge_readiness,
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
            "connected": runner_connected,
            "max_campaigns": QRE_CONTROLLED_EVAL_MAX_CAMPAIGNS,
            "timeout_seconds_per_campaign": timeout_seconds_per_campaign,
            "poll_seconds": QRE_CONTROLLED_EVAL_DEFAULT_POLL_SECONDS,
            "reason": (
                "runner adapter connected and invoked"
                if runner_connected
                else "runner adapter not connected unless explicitly requested"
            ),
        },
        "controlled_eval_result": runner_result,
        "campaign_invariant_preflight": campaign_invariant_preflight,
        "would_write_artifacts": [
            "logs/qre_controlled_validation_execution/latest.json",
            *_runner_report_paths().values(),
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
    parser.add_argument("--connect-runner-adapter", action="store_true")
    parser.add_argument(
        "--timeout-seconds-per-campaign",
        type=int,
        default=QRE_CONTROLLED_EVAL_DEFAULT_TIMEOUT_SECONDS,
    )
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
        connect_runner_adapter=bool(args.connect_runner_adapter),
        timeout_seconds_per_campaign=int(args.timeout_seconds_per_campaign),
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
    "CONTROLLED_EVAL_REPORT_JSON",
    "CONTROLLED_EVAL_REPORT_MD",
    "EXECUTION_AUTHORIZED_RUNNER_NOT_CONNECTED",
    "EXECUTION_COMPLETED",
    "EXECUTION_FAILED",
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
