from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
GAP_REGISTRY_PATH = Path("generated_research/alpha_discovery/capability_gaps/latest.json")
BLOCKED_EXPERIMENTS_PATH = Path("generated_research/alpha_discovery/blocked_experiments/latest.json")
LEASE_PATH = REPO_ROOT / "logs/qre_research_supervisor/lease.json"
STATUS_PATH = REPO_ROOT / "logs/qre_research_supervisor/latest.json"
HEALTHCHECK_PATH = REPO_ROOT / "logs/qre_research_supervisor/healthcheck.json"
SOURCE_QUALIFICATIONS_PATH = REPO_ROOT / "generated_research/alpha_discovery/source_qualifications/latest.json"
SERVICE_VERSION = "qre_alpha_supervisor_pr4_v1"
DEFAULT_INTERVAL_SECONDS = 300
MAX_INTERVAL_SECONDS = 3600
DEFAULT_MAX_ITERATIONS = 1
HEALTH_BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
HEALTH_BLOCKED_CREDENTIAL = "BLOCKED_CREDENTIAL"
HEALTH_BLOCKED_LICENSE = "BLOCKED_LICENSE"
HEALTH_BLOCKED_SOURCE_CERTIFICATION = "BLOCKED_SOURCE_CERTIFICATION"
HEALTH_HEALTHY_RESEARCH_ACTIVE = "HEALTHY_RESEARCH_ACTIVE"
HEALTH_HEALTHY_WAITING = "HEALTHY_WAITING_FOR_TRIGGER"
HEALTH_DEGRADED_STATE_EPOCH_MISMATCH = "DEGRADED_STATE_EPOCH_MISMATCH"

_STOP = False


def _contracts() -> Any:
    return importlib.import_module("packages.qre_research.alpha_discovery.contracts")


def _runner() -> Any:
    return importlib.import_module("packages.qre_research.alpha_discovery.runner")


def _snapshot_lineage_module() -> Any:
    return importlib.import_module("packages.qre_research.alpha_discovery.snapshot_lineage")


def content_id(prefix: str, payload: Any) -> str:
    return _contracts().content_id(prefix, payload)


def load_snapshot_lineage(repo_root: Path) -> dict[str, Any]:
    return _snapshot_lineage_module().load_snapshot_lineage(repo_root)


def read_status(repo_root: Path) -> dict[str, Any]:
    return _runner().read_status(repo_root)


def run_alpha_discovery_mvp(*, repo_root: Path, dry_run: bool, max_hypotheses: int, execution_tier: str) -> dict[str, Any]:
    return _runner().run_alpha_discovery_mvp(
        repo_root=repo_root,
        dry_run=dry_run,
        max_hypotheses=max_hypotheses,
        execution_tier=execution_tier,
    )


def _signal_handler(signum, frame) -> None:
    global _STOP
    _STOP = True


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _write_status(payload: dict[str, Any]) -> None:
    _atomic_json(STATUS_PATH, payload)
    _atomic_json(HEALTHCHECK_PATH, {"health": payload.get("health"), "generated_at_utc": _utcnow(), "content_identity": content_id("qhealth", payload.get("health"))})


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    delay = 0.05
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.5)


def _acquire_lease() -> dict[str, Any] | None:
    now = datetime.now(UTC)
    current = _read_json(LEASE_PATH)
    if current is not None:
        expires = str(current.get("expires_at_utc") or "")
        try:
            if datetime.fromisoformat(expires.replace("Z", "+00:00")) > now:
                return None
        except ValueError:
            pass
    lease = {
        "lease_id": content_id("qlease", now.isoformat()),
        "acquired_at_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (now + timedelta(minutes=10)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "content_identity": content_id("qleasec", now.isoformat()),
    }
    _atomic_json(LEASE_PATH, lease)
    return lease


def _release_lease(lease: dict[str, Any] | None) -> None:
    if lease is None:
        return
    current = _read_json(LEASE_PATH)
    if current and current.get("lease_id") == lease.get("lease_id"):
        with suppress(OSError):
            LEASE_PATH.unlink()


