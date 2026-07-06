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
RUNTIME_EPOCH_PATH = REPO_ROOT / "generated_research/alpha_discovery/runtime_epoch/latest.json"
SOURCE_RESOLUTION_PATH = REPO_ROOT / "generated_research/alpha_discovery/source_resolution/latest.json"
OBSERVATIONS_PATH = REPO_ROOT / "generated_research/alpha_discovery/observations/latest.json"
RUNS_PATH = Path("generated_research/alpha_discovery/runs/latest.json")
SEARCH_LEDGER_PATH = Path("generated_research/alpha_discovery/search_ledger/latest.json")
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
HEALTH_DEGRADED_LEGACY_STATE_INCOMPLETE = "DEGRADED_LEGACY_STATE_INCOMPLETE"
HEALTH_DEGRADED_LEGACY_STATE_INCONSISTENT = "DEGRADED_LEGACY_STATE_INCONSISTENT"

_STOP = False


def _contracts() -> Any:
    return importlib.import_module("packages.qre_research.alpha_discovery.contracts")


def _runner() -> Any:
    return importlib.import_module("packages.qre_research.alpha_discovery.runner")


def _snapshot_lineage_module() -> Any:
    return importlib.import_module("packages.qre_research.alpha_discovery.snapshot_lineage")


def content_id(prefix: str, payload: Any) -> str:
    return _contracts().content_id(prefix, payload)


def canonical_payload(value: Any) -> Any:
    return _contracts().canonical_payload(value)


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
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
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


def _watermarks(*, snapshot_lineage_set_id: str, qualification_set_id: str, open_gaps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "snapshot_lineage": snapshot_lineage_set_id,
        "source_qualifications": qualification_set_id,
        "open_gap_ids": sorted(str(row.get("gap_id") or "") for row in open_gaps),
    }


def _operator_actions(open_gaps: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "configure_provider_credentials" if str(row.get("gap_type") or "") == "CREDENTIAL_GAP" else
                "resolve_license_boundary" if str(row.get("gap_type") or "") == "LICENSE_GAP" else
                "review_source_certification" if str(row.get("gap_type") or "") == "SOURCE_CERTIFICATION_GAP" else
                "review_blocked_experiment"
                for row in open_gaps
            }
        )
    )


