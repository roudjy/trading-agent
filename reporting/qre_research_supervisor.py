from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.qre_research.alpha_discovery.capability_loop import BLOCKED_EXPERIMENTS_PATH, GAP_REGISTRY_PATH
from packages.qre_research.alpha_discovery.contracts import (
    HEALTH_BLOCKED_CAPABILITY,
    HEALTH_BLOCKED_CREDENTIAL,
    HEALTH_BLOCKED_LICENSE,
    HEALTH_BLOCKED_SOURCE_CERTIFICATION,
    HEALTH_HEALTHY_RESEARCH_ACTIVE,
    HEALTH_HEALTHY_WAITING,
    SupervisorStatus,
    content_id,
)
from packages.qre_research.alpha_discovery.runner import read_status, run_alpha_discovery_mvp
from packages.qre_research.alpha_discovery.snapshot_lineage import load_snapshot_lineage

REPO_ROOT = Path(__file__).resolve().parent.parent
LEASE_PATH = REPO_ROOT / "logs/qre_research_supervisor/lease.json"
STATUS_PATH = REPO_ROOT / "logs/qre_research_supervisor/latest.json"
HEALTHCHECK_PATH = REPO_ROOT / "logs/qre_research_supervisor/healthcheck.json"
SOURCE_QUALIFICATIONS_PATH = REPO_ROOT / "generated_research/alpha_discovery/source_qualifications/latest.json"
SERVICE_VERSION = "qre_alpha_supervisor_pr4_v1"
DEFAULT_INTERVAL_SECONDS = 300
MAX_INTERVAL_SECONDS = 3600
DEFAULT_MAX_ITERATIONS = 1

_STOP = False


def _signal_handler(signum, frame) -> None:  # noqa: ANN001, ARG001
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
    os.replace(tmp, path)


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


def _health_from_run(run_payload: dict[str, Any], open_gaps: list[dict[str, Any]]) -> str:
    disposition = str(run_payload.get("terminal_disposition") or "")
    if disposition == "STOPPED_CREDENTIAL_BOUNDARY":
        return HEALTH_BLOCKED_CREDENTIAL
    if disposition == "STOPPED_LICENSE_BOUNDARY":
        return HEALTH_BLOCKED_LICENSE
    if disposition == "STOPPED_SOURCE_CERTIFICATION_BOUNDARY":
        return HEALTH_BLOCKED_SOURCE_CERTIFICATION
    if open_gaps:
        return HEALTH_BLOCKED_CAPABILITY
    if disposition.startswith("COMPLETED_"):
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
        source_qualifications = _read_json(SOURCE_QUALIFICATIONS_PATH) or {}
        open_gaps = _open_gaps()
        blocked = _blocked_experiments()
        current_watermarks = {
            "snapshot_lineage": lineage.get("snapshot_lineage", {}).get("content_identity"),
            "source_qualifications": source_qualifications.get("content_identity"),
            "open_gap_ids": sorted(str(row.get("gap_id") or "") for row in open_gaps),
        }
        prior_watermarks = prior_status.get("watermarks") if isinstance(prior_status.get("watermarks"), dict) else {}
        comparable_prior = {key: prior_watermarks.get(key) for key in current_watermarks}
        if comparable_prior == current_watermarks and not blocked:
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
        alpha_status = read_status(repo_root)
        health = _health_from_run(run_payload, open_gaps)
        status = SupervisorStatus(
            service_version=SERVICE_VERSION,
            last_cycle={
                "run_id": run_payload.get("run_id"),
                "terminal_disposition": run_payload.get("terminal_disposition"),
                "generated_at_utc": _utcnow(),
            },
            last_successful_cycle={
                "run_id": run_payload.get("run_id"),
                "terminal_disposition": run_payload.get("terminal_disposition"),
            } if str(run_payload.get("terminal_disposition") or "").startswith(("COMPLETED_", "DRY_RUN")) else None,
            current_stage="COMPLETE",
            current_dataset_snapshot=((run_payload.get("artifacts") or {}).get("source_resolution") or {}).get("selected_snapshot"),
            current_source_tier=str((((run_payload.get("artifacts") or {}).get("source_resolution") or {}).get("current_source_tier")) or "SOURCE_BLOCKED"),
            current_experiment=run_payload.get("experiment_id"),
            current_campaign=run_payload.get("campaign_id"),
            open_gaps=tuple(str(row.get("gap_id") or "") for row in open_gaps),
            active_ADE_requests=tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
            operator_actions=tuple(
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
            next_retry=(datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            next_scheduled_cycle=(datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            consecutive_failures=0 if health.startswith("HEALTHY") else 1,
            watermarks={**current_watermarks, "alpha_status": alpha_status.get("content_identity")},
            leases=lease,
            artifact_refs={
                "alpha_status": str(repo_root / Path("generated_research/alpha_discovery/status/latest.json")),
                "supervisor_status": str(STATUS_PATH),
            },
            health=health,
            content_identity=content_id("qsup", {"run_id": run_payload.get("run_id"), "health": health, "blocked": len(blocked)}),
        )
        payload = {
            **asdict(status),  # type: ignore[name-defined]
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