def _open_gaps() -> list[dict[str, Any]]:
    payload = _read_json(GAP_REGISTRY_PATH) or {}
    return [dict(row) for row in payload.get("rows") or [] if isinstance(row, dict) and str(row.get("status") or "").upper() != "RESOLVED"]


def _blocked_experiments() -> list[dict[str, Any]]:
    payload = _read_json(BLOCKED_EXPERIMENTS_PATH) or {}
    return [dict(row) for row in payload.get("rows") or [] if isinstance(row, dict)]


def _blocked_retry_due(blocked: list[dict[str, Any]]) -> bool:
    now = datetime.now(UTC)
    for row in blocked:
        next_retry = str(row.get("next_retry_after_utc") or "")
        if not next_retry:
            return True
        try:
            if datetime.fromisoformat(next_retry.replace("Z", "+00:00")) <= now:
                return True
        except ValueError:
            return True
    return False


def _qualification_rows() -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    payload = _read_json(SOURCE_QUALIFICATIONS_PATH) or {}
    rows = tuple(dict(row) for row in payload.get("rows") or [] if isinstance(row, dict))
    return payload, rows


def _health_from_run(run_payload: dict[str, Any], open_gaps: list[dict[str, Any]]) -> str:
    disposition = str(run_payload.get("legacy_terminal_disposition") or run_payload.get("terminal_disposition") or "")
    execution_status = str(run_payload.get("execution_status") or "")
    if disposition == "STOPPED_CREDENTIAL_BOUNDARY":
        return HEALTH_BLOCKED_CREDENTIAL
    if disposition == "STOPPED_LICENSE_BOUNDARY":
        return HEALTH_BLOCKED_LICENSE
    if disposition == "STOPPED_SOURCE_CERTIFICATION_BOUNDARY":
        return HEALTH_BLOCKED_SOURCE_CERTIFICATION
    if open_gaps:
        return HEALTH_BLOCKED_CAPABILITY
    if execution_status == "COMPLETED" or disposition.startswith("COMPLETED_"):
        return HEALTH_HEALTHY_RESEARCH_ACTIVE
    return HEALTH_HEALTHY_WAITING