def _semantic_gap_rows(open_gaps: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    rows = [
        canonical_payload(
            {
                "gap_id": str(row.get("gap_id") or ""),
                "experiment_id": str(row.get("experiment_id") or ""),
                "gap_type": str(row.get("gap_type") or ""),
                "status": str(row.get("status") or ""),
                "request_id": str(row.get("request_id") or ""),
                "deduplication_key": str(row.get("deduplication_key") or ""),
                "content_identity": str(row.get("content_identity") or ""),
            }
        )
        for row in open_gaps
    ]
    return tuple(sorted(rows, key=lambda row: (str(row.get("gap_id") or ""), str(row.get("experiment_id") or ""), str(row.get("gap_type") or ""))))


def _semantic_blocked_rows(blocked: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    rows = [
        canonical_payload(
            {
                "experiment_id": str(row.get("experiment_id") or ""),
                "hypothesis_id": str(row.get("hypothesis_id") or ""),
                "strategy_spec_id": str(row.get("strategy_spec_id") or ""),
                "preregistration_id": str(row.get("preregistration_id") or ""),
                "blocked_stage": str(row.get("blocked_stage") or ""),
                "gap_ids": tuple(sorted(str(value) for value in row.get("gap_ids") or () if str(value))),
                "required_data_snapshot": str(row.get("required_data_snapshot") or ""),
                "required_source_tier": str(row.get("required_source_tier") or ""),
                "required_primitive": str(row.get("required_primitive") or ""),
                "required_executor": str(row.get("required_executor") or ""),
                "current_status": str(row.get("current_status") or ""),
                "resume_token": str(row.get("resume_token") or ""),
                "content_identity": str(row.get("content_identity") or ""),
            }
        )
        for row in blocked
    ]
    return tuple(sorted(rows, key=lambda row: (str(row.get("experiment_id") or ""), str(row.get("resume_token") or ""))))


def _source_resolution_state(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / Path("generated_research/alpha_discovery/source_resolution/latest.json")) or {}
    rows = payload.get("rows") or []
    if not rows or not isinstance(rows[0], dict):
        return {}
    row = dict(rows[0])
    return canonical_payload(
        {
            "resolution_id": str(row.get("resolution_id") or ""),
            "selected_source": str(row.get("selected_source") or ""),
            "selected_snapshot": str(row.get("selected_snapshot") or ""),
            "current_source_tier": str(row.get("current_source_tier") or ""),
            "target_source_tier": str(row.get("target_source_tier") or ""),
            "qualification_actions": tuple(sorted(str(value) for value in row.get("qualification_actions") or () if str(value))),
            "candidate_sources": tuple(sorted(str(value) for value in row.get("candidate_sources") or () if str(value))),
            "credential_requirements": tuple(sorted(str(value) for value in row.get("credential_requirements") or () if str(value))),
            "license_requirements": tuple(sorted(str(value) for value in row.get("license_requirements") or () if str(value))),
            "cross_source_requirements": tuple(sorted(str(value) for value in row.get("cross_source_requirements") or () if str(value))),
            "unresolved_blockers": tuple(sorted(str(value) for value in row.get("unresolved_blockers") or () if str(value))),
            "operator_action_required": bool(row.get("operator_action_required")),
            "automatic_actions_allowed": bool(row.get("automatic_actions_allowed")),
            "content_identity": str(row.get("content_identity") or payload.get("content_identity") or ""),
        }
    )


def _observation_inventory_state(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / Path("generated_research/alpha_discovery/observations/latest.json")) or {}
    if not payload:
        return {}
    return canonical_payload(
        {
            "primitive_inventory": payload.get("primitive_inventory") or {},
            "executor_inventory": payload.get("executor_inventory") or {},
            "data_coverage": payload.get("data_coverage") or {},
            "source_quality": payload.get("source_quality") or {},
            "identity_readiness": str(payload.get("identity_readiness") or ""),
        }
    )


def _semantic_cycle_inputs(
    *,
    snapshot_lineage_set_id: str,
    qualification_set_id: str,
    open_gaps: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    source_resolution_state: dict[str, Any],
    observation_state: dict[str, Any],
    alpha_status: dict[str, Any],
) -> dict[str, Any]:
    return canonical_payload(
        {
            "snapshot_lineage_set_id": snapshot_lineage_set_id,
            "qualification_set_id": qualification_set_id,
            "open_gaps": _semantic_gap_rows(open_gaps),
            "blocked_experiments": _semantic_blocked_rows(blocked),
            "source_resolution": source_resolution_state,
            "observation_state": observation_state,
            "authority_state": {
                "requested_execution_tier": str(alpha_status.get("requested_execution_tier") or ""),
                "admitted_execution_tier": str(alpha_status.get("admitted_execution_tier") or ""),
                "current_source_tier": str(alpha_status.get("current_source_tier") or ""),
                "terminal_disposition": str(alpha_status.get("terminal_disposition") or alpha_status.get("legacy_terminal_disposition") or ""),
                "scientific_disposition": str(alpha_status.get("scientific_disposition") or ""),
                "evidence_tier_reached": str(alpha_status.get("evidence_tier_reached") or ""),
                "execution_status": str(alpha_status.get("execution_status") or ""),
            },
        }
    )


def _semantic_cycle_identity(**kwargs: Any) -> str:
    return content_id("qsupsem", _semantic_cycle_inputs(**kwargs))


def _validate_status_publication(payload: dict[str, Any]) -> None:
    watermarks = payload.get("watermarks") if isinstance(payload.get("watermarks"), dict) else {}
    qualification_set_id = str(payload.get("qualification_set_id") or "")
    snapshot_lineage_set_id = str(payload.get("snapshot_lineage_set_id") or "")
    if qualification_set_id and str(watermarks.get("source_qualifications") or "") not in {"", qualification_set_id}:
        raise ValueError("supervisor_status_publication_requires_matching_source_qualification_watermark")
    if snapshot_lineage_set_id and str(watermarks.get("snapshot_lineage") or "") not in {"", snapshot_lineage_set_id}:
        raise ValueError("supervisor_status_publication_requires_matching_snapshot_lineage_watermark")


def _publish_status(payload: dict[str, Any]) -> None:
    _validate_status_publication(payload)
    _write_status(payload)


def _qualification_rows() -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    payload = _read_json(SOURCE_QUALIFICATIONS_PATH) or {}
    rows = tuple(dict(row) for row in payload.get("rows") or [] if isinstance(row, dict))
    return payload, rows


def _runtime_epoch_payload(*, alpha_status: dict[str, Any], qualification_set_id: str, snapshot_lineage_set_id: str) -> dict[str, Any]:
    run_id = str(alpha_status.get("run_id") or alpha_status.get("search_run_id") or "")
    campaign_id = str(alpha_status.get("campaign_id") or alpha_status.get("current_campaign") or "")
    runtime_epoch_components = {
        "snapshot_lineage_set_id": snapshot_lineage_set_id,
        "qualification_set_id": qualification_set_id,
        "alpha_run_id": run_id,
        "alpha_campaign_id": campaign_id,
    }
    return {
        "runtime_epoch_id": content_id("qepoch", runtime_epoch_components),
        "qualification_set_id": qualification_set_id,
        "snapshot_lineage_set_id": snapshot_lineage_set_id,
        "run_id": run_id,
        "campaign_id": campaign_id,
        "content_identity": content_id("qepochstate", runtime_epoch_components),
    }


def _read_runtime_epoch_state() -> dict[str, Any]:
    payload = _read_json(RUNTIME_EPOCH_PATH) or {}
    return payload if isinstance(payload, dict) else {}


def _read_current_run_state(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / RUNS_PATH) or {}
    return payload if isinstance(payload, dict) else {}


def _ledger_artifact_identity(repo_root: Path) -> tuple[str, bool]:
    path = repo_root / SEARCH_LEDGER_PATH
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return "", path.is_file()
    candidates: list[str] = []
    for key in ("search_ledger_id", "search_run_id", "ledger_id"):
        value = str(payload.get(key) or "")
        if value:
            candidates.append(value)
    ledger = payload.get("ledger")
    if isinstance(ledger, dict):
        for key in ("search_ledger_id", "search_run_id", "ledger_id"):
            value = str(ledger.get(key) or "")
            if value:
                candidates.append(value)
    rows = payload.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("search_ledger_id", "search_run_id", "ledger_id"):
                value = str(row.get(key) or "")
                if value:
                    candidates.append(value)
    unique = tuple(dict.fromkeys(candidates))
    return (unique[0], True) if len(unique) == 1 else ("", True)


def _reconstruct_legacy_search_ledger_id(
    *,
    repo_root: Path,
    alpha_status: dict[str, Any],
    persisted_runtime_epoch: dict[str, Any],
) -> tuple[str | None, tuple[str, ...]]:
    runtime_ledger_id = str(persisted_runtime_epoch.get("search_ledger_id") or "")
    run_ledger_id = str(_read_current_run_state(repo_root).get("search_ledger_id") or "")
    artifact_ledger_id, artifact_present = _ledger_artifact_identity(repo_root)
    status_ledger_id = str(alpha_status.get("search_ledger_id") or "")
    source_ids = {
        "runtime_epoch": runtime_ledger_id,
        "run": run_ledger_id,
        "search_ledger": artifact_ledger_id,
        "status": status_ledger_id,
    }
    nonempty_ids = {value for value in source_ids.values() if value}
    if len(nonempty_ids) > 1:
        return None, ("legacy_search_ledger_identity_mismatch",)
    if runtime_ledger_id and artifact_present and not artifact_ledger_id:
        return None, ("legacy_search_ledger_identity_mismatch",)
    if run_ledger_id and artifact_present and not artifact_ledger_id:
        return None, ("legacy_search_ledger_identity_mismatch",)
    if nonempty_ids:
        return sorted(nonempty_ids)[0], ()
    return None, ()


def _artifact_rows(repo_root: Path, relative: str) -> tuple[dict[str, Any], ...]:
    payload = _read_json(repo_root / Path(relative)) or {}
    return tuple(dict(row) for row in payload.get("rows") or [] if isinstance(row, dict))


def _legacy_blocked_state_validation(
    *,
    repo_root: Path,
    prior_status: dict[str, Any],
    alpha_status: dict[str, Any],
    persisted_runtime_epoch: dict[str, Any],
    current_watermarks: dict[str, Any],
    qualification_rows: tuple[dict[str, Any], ...],
    open_gaps: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    snapshot_lineage_set_id: str,
    qualification_set_id: str,
) -> tuple[bool, str, tuple[str, ...]]:
    reasons: list[str] = []
    inconsistent: list[str] = []
    prior_watermarks = prior_status.get("watermarks") if isinstance(prior_status.get("watermarks"), dict) else {}
    comparable_prior = {key: prior_watermarks.get(key) for key in current_watermarks}
    if comparable_prior != current_watermarks:
        inconsistent.append("legacy_watermarks_do_not_match_current_inputs")
    if not blocked:
        reasons.append("legacy_blocked_experiments_missing")
    if not open_gaps:
        reasons.append("legacy_open_gaps_missing")
    if not snapshot_lineage_set_id:
        reasons.append("legacy_snapshot_lineage_missing")
    if not qualification_set_id:
        reasons.append("legacy_qualification_set_missing")
    if str(alpha_status.get("current_source_tier") or "") != "SOURCE_BLOCKED":
        inconsistent.append("legacy_source_tier_not_blocked")
    if alpha_status.get("current_campaign") or prior_status.get("current_campaign"):
        inconsistent.append("legacy_campaign_present")
    if any(row.get("request_id") for row in open_gaps):
        inconsistent.append("legacy_active_ade_request_present")
    screening_eligible = {
        str(row.get("dataset_snapshot_id") or "")
        for row in qualification_rows
        if str(row.get("allowed_evidence_tier") or "").upper() == "SOURCE_SCREENING_ELIGIBLE"
        or str(row.get("qualification_status") or "").upper() in {"SCREENING_ELIGIBLE", "QUALIFIED"}
    }
    if screening_eligible:
        inconsistent.append("legacy_screening_eligible_source_present")
    epoch_qualification = str(persisted_runtime_epoch.get("qualification_set_id") or alpha_status.get("qualification_set_id") or "")
    epoch_lineage = str(persisted_runtime_epoch.get("snapshot_lineage_set_id") or alpha_status.get("snapshot_lineage_set_id") or "")
    if not str(persisted_runtime_epoch.get("runtime_epoch_id") or alpha_status.get("runtime_epoch_id") or prior_status.get("runtime_epoch_id") or ""):
        reasons.append("legacy_runtime_epoch_missing")
    if epoch_qualification and epoch_qualification != qualification_set_id:
        inconsistent.append("legacy_runtime_epoch_qualification_mismatch")
    if epoch_lineage and epoch_lineage != snapshot_lineage_set_id:
        inconsistent.append("legacy_runtime_epoch_lineage_mismatch")
    hypotheses = _artifact_rows(repo_root, "generated_research/alpha_discovery/hypotheses/latest.json")
    experiments = _artifact_rows(repo_root, "generated_research/alpha_discovery/experiments/latest.json")
    hypothesis_ids = {str(row.get("hypothesis_id") or "") for row in hypotheses}
    experiment_ids = {str(row.get("experiment_id") or "") for row in experiments}
    gap_by_id = {str(row.get("gap_id") or ""): row for row in open_gaps}
    if blocked and not hypotheses:
        reasons.append("legacy_hypotheses_missing")
    if blocked and not experiments:
        reasons.append("legacy_experiments_missing")
    for row in blocked:
        experiment_id = str(row.get("experiment_id") or "")
        hypothesis_id = str(row.get("hypothesis_id") or "")
        if not experiment_id or experiment_id not in experiment_ids:
            inconsistent.append("legacy_blocked_experiment_record_missing")
        if not hypothesis_id or hypothesis_id not in hypothesis_ids:
            inconsistent.append("legacy_blocked_hypothesis_record_missing")
        for gap_id in tuple(str(value) for value in row.get("gap_ids") or () if str(value)):
            gap = gap_by_id.get(gap_id)
            if not gap:
                inconsistent.append("legacy_blocked_gap_missing")
                continue
            if str(gap.get("experiment_id") or "") not in {"", experiment_id}:
                inconsistent.append("legacy_gap_experiment_mismatch")
    if reasons:
        return False, HEALTH_DEGRADED_LEGACY_STATE_INCOMPLETE, tuple(dict.fromkeys(reasons))
    if inconsistent:
        return False, HEALTH_DEGRADED_LEGACY_STATE_INCONSISTENT, tuple(dict.fromkeys(inconsistent))
    return True, "", ()


def _is_semantically_coherent_epoch(
    *,
    mismatch_reasons: list[str],
    alpha_status: dict[str, Any],
    prior_status: dict[str, Any],
    qualified_snapshot_ids: set[str],
) -> bool:
    if not mismatch_reasons:
        return False
    if any(
        reason
        not in {
            "runtime_epoch_mismatch",
            "qualification_set_mismatch",
            "snapshot_lineage_set_mismatch",
        }
        for reason in mismatch_reasons
    ):
        return False
    alpha_snapshot = str(alpha_status.get("current_dataset_snapshot") or "")
    if alpha_snapshot and alpha_snapshot not in qualified_snapshot_ids:
        return False
    for field in ("current_campaign", "current_dataset_snapshot", "current_source_tier"):
        prior_value = str(prior_status.get(field) or "")
        alpha_value = str(alpha_status.get(field) or "")
        if prior_value and alpha_value and prior_value != alpha_value:
            return False
    return True


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
        persisted_runtime_epoch = _read_runtime_epoch_state()
        reconstructed_search_ledger_id, search_ledger_reasons = _reconstruct_legacy_search_ledger_id(
            repo_root=repo_root,
            alpha_status=alpha_status,
            persisted_runtime_epoch=persisted_runtime_epoch,
        )
        epoch_state = persisted_runtime_epoch or alpha_status
        open_gaps = _open_gaps()
        blocked = _blocked_experiments()
        blocked_retry_due = _blocked_retry_due(blocked)
        snapshot_lineage_set_id = str(lineage.get("snapshot_lineage", {}).get("content_identity") or "")
        qualification_set_id = str(source_qualifications.get("content_identity") or "")
        current_watermarks = _watermarks(
            snapshot_lineage_set_id=snapshot_lineage_set_id,
            qualification_set_id=qualification_set_id,
            open_gaps=open_gaps,
        )
        source_resolution_state = _source_resolution_state(repo_root)
        observation_state = _observation_inventory_state(repo_root)
        semantic_input_identity = _semantic_cycle_identity(
            snapshot_lineage_set_id=snapshot_lineage_set_id,
            qualification_set_id=qualification_set_id,
            open_gaps=open_gaps,
            blocked=blocked,
            source_resolution_state=source_resolution_state,
            observation_state=observation_state,
            alpha_status=alpha_status,
        )
        prior_watermarks = prior_status.get("watermarks") if isinstance(prior_status.get("watermarks"), dict) else {}
        prior_semantic_input_identity = str(prior_status.get("semantic_input_identity") or "")
        qualified_snapshot_ids = {str(row.get("dataset_snapshot_id") or "") for row in qualification_rows if str(row.get("dataset_snapshot_id") or "")}
        epoch_mismatch_reasons: list[str] = []
        if str(epoch_state.get("runtime_epoch_id") or "") and str(prior_status.get("runtime_epoch_id") or "") and epoch_state.get("runtime_epoch_id") != prior_status.get("runtime_epoch_id"):
            epoch_mismatch_reasons.append("runtime_epoch_mismatch")
        if str(epoch_state.get("qualification_set_id") or "") and str(source_qualifications.get("content_identity") or "") and epoch_state.get("qualification_set_id") != source_qualifications.get("content_identity"):
            epoch_mismatch_reasons.append("qualification_set_mismatch")
        if str(epoch_state.get("snapshot_lineage_set_id") or "") and str(lineage.get("snapshot_lineage", {}).get("content_identity") or "") and epoch_state.get("snapshot_lineage_set_id") != lineage.get("snapshot_lineage", {}).get("content_identity"):
            epoch_mismatch_reasons.append("snapshot_lineage_set_mismatch")
        if str(persisted_runtime_epoch.get("qualification_set_id") or "") and str(source_qualifications.get("content_identity") or "") and persisted_runtime_epoch.get("qualification_set_id") != source_qualifications.get("content_identity"):
            epoch_mismatch_reasons.append("persisted_qualification_set_mismatch")
        if str(persisted_runtime_epoch.get("snapshot_lineage_set_id") or "") and str(lineage.get("snapshot_lineage", {}).get("content_identity") or "") and persisted_runtime_epoch.get("snapshot_lineage_set_id") != lineage.get("snapshot_lineage", {}).get("content_identity"):
            epoch_mismatch_reasons.append("persisted_snapshot_lineage_set_mismatch")
        alpha_snapshot = str(alpha_status.get("current_dataset_snapshot") or "")
        if alpha_snapshot and alpha_snapshot not in qualified_snapshot_ids:
            epoch_mismatch_reasons.append("snapshot_not_in_current_qualifications")
        if str(prior_status.get("current_campaign") or "") and str(alpha_status.get("current_campaign") or "") and prior_status.get("current_campaign") != alpha_status.get("current_campaign"):
            epoch_mismatch_reasons.append("current_campaign_mismatch")
        if str(prior_status.get("current_dataset_snapshot") or "") and str(alpha_status.get("current_dataset_snapshot") or "") and prior_status.get("current_dataset_snapshot") != alpha_status.get("current_dataset_snapshot"):
            epoch_mismatch_reasons.append("current_snapshot_mismatch")
        if str(prior_status.get("current_source_tier") or "") and str(alpha_status.get("current_source_tier") or "") and prior_status.get("current_source_tier") != alpha_status.get("current_source_tier"):
            epoch_mismatch_reasons.append("current_source_tier_mismatch")
        source_improvement_trigger = bool(
            prior_semantic_input_identity
            and str(prior_watermarks.get("source_qualifications") or "")
            and str(prior_watermarks.get("source_qualifications") or "") != qualification_set_id
            and any(str(row.get("allowed_evidence_tier") or "") in {"SOURCE_SCREENING_ELIGIBLE", "SOURCE_VALIDATION_ELIGIBLE"} for row in qualification_rows)
        )
        if source_improvement_trigger:
            epoch_mismatch_reasons = [reason for reason in epoch_mismatch_reasons if reason != "qualification_set_mismatch"]
        epoch_mismatch = bool(epoch_mismatch_reasons)
        if prior_status and not prior_semantic_input_identity and blocked:
            legacy_valid, legacy_health, legacy_reasons = _legacy_blocked_state_validation(
                repo_root=repo_root,
                prior_status=prior_status,
                alpha_status=alpha_status,
                persisted_runtime_epoch=persisted_runtime_epoch,
                current_watermarks=current_watermarks,
                qualification_rows=qualification_rows,
                open_gaps=open_gaps,
                blocked=blocked,
                snapshot_lineage_set_id=snapshot_lineage_set_id,
                qualification_set_id=qualification_set_id,
            )
            if legacy_valid and search_ledger_reasons:
                legacy_valid = False
                legacy_health = HEALTH_DEGRADED_LEGACY_STATE_INCONSISTENT
                legacy_reasons = search_ledger_reasons
            if legacy_valid:
                runtime_epoch_id = str(persisted_runtime_epoch.get("runtime_epoch_id") or alpha_status.get("runtime_epoch_id") or prior_status.get("runtime_epoch_id") or "")
                health = _health_from_run(alpha_status, open_gaps)
                payload = {
                    "service_version": SERVICE_VERSION,
                    "health": health,
                    "current_stage": "LEGACY_SEMANTIC_IDENTITY_MIGRATED",
                    "last_cycle": {
                        "decision": "semantic_identity_backfilled_no_change",
                        "generated_at_utc": _utcnow(),
                        "reason_codes": ("legacy_semantic_identity_missing", "semantic_inputs_reconstructed_from_persisted_artifacts"),
                    },
                    "last_successful_cycle": prior_status.get("last_successful_cycle"),
                    "current_dataset_snapshot": alpha_status.get("current_dataset_snapshot"),
                    "current_source_tier": alpha_status.get("current_source_tier"),
                    "current_experiment": alpha_status.get("current_experiment"),
                    "current_campaign": alpha_status.get("current_campaign"),
                    "open_gaps": tuple(str(row.get("gap_id") or "") for row in open_gaps),
                    "active_ADE_requests": tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
                    "operator_actions": _operator_actions(open_gaps),
                    "next_retry": prior_status.get("next_retry"),
                    "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "consecutive_failures": 0 if health.startswith("HEALTHY") else 1,
                    "watermarks": current_watermarks,
                    "leases": lease,
                    "runtime_epoch_id": runtime_epoch_id,
                    "qualification_set_id": qualification_set_id,
                    "snapshot_lineage_set_id": snapshot_lineage_set_id,
                    "search_ledger_id": reconstructed_search_ledger_id,
                    "semantic_input_identity": semantic_input_identity,
                    "blocked_experiments": blocked,
                    "content_identity": content_id("qsuplegacy", {"semantic_input_identity": semantic_input_identity, "health": health}),
                }
                _publish_status(payload)
                return payload
            payload = {
                "service_version": SERVICE_VERSION,
                "health": legacy_health,
                "current_stage": legacy_health,
                "last_cycle": {
                    "decision": "fail_closed_legacy_state_not_migrated",
                    "generated_at_utc": _utcnow(),
                    "reason_codes": legacy_reasons,
                },
                "last_successful_cycle": prior_status.get("last_successful_cycle"),
                "current_dataset_snapshot": alpha_status.get("current_dataset_snapshot"),
                "current_source_tier": alpha_status.get("current_source_tier"),
                "current_experiment": alpha_status.get("current_experiment"),
                "current_campaign": alpha_status.get("current_campaign"),
                "open_gaps": tuple(str(row.get("gap_id") or "") for row in open_gaps),
                "active_ADE_requests": tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
                "operator_actions": ("repair_legacy_supervisor_state",),
                "next_retry": prior_status.get("next_retry"),
                "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "consecutive_failures": int(prior_status.get("consecutive_failures") or 0) + 1,
                "watermarks": current_watermarks,
                "leases": lease,
                "runtime_epoch_id": str(persisted_runtime_epoch.get("runtime_epoch_id") or alpha_status.get("runtime_epoch_id") or prior_status.get("runtime_epoch_id") or ""),
                "qualification_set_id": qualification_set_id,
                "snapshot_lineage_set_id": snapshot_lineage_set_id,
                "search_ledger_id": None if search_ledger_reasons else reconstructed_search_ledger_id,
                "blocked_experiments": blocked,
                "content_identity": content_id("qsuplegacydegraded", {"reason_codes": legacy_reasons, "watermarks": current_watermarks}),
            }
            _publish_status(payload)
            return payload
        if blocked and search_ledger_reasons:
            payload = {
                "service_version": SERVICE_VERSION,
                "health": HEALTH_DEGRADED_LEGACY_STATE_INCONSISTENT,
                "current_stage": HEALTH_DEGRADED_LEGACY_STATE_INCONSISTENT,
                "last_cycle": {
                    "decision": "fail_closed_legacy_state_not_migrated",
                    "generated_at_utc": _utcnow(),
                    "reason_codes": search_ledger_reasons,
                },
                "last_successful_cycle": prior_status.get("last_successful_cycle"),
                "current_dataset_snapshot": alpha_status.get("current_dataset_snapshot"),
                "current_source_tier": alpha_status.get("current_source_tier"),
                "current_experiment": alpha_status.get("current_experiment"),
                "current_campaign": alpha_status.get("current_campaign"),
                "open_gaps": tuple(str(row.get("gap_id") or "") for row in open_gaps),
                "active_ADE_requests": tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
                "operator_actions": ("repair_legacy_supervisor_state",),
                "next_retry": prior_status.get("next_retry"),
                "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "consecutive_failures": int(prior_status.get("consecutive_failures") or 0) + 1,
                "watermarks": current_watermarks,
                "leases": lease,
                "runtime_epoch_id": str(persisted_runtime_epoch.get("runtime_epoch_id") or alpha_status.get("runtime_epoch_id") or prior_status.get("runtime_epoch_id") or ""),
                "qualification_set_id": qualification_set_id,
                "snapshot_lineage_set_id": snapshot_lineage_set_id,
                "search_ledger_id": None,
                "blocked_experiments": blocked,
                "content_identity": content_id("qsuplegacydegraded", {"reason_codes": search_ledger_reasons, "watermarks": current_watermarks}),
            }
            _publish_status(payload)
            return payload
        if _is_semantically_coherent_epoch(
            mismatch_reasons=epoch_mismatch_reasons,
            alpha_status=alpha_status,
            prior_status=prior_status,
            qualified_snapshot_ids=qualified_snapshot_ids,
        ):
            reconciled_epoch = _runtime_epoch_payload(
                alpha_status=alpha_status,
                qualification_set_id=str(source_qualifications.get("content_identity") or ""),
                snapshot_lineage_set_id=str(lineage.get("snapshot_lineage", {}).get("content_identity") or ""),
            )
            _atomic_json(RUNTIME_EPOCH_PATH, reconciled_epoch)
            payload = {
                "service_version": SERVICE_VERSION,
                "health": HEALTH_HEALTHY_WAITING,
                "current_stage": "COHERENT_EPOCH_RECONCILED",
                "last_cycle": {
                    "decision": "reconciled_semantically_coherent_epoch",
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
                "operator_actions": _operator_actions(open_gaps),
                "next_retry": (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "consecutive_failures": 0,
                "watermarks": {**current_watermarks, "alpha_status": alpha_status.get("content_identity")},
                "leases": lease,
                "artifact_refs": {
                    "alpha_status": str(repo_root / Path("generated_research/alpha_discovery/status/latest.json")),
                    "supervisor_status": str(STATUS_PATH),
                    "runtime_epoch": str(RUNTIME_EPOCH_PATH),
                },
                "runtime_epoch_id": reconciled_epoch["runtime_epoch_id"],
                "qualification_set_id": reconciled_epoch["qualification_set_id"],
                "snapshot_lineage_set_id": reconciled_epoch["snapshot_lineage_set_id"],
                "content_identity": content_id("qsupreconcile", {"watermarks": current_watermarks, "epoch": reconciled_epoch["content_identity"]}),
                "semantic_input_identity": semantic_input_identity,
                "blocked_experiments": blocked,
                "search_ledger_id": alpha_status.get("search_ledger_id"),
            }
            _publish_status(payload)
            return payload
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
                    "runtime_epoch": str(RUNTIME_EPOCH_PATH),
                },
                "runtime_epoch_id": alpha_status.get("runtime_epoch_id"),
                "qualification_set_id": source_qualifications.get("content_identity"),
                "snapshot_lineage_set_id": lineage.get("snapshot_lineage", {}).get("content_identity"),
                "content_identity": content_id("qsupdegraded", {"reason_codes": tuple(dict.fromkeys(epoch_mismatch_reasons)), "watermarks": current_watermarks}),
                "semantic_input_identity": semantic_input_identity,
                "blocked_experiments": blocked,
                "search_ledger_id": alpha_status.get("search_ledger_id"),
            }
            _publish_status(payload)
            return payload
        comparable_prior = {key: prior_watermarks.get(key) for key in current_watermarks}
        if prior_semantic_input_identity == semantic_input_identity or (
            comparable_prior == current_watermarks and not blocked_retry_due
        ):
            health = _health_from_run(alpha_status, open_gaps)
            payload = {
                "service_version": SERVICE_VERSION,
                "health": health,
                "current_stage": "NO_CHANGE_SKIP",
                "last_cycle": {
                    "decision": "no_material_change",
                    "generated_at_utc": _utcnow(),
                    "reason_codes": ("semantic_inputs_unchanged",) if prior_semantic_input_identity == semantic_input_identity else ("watermarks_unchanged",),
                },
                "last_successful_cycle": prior_status.get("last_successful_cycle"),
                "current_dataset_snapshot": alpha_status.get("current_dataset_snapshot"),
                "current_source_tier": alpha_status.get("current_source_tier"),
                "current_experiment": alpha_status.get("current_experiment"),
                "current_campaign": alpha_status.get("current_campaign"),
                "open_gaps": tuple(str(row.get("gap_id") or "") for row in open_gaps),
                "active_ADE_requests": tuple(str(row.get("request_id") or "") for row in open_gaps if row.get("request_id")),
                "operator_actions": _operator_actions(open_gaps),
                "next_retry": prior_status.get("next_retry"),
                "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "consecutive_failures": 0 if health.startswith("HEALTHY") else 1,
                "watermarks": current_watermarks,
                "leases": lease,
                "runtime_epoch_id": str(persisted_runtime_epoch.get("runtime_epoch_id") or alpha_status.get("runtime_epoch_id") or ""),
                "qualification_set_id": qualification_set_id,
                "snapshot_lineage_set_id": snapshot_lineage_set_id,
                "search_ledger_id": reconstructed_search_ledger_id,
                "semantic_input_identity": semantic_input_identity,
                "blocked_experiments": blocked,
                "content_identity": content_id("qsupnoop", {"semantic_input_identity": semantic_input_identity, "health": health}),
            }
            _publish_status(payload)
            return payload
        run_payload = run_alpha_discovery_mvp(repo_root=repo_root, dry_run=dry_run, max_hypotheses=3, execution_tier="screening")
        open_gaps = _open_gaps()
        blocked = _blocked_experiments()
        current_watermarks = _watermarks(
            snapshot_lineage_set_id=str(run_payload.get("snapshot_lineage_set_id") or snapshot_lineage_set_id),
            qualification_set_id=str(run_payload.get("qualification_set_id") or qualification_set_id),
            open_gaps=open_gaps,
        )
        semantic_input_identity = _semantic_cycle_identity(
            snapshot_lineage_set_id=str(run_payload.get("snapshot_lineage_set_id") or snapshot_lineage_set_id),
            qualification_set_id=str(run_payload.get("qualification_set_id") or qualification_set_id),
            open_gaps=open_gaps,
            blocked=blocked,
            source_resolution_state=_source_resolution_state(repo_root),
            observation_state=_observation_inventory_state(repo_root),
            alpha_status=run_payload,
        )
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
            "operator_actions": _operator_actions(open_gaps),
            "next_retry": (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "next_scheduled_cycle": (datetime.now(UTC) + timedelta(seconds=DEFAULT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "consecutive_failures": 0 if health.startswith("HEALTHY") else 1,
            "watermarks": {**current_watermarks, "alpha_status": run_payload.get("content_identity")},
            "leases": lease,
            "artifact_refs": {
                "alpha_status": str(repo_root / Path("generated_research/alpha_discovery/status/latest.json")),
                "supervisor_status": str(STATUS_PATH),
            },
            "runtime_epoch_id": run_payload.get("runtime_epoch_id"),
            "qualification_set_id": run_payload.get("qualification_set_id"),
            "snapshot_lineage_set_id": run_payload.get("snapshot_lineage_set_id"),
            "health": health,
            "semantic_input_identity": semantic_input_identity,
            "content_identity": content_id("qsup", {"run_id": run_payload.get("run_id"), "health": health, "blocked": len(blocked)}),
        }
        payload = {
            **status,
            "blocked_experiments": blocked,
            "search_ledger_id": run_payload.get("search_ledger_id"),
        }
        _publish_status(payload)
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
        return 0 if str(payload.get("health") or "").startswith(("HEALTHY", "BLOCKED")) else 1

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