def run_cycle(
    *,
    repo_root: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    lease = _acquire_lease()
    if lease is None:
        payload = {
            "service_version": SERVICE_VERSION,
            "health": HEALTH_HEALTHY_WAITING,
            "current_stage": "SKIPPED_ACTIVE_LEASE",
            "last_cycle": {"decision": "skip_due_to_active_lease", "generated_at_utc": _utcnow()},
            "content_identity": content_id("qsupskip", _utcnow()),
        }
        _write_status(payload)
        return payload
    try:
        lineage = load_snapshot_lineage(repo_root)
        prior_status = _read_json(STATUS_PATH) or {}
        source_qualifications, qualification_rows = _qualification_rows()
        alpha_status = read_status(repo_root)
        open_gaps = _open_gaps()
        blocked = _blocked_experiments()
        blocked_retry_due = _blocked_retry_due(blocked)
        current_watermarks = {
            "snapshot_lineage": lineage.get("snapshot_lineage", {}).get("content_identity"),
            "source_qualifications": source_qualifications.get("content_identity"),
            "open_gap_ids": sorted(str(row.get("gap_id") or "") for row in open_gaps),
        }
        prior_watermarks = prior_status.get("watermarks") if isinstance(prior_status.get("watermarks"), dict) else {}
        qualified_snapshot_ids = {str(row.get("dataset_snapshot_id") or "") for row in qualification_rows if str(row.get("dataset_snapshot_id") or "")}
        epoch_mismatch_reasons: list[str] = []
        if str(alpha_status.get("runtime_epoch_id") or "") and str(prior_status.get("runtime_epoch_id") or "") and alpha_status.get("runtime_epoch_id") != prior_status.get("runtime_epoch_id"):
            epoch_mismatch_reasons.append("runtime_epoch_mismatch")
        if str(alpha_status.get("qualification_set_id") or "") and str(source_qualifications.get("content_identity") or "") and alpha_status.get("qualification_set_id") != source_qualifications.get("content_identity"):
            epoch_mismatch_reasons.append("qualification_set_mismatch")
        if str(alpha_status.get("snapshot_lineage_set_id") or "") and str(lineage.get("snapshot_lineage", {}).get("content_identity") or "") and alpha_status.get("snapshot_lineage_set_id") != lineage.get("snapshot_lineage", {}).get("content_identity"):
            epoch_mismatch_reasons.append("snapshot_lineage_set_mismatch")
        alpha_snapshot = str(alpha_status.get("current_dataset_snapshot") or "")
        if alpha_snapshot and alpha_snapshot not in qualified_snapshot_ids:
            epoch_mismatch_reasons.append("snapshot_not_in_current_qualifications")
        if str(prior_status.get("current_campaign") or "") and str(alpha_status.get("current_campaign") or "") and prior_status.get("current_campaign") != alpha_status.get("current_campaign"):
            epoch_mismatch_reasons.append("current_campaign_mismatch")
        if str(prior_status.get("current_dataset_snapshot") or "") and str(alpha_status.get("current_dataset_snapshot") or "") and prior_status.get("current_dataset_snapshot") != alpha_status.get("current_dataset_snapshot"):
            epoch_mismatch_reasons.append("current_snapshot_mismatch")
        if str(prior_status.get("current_source_tier") or "") and str(alpha_status.get("current_source_tier") or "") and prior_status.get("current_source_tier") != alpha_status.get("current_source_tier"):
            epoch_mismatch_reasons.append("current_source_tier_mismatch")
        epoch_mismatch = bool(epoch_mismatch_reasons)
        if epoch_mismatch:
            payload = {
                "service_version": SERVICE_VERSION,
                "health": HEALTH_DEGRADED_STATE_EPOCH_MISMATCH,
                "current_stage": "DEGRADED_EPOCH_MISMATCH",
                "last_cycle": {
                    "decision": "blocked_due_to_epoch_mismatch",
                    "generated_at_utc": _utcnow(),
                    "reason_codes": tuple(dict.fromkeys(epoch_mismatch_reasons)),
                },
                "last_successful_cycle": prior_status.get("last_successful_cycle"),
                "current_dataset_snapshot": alpha_status.get("current_dataset_snapshot"),
                "current_source_tier": alpha_status.get("current_source_tier"),
                "current_experiment": alpha_status.get("current_experiment"),
                "current_campaign": alpha_status.get("current_campaign"),
                "open_gaps": tuple(str(row.get("gap_id") or "") for row in open_gaps),
                "active_ADE_requests": tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
                "operator_actions": ("reconcile_runtime_epoch",),
                "next_retry": (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "consecutive_failures": 1,
                "watermarks": current_watermarks,
                "leases": lease,
                "artifact_refs": {
                    "alpha_status": str(repo_root / Path("generated_research/alpha_discovery/status/latest.json")),
                    "supervisor_status": str(STATUS_PATH),
                },
                "runtime_epoch_id": alpha_status.get("runtime_epoch_id"),
                "qualification_set_id": source_qualifications.get("content_identity"),
                "snapshot_lineage_set_id": lineage.get("snapshot_lineage", {}).get("content_identity"),
                "content_identity": content_id("qsupdegraded", {"reason_codes": tuple(dict.fromkeys(epoch_mismatch_reasons)), "watermarks": current_watermarks}),
                "blocked_experiments": blocked,
                "search_ledger_id": alpha_status.get("search_ledger_id"),
            }
            _write_status(payload)
            return payload
        comparable_prior = {key: prior_watermarks.get(key) for key in current_watermarks}
        if comparable_prior == current_watermarks and not blocked_retry_due:
            payload = {
                "service_version": SERVICE_VERSION,
                "health": HEALTH_HEALTHY_WAITING,
                "current_stage": "NO_CHANGE_SKIP",
                "last_cycle": {"decision": "no_material_change", "generated_at_utc": _utcnow()},
                "last_successful_cycle": prior_status.get("last_successful_cycle"),
                "watermarks": current_watermarks,
                "leases": lease,
                "content_identity": content_id("qsupnoop", current_watermarks),
            }
            _write_status(payload)
            return payload
        run_payload = run_alpha_discovery_mvp(repo_root=repo_root, dry_run=dry_run, max_hypotheses=3, execution_tier="screening")
        open_gaps = _open_gaps()
        blocked = _blocked_experiments()
        current_watermarks = {
            "snapshot_lineage": lineage.get("snapshot_lineage", {}).get("content_identity"),
            "source_qualifications": source_qualifications.get("content_identity"),
            "open_gap_ids": sorted(str(row.get("gap_id") or "") for row in open_gaps),
        }
        health = _health_from_run(run_payload, open_gaps)
        status = {
            "service_version": SERVICE_VERSION,
            "last_cycle": {
                "run_id": run_payload.get("run_id"),
                "terminal_disposition": run_payload.get("terminal_disposition"),
                "generated_at_utc": _utcnow(),
            },
            "last_successful_cycle": {
                "run_id": run_payload.get("run_id"),
                "terminal_disposition": run_payload.get("terminal_disposition"),
            } if str(run_payload.get("terminal_disposition") or "").startswith(("COMPLETED_", "DRY_RUN")) else None,
            "current_stage": "COMPLETE",
            "current_dataset_snapshot": run_payload.get("current_dataset_snapshot"),
            "current_source_tier": str(run_payload.get("current_source_tier") or "SOURCE_BLOCKED"),
            "current_experiment": run_payload.get("current_experiment"),
            "current_campaign": run_payload.get("current_campaign"),
            "open_gaps": tuple(str(row.get("gap_id") or "") for row in open_gaps),
            "active_ADE_requests": tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
            "operator_actions": tuple(
                sorted(
                    {
                        "configure_provider_credentials" if str(row.get("gap_type") or "") == "CREDENTIAL_GAP" else
                        "resolve_license_boundary" if str(row.get("gap_type") or "") == "LICENSE_GAP" else
                        "review_source_certification" if str(row.get("gap_type") or "") == "SOURCE_CERTIFICATION_GAP" else
                        "review_blocked_experiment"
                        for row in open_gaps
                    }
                )
            ),
            "next_retry": (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "consecutive_failures": 0 if health.startswith("HEALTHY") else 1,
            "watermarks": {**current_watermarks, "alpha_status": alpha_status.get("content_identity")},
            "leases": lease,
            "artifact_refs": {
                "alpha_status": str(repo_root / Path("generated_research/alpha_discovery/status/latest.json")),
                "supervisor_status": str(STATUS_PATH),
            },
            "runtime_epoch_id": run_payload.get("runtime_epoch_id"),
            "qualification_set_id": run_payload.get("qualification_set_id"),
            "snapshot_lineage_set_id": run_payload.get("snapshot_lineage_set_id"),
            "health": health,
            "content_identity": content_id("qsup", {"run_id": run_payload.get("run_id"), "health": health, "blocked": len(blocked)}),
        }
        payload = {
            **status,
            "blocked_experiments": blocked,
            "search_ledger_id": run_payload.get("search_ledger_id"),
        }
        _write_status(payload)
        return payload
    finally:
        _release_lease(lease)


def _print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded QRE alpha research supervisor")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    return parser


def main(argv: list[str] | None = None) -> int:
    global _STOP
    parser = _parser()
    args = parser.parse_args(argv)
    if args.status:
        _print_json(_read_json(STATUS_PATH) or {"health": "NOT_AVAILABLE"})
        return 0
    if args.healthcheck:
        payload = _read_json(HEALTHCHECK_PATH) or {"health": "FAILED"}
        _print_json(payload)
        return 0 if str(payload.get("health") or "").startswith(("HEALTHY", "DEGRADED", "BLOCKED")) else 1

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    interval = max(30, min(int(args.interval_seconds or DEFAULT_INTERVAL_SECONDS), MAX_INTERVAL_SECONDS))
    iterations = max(1, int(args.max_iterations or DEFAULT_MAX_ITERATIONS))

    if args.run_once or not args.loop:
        _print_json(run_cycle(repo_root=args.repo_root, dry_run=bool(args.dry_run)))
        return 0

    payload = {}
    for _ in range(iterations):
        if _STOP:
            break
        payload = run_cycle(repo_root=args.repo_root, dry_run=bool(args.dry_run))
        if _STOP:
            break
        time.sleep(interval)
    _print_json(payload or {"health": "FAILED"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
