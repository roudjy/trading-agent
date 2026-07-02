from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_hypothesis_generation as a20
from packages.qre_research import generated_hypothesis_paths as ghp
from packages.qre_research import generated_strategy_paths as gsp
from packages.qre_research import hypothesis_lifecycle as qhl
from packages.qre_research import second_preregistered_campaign as spc
from reporting import execution_authority as ea
from reporting import qre_development_intake_promotion as qdip
from reporting import qre_development_queue_admission_policy as qdap

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-036.1"
REPORT_KIND: Final[str] = "qre_autonomous_opportunity_loop"
POLICY_VERSION: Final[str] = "qre_opportunity_loop_policy_v1"

STATE_VALUES: Final[tuple[str, ...]] = (
    "WAITING_FOR_TRIGGER",
    "MATERIAL_CHANGE_CHECK",
    "OPPORTUNITY_DISCOVERY",
    "HYPOTHESIS_GENERATION",
    "HYPOTHESIS_ADMISSION",
    "CAMPAIGN_CELL_MATERIALIZATION",
    "PORTFOLIO_ADMISSION",
    "EMPIRICAL_EXECUTION",
    "EVIDENCE_AND_LEARNING",
    "NO_MATERIAL_CHANGE",
    "NO_ELIGIBLE_OPPORTUNITY",
    "ADE_REQUEST_CREATED",
    "WAITING_FOR_CAPABILITY",
    "OPERATOR_REVIEW_REQUIRED",
    "READY_FOR_SYNTHESIS",
    "OPERATOR_GATE",
    "WAITING_FOR_NOVELTY",
    "RESEARCH_EXECUTED",
    "CAPABILITY_REQUESTED",
)
PRECHECK_STATUSES: Final[tuple[str, ...]] = (
    "NO_MATERIAL_CHANGE",
    "MATERIAL_DATA_CHANGE",
    "RESEARCH_CONTEXT_CHANGE",
    "CAPABILITY_CHANGE",
    "POLICY_CHANGE",
    "MULTIPLE_MATERIAL_CHANGES",
)
TRIGGER_TYPES: Final[tuple[str, ...]] = (
    "NEW_COMPLETE_MARKET_DATA",
    "NEW_USABLE_OOS_WINDOW",
    "MATERIAL_DATASET_CHANGE",
    "SOURCE_QUALITY_CHANGE",
    "IDENTITY_CHANGE",
    "NEW_ADMISSIBLE_UNIVERSE",
    "NEW_CANONICAL_TIMEFRAME",
    "NEW_REGIME_SEGMENT",
    "NEW_FALSIFICATION_CONTROL",
    "NEW_CANONICAL_PRIMITIVE",
    "CAPABILITY_GAP_RESOLVED",
    "COOLDOWN_EXPIRED",
    "NEW_HYPOTHESIS_TEMPLATE",
    "NEW_CONTRADICTORY_EVIDENCE",
)
HYPOTHESIS_ADMISSION_STATUSES: Final[tuple[str, ...]] = (
    "HYPOTHESIS_ADMITTED",
    "HYPOTHESIS_DUPLICATE",
    "HYPOTHESIS_NEAR_DUPLICATE",
    "HYPOTHESIS_DATA_BLOCKED",
    "HYPOTHESIS_IDENTITY_BLOCKED",
    "HYPOTHESIS_PRIMITIVE_BLOCKED",
    "HYPOTHESIS_EXECUTOR_BLOCKED",
    "HYPOTHESIS_POLICY_BLOCKED",
    "HYPOTHESIS_EXTERNAL_BOUNDARY",
)
CAPABILITY_GAP_CLASSES: Final[tuple[str, ...]] = (
    "DATA_AVAILABILITY_WAIT",
    "EXTERNAL_DATA_BOUNDARY",
    "SOURCE_QUALITY_GAP",
    "IDENTITY_GAP",
    "CACHE_CAPABILITY_GAP",
    "PRIMITIVE_CAPABILITY_GAP",
    "EXECUTOR_CAPABILITY_GAP",
    "DIAGNOSTIC_CAPABILITY_GAP",
    "ORCHESTRATION_CAPABILITY_GAP",
    "POLICY_OR_GOVERNANCE_GATE",
    "INSUFFICIENT_EMPIRICAL_EVIDENCE",
    "MECHANISM_CONTRADICTION",
    "LOW_SIGNAL_DENSITY",
    "DUPLICATE_RESEARCH_PATH",
)
REQUEST_STATUSES: Final[tuple[str, ...]] = (
    "PROPOSED",
    "DEDUPLICATED",
    "AUTHORITY_CLASSIFIED",
    "AUTO_ALLOWED",
    "NEEDS_HUMAN",
    "PERMANENTLY_DENIED",
    "EXTERNAL_BOUNDARY",
    "MERGED",
    "RESOLVED",
    "SUPERSEDED",
)
INPUT_CLASSES: Final[tuple[str, ...]] = (
    "EXTERNAL_MARKET_STATE",
    "CANONICAL_SOURCE_STATE",
    "CANONICAL_IDENTITY_STATE",
    "CANONICAL_POLICY_STATE",
    "CANONICAL_PRIMITIVE_STATE",
    "CANONICAL_HYPOTHESIS_TEMPLATE_STATE",
    "ADE_EXTERNAL_RESOLUTION_STATE",
    "QRE_LOOP_OUTPUT",
    "QRE_GENERATED_HYPOTHESIS_OUTPUT",
    "QRE_CAPABILITY_REQUEST_OUTPUT",
    "QRE_REPORTING_OUTPUT",
    "REPLAY_OR_STATUS_OUTPUT",
)
NON_MATERIAL_INPUT_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "QRE_LOOP_OUTPUT",
        "QRE_GENERATED_HYPOTHESIS_OUTPUT",
        "QRE_CAPABILITY_REQUEST_OUTPUT",
        "QRE_REPORTING_OUTPUT",
        "REPLAY_OR_STATUS_OUTPUT",
    }
)
BOOTSTRAP_BASELINE: Final[str] = "BOOTSTRAP_BASELINE"
SELF_TRIGGER_FALSE_POSITIVE_REASON: Final[str] = "SELF_TRIGGER_FALSE_POSITIVE"
LOOP_OUTPUT_NOT_AUTHORIZED_REASON: Final[str] = "LOOP_OUTPUT_NOT_AUTHORIZED_AS_CAPABILITY_TRIGGER"
KNOWN_FALSE_POSITIVE_REQUEST_ID: Final[str] = "qrdr_b5264c941dcf3e88"

DEFAULT_LIMITS: Final[dict[str, int]] = {
    "maximum_cycles_per_run": 3,
    "maximum_generated_hypotheses_per_cycle": 8,
    "maximum_campaign_cells_per_run": 8,
    "maximum_campaign_executions_per_run": 3,
}
LOCK_LEASE_SECONDS: Final[int] = 900

REPO_ROOT: Final[Path] = gsp.REPO_ROOT
LOOP_ROOT: Final[Path] = Path("generated_research/orchestration/opportunity_loop")
WATERMARK_PATH: Final[Path] = LOOP_ROOT / "watermark" / "external_input_watermark.v1.json"
PRECHECK_PATH: Final[Path] = LOOP_ROOT / "watermark" / "material_change_detection.v1.json"
OPPORTUNITIES_PATH: Final[Path] = LOOP_ROOT / "registry" / "research_opportunity_registry.v1.json"
HYPOTHESIS_BATCH_PATH: Final[Path] = LOOP_ROOT / "registry" / "generated_hypothesis_batch.v1.json"
HYPOTHESIS_NOVELTY_PATH: Final[Path] = LOOP_ROOT / "registry" / "hypothesis_novelty_decisions.v1.json"
CAMPAIGN_CELL_PATH: Final[Path] = LOOP_ROOT / "registry" / "campaign_cell_registry.v1.json"
CAMPAIGN_CELL_NOVELTY_PATH: Final[Path] = LOOP_ROOT / "registry" / "campaign_cell_novelty_decisions.v1.json"
STATE_PATH: Final[Path] = LOOP_ROOT / "status" / "opportunity_loop_state.v1.json"
RUN_PATH: Final[Path] = LOOP_ROOT / "status" / "opportunity_loop_run.v1.json"
LOCK_PATH: Final[Path] = LOOP_ROOT / "status" / "opportunity_loop_lock.v1.json"
OUTPUT_CHECKPOINT_PATH: Final[Path] = LOOP_ROOT / "status" / "loop_output_checkpoint.v1.json"
LATEST_RUN_SUMMARY_PATH: Final[Path] = LOOP_ROOT / "status" / "latest_run_summary.v1.json"
GAP_REGISTRY_PATH: Final[Path] = LOOP_ROOT / "registry" / "capability_gap_registry.v1.json"
ADE_REQUESTS_PATH: Final[Path] = LOOP_ROOT / "registry" / "ade_development_requests.v1.json"
ADE_FEEDBACK_PATH: Final[Path] = LOOP_ROOT / "registry" / "ade_request_resolution_feedback.v1.json"
REQUEST_LIFECYCLE_PATH: Final[Path] = LOOP_ROOT / "registry" / "ade_request_lifecycle.v1.json"
CONTINUATION_PLAN_PATH: Final[Path] = LOOP_ROOT / "status" / "research_continuation_plan.v1.json"
ROOT_CAUSE_PATH: Final[Path] = LOOP_ROOT / "diagnostics" / "self_trigger_root_cause.v1.json"
PROPOSAL_INTAKE_PATH: Final[Path] = Path("logs/qre_research_action_proposal_intake/latest.json")


@dataclass(frozen=True)
class LoopLock:
    run_id: str
    lease_expires_at_utc: str


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _repo_path(path: Path, *, repo_root: Path) -> Path:
    return repo_root / path


def _validate_write_target(path: Path, *, repo_root: Path) -> None:
    try:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"opportunity loop write escaped repo root: {path}") from exc
    if relative == PROPOSAL_INTAKE_PATH.as_posix():
        return
    if not any(relative.startswith(prefix) for prefix in gsp.WRITE_PREFIXES):
        raise ValueError(f"opportunity loop write outside canonical generated surface: {relative}")


def _atomic_write(path: Path, payload: str, *, repo_root: Path) -> None:
    _validate_write_target(path, repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        if path.read_text(encoding="utf-8-sig") == payload:
            return
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_036.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _write_json(path: Path, payload: dict[str, Any], *, repo_root: Path) -> None:
    _atomic_write(
        _repo_path(path, repo_root=repo_root),
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        repo_root=repo_root,
    )


def _read_json(path: Path, *, repo_root: Path) -> dict[str, Any] | None:
    file_path = _repo_path(path, repo_root=repo_root)
    if not file_path.is_file():
        return None
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path, *, repo_root: Path, keys: tuple[str, ...] = ("rows",)) -> list[dict[str, Any]]:
    payload = _read_json(path, repo_root=repo_root)
    if payload is None:
        return []
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _load_cache_manifest(repo_root: Path) -> dict[str, Any]:
    return _read_json(Path("logs/qre_data_cache_manifest/latest.json"), repo_root=repo_root) or {}


def _load_source_quality(repo_root: Path) -> dict[str, Any]:
    return _read_json(Path("logs/qre_data_source_quality_readiness/latest.json"), repo_root=repo_root) or {}


def _load_portfolio_rows(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(
        Path("generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json"),
        repo_root=repo_root,
    )


def _load_strategy_registry(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(Path("generated_research/registry/generated_strategy_registry.v1.json"), repo_root=repo_root)


def _load_primitive_registry(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(
        Path("generated_research/primitives/registry/generated_primitive_registry.v1.json"),
        repo_root=repo_root,
    )


def _load_identity_rows(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(
        Path("generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json"),
        repo_root=repo_root,
    )


def _load_research_memory(repo_root: Path) -> dict[str, Any]:
    return _read_json(ghp.RESEARCH_MEMORY_PATH, repo_root=repo_root) or {}


def _load_trust_continuation(repo_root: Path) -> dict[str, Any]:
    return _read_json(
        Path("generated_research/orchestration/trust_closure/research_continuation_plan.v1.json"),
        repo_root=repo_root,
    ) or {}


def _load_shadow_readiness(repo_root: Path) -> dict[str, Any]:
    return _read_json(
        Path("generated_research/orchestration/trust_closure/shadow_readiness.v1.json"),
        repo_root=repo_root,
    ) or {}


def _load_empirical_history(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(
        Path("generated_research/campaign_execution/evidence/empirical_campaign_history.v1.json"),
        repo_root=repo_root,
    )


def _load_oos_consumption(repo_root: Path) -> dict[str, Any]:
    return _read_json(Path("generated_research/campaign_execution/ledgers/oos_consumption.v1.json"), repo_root=repo_root) or {}


def _semantic_normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _semantic_normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_semantic_normalize(item) for item in value]
        if all(isinstance(item, dict | list | str | int | float | bool) or item is None for item in normalized):
            return sorted(normalized, key=_stable_json)
        return normalized
    return value


def _semantic_digest(value: Any) -> str:
    return stable_digest(_semantic_normalize(value))


def _external_input_descriptor(
    *,
    input_class: str,
    canonical_owner: str,
    producer: str,
    scope: str,
    eligible_as_material_trigger: bool,
    eligible_trigger_types: list[str],
    value: Any,
) -> dict[str, Any]:
    payload = {
        "input_class": input_class,
        "canonical_owner": canonical_owner,
        "producer": producer,
        "scope": scope,
        "eligible_as_material_trigger": eligible_as_material_trigger,
        "eligible_trigger_types": eligible_trigger_types,
        "semantic_content_identity": _semantic_digest(value),
        "canonical_entity_identity": _content_id(
            "qrei",
            {
                "owner": canonical_owner,
                "scope": scope,
                "class": input_class,
            },
        ),
        "canonical_version": POLICY_VERSION,
        "effective_state": _semantic_normalize(value),
    }
    payload["content_identity"] = _content_id("qred", payload)
    return payload


def _tracked_request_statuses(previous_checkpoint: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(previous_checkpoint, dict):
        return {}
    tracked = previous_checkpoint.get("tracked_request_statuses")
    if not isinstance(tracked, dict):
        return {}
    return {
        str(request_id): str(status or "")
        for request_id, status in tracked.items()
        if str(request_id or "")
    }


def _canonical_resolution_state(
    *,
    repo_root: Path,
    previous_checkpoint: dict[str, Any] | None,
) -> dict[str, str]:
    tracked = _tracked_request_statuses(previous_checkpoint)
    if not tracked:
        return {}
    work_queue = _read_json(Path("logs/development_work_queue/latest.json"), repo_root=repo_root) or {}
    items = work_queue.get("items") if isinstance(work_queue.get("items"), list) else []
    resolved_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {"done", "archived"}:
            continue
        text = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("notes") or ""),
                str(item.get("item_id") or ""),
            ]
        )
        for request_id in tracked:
            if request_id and request_id in text:
                resolved_ids.add(request_id)
    return {
        request_id: ("RESOLVED" if request_id in resolved_ids else str(status or "PENDING"))
        for request_id, status in tracked.items()
    }


def _load_root_cause_payload(*, repo_root: Path, previous_checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    generated_thesis = _read_json(ghp.GENERATED_THESIS_REGISTRY_PATH, repo_root=repo_root) or {}
    generated_requests = _read_json(ADE_REQUESTS_PATH, repo_root=repo_root) or {}
    generated_feedback = _read_json(ADE_FEEDBACK_PATH, repo_root=repo_root) or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_opportunity_loop_self_trigger_root_cause",
        "affected_invocation": 2,
        "false_request_id": KNOWN_FALSE_POSITIVE_REQUEST_ID,
        "rows": [
            {
                "trigger_type": "NEW_HYPOTHESIS_TEMPLATE",
                "source_artifact": ghp.GENERATED_THESIS_REGISTRY_PATH.as_posix(),
                "artifact_producer": "packages.qre_research.automated_hypothesis_generation",
                "artifact_owner": "QRE generated hypothesis output",
                "previous_identity": "",
                "current_identity": _semantic_digest(generated_thesis),
                "why_it_changed": "invocation_1_generated_hypotheses_rewrote_the_generated_thesis_registry",
                "loop_authored": True,
                "externally_authoritative": False,
                "incorrect_material_reason": "generated hypothesis output was folded into hypothesis_catalog_version",
            },
            {
                "trigger_type": "CAPABILITY_GAP_RESOLVED",
                "source_artifact": ADE_REQUESTS_PATH.as_posix(),
                "artifact_producer": "packages.qre_research.autonomous_opportunity_loop",
                "artifact_owner": "QRE capability request output",
                "previous_identity": "",
                "current_identity": _semantic_digest(
                    {
                        "requests": generated_requests,
                        "feedback": generated_feedback,
                        "tracked_request_statuses": _tracked_request_statuses(previous_checkpoint),
                    }
                ),
                "why_it_changed": "invocation_1_created_or_rewrote_loop_authored_capability_request_artifacts",
                "loop_authored": True,
                "externally_authoritative": False,
                "incorrect_material_reason": "loop request artifacts were folded into capability_inventory_version",
            },
        ],
        "content_identity": "",
    }


def _watermark_components(
    repo_root: Path,
    *,
    previous_checkpoint: dict[str, Any] | None,
) -> dict[str, Any]:
    cache_manifest = _load_cache_manifest(repo_root)
    source_quality = _load_source_quality(repo_root)
    portfolio_rows = _load_portfolio_rows(repo_root)
    primitive_rows = _load_primitive_registry(repo_root)
    research_memory = _load_research_memory(repo_root)
    identity_rows = _load_identity_rows(repo_root)
    empirical_history = _load_empirical_history(repo_root)
    source_identities = {
        str(row.get("cache_kind") or ""): str(row.get("status") or "")
        for row in cache_manifest.get("cache_roots", [])
        if isinstance(row, dict)
    }
    dataset_fingerprints = {
        f"{row.get('source')}|{row.get('instrument')}|{row.get('timeframe')}": str(row.get("content_hash") or "")
        for row in cache_manifest.get("coverage", [])
        if isinstance(row, dict)
    }
    latest_complete_bar = {
        f"{row.get('source')}|{row.get('instrument')}|{row.get('timeframe')}": str(row.get("max_timestamp_utc") or "")
        for row in cache_manifest.get("coverage", [])
        if isinstance(row, dict)
    }
    usable_history_end = {
        str(row.get("campaign_cell_id") or ""): str((row.get("validation_window") or {}).get("end") or "")
        for row in portfolio_rows
    }
    usable_oos_end = {
        str(row.get("campaign_cell_id") or ""): str((row.get("oos_window") or {}).get("end") or "")
        for row in portfolio_rows
    }
    quality_status = {
        str(row.get("source") or ""): str(row.get("ready") or row.get("quality_status_counts") or "")
        for row in source_quality.get("sources", [])
        if isinstance(row, dict)
    }
    identity_status = {
        str(row.get("generated_strategy_id") or row.get("source_hypothesis_id") or ""): str(row.get("outcome") or row.get("authority_state") or "")
        for row in identity_rows
    }
    regime_signature = sorted(
        {
            str(regime)
            for row in portfolio_rows
            if isinstance(row, dict)
            for regime in row.get("regime_scope", []) or row.get("regimes", []) or []
            if regime
        }
    )
    ade_resolution_state = _canonical_resolution_state(
        repo_root=repo_root,
        previous_checkpoint=previous_checkpoint,
    )
    capability_inventory_version = _semantic_digest(ade_resolution_state)
    primitive_inventory_version = _semantic_digest(primitive_rows)
    hypothesis_catalog_version = _semantic_digest(
        {
            "manual_snapshot": a20.build_evidence_snapshot(repo_root=repo_root).get("manual_thesis_digest", ""),
        }
    )
    research_memory_version = _semantic_digest(research_memory)
    cooldown_state_version = stable_digest(
        {
            "active_blocker": _load_trust_continuation(repo_root).get("active_blocker"),
            "blocked_cells": _load_trust_continuation(repo_root).get("blocked_cells", []),
        }
    )
    contradictory_evidence = _semantic_digest(
        _read_json(ghp.EVIDENCE_UPDATES_PATH, repo_root=repo_root) or {}
    )
    inputs = [
        _external_input_descriptor(
            input_class="EXTERNAL_MARKET_STATE",
            canonical_owner="logs/qre_data_cache_manifest/latest.json",
            producer="qre_data_cache_manifest",
            scope="market_data",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["NEW_COMPLETE_MARKET_DATA", "MATERIAL_DATASET_CHANGE", "NEW_CANONICAL_TIMEFRAME"],
            value={
                "dataset_fingerprints": dataset_fingerprints,
                "latest_complete_bar_by_asset_timeframe": latest_complete_bar,
                "source_manifest_identities": source_identities,
            },
        ),
        _external_input_descriptor(
            input_class="CANONICAL_SOURCE_STATE",
            canonical_owner="logs/qre_data_source_quality_readiness/latest.json",
            producer="qre_data_source_quality_readiness",
            scope="source_quality",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["SOURCE_QUALITY_CHANGE"],
            value=quality_status,
        ),
        _external_input_descriptor(
            input_class="CANONICAL_IDENTITY_STATE",
            canonical_owner="generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
            producer="autonomous_universe_authority",
            scope="identity_resolution",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["IDENTITY_CHANGE", "NEW_ADMISSIBLE_UNIVERSE", "NEW_USABLE_OOS_WINDOW"],
            value={
                "identity_status_by_universe": identity_status,
                "usable_history_end_by_cell": usable_history_end,
                "usable_oos_end_by_cell": usable_oos_end,
            },
        ),
        _external_input_descriptor(
            input_class="CANONICAL_POLICY_STATE",
            canonical_owner="packages/qre_research/autonomous_opportunity_loop.py",
            producer="policy_constant",
            scope="policy",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["NEW_FALSIFICATION_CONTROL"],
            value={"policy_version": POLICY_VERSION, "cooldown_state_version": cooldown_state_version},
        ),
        _external_input_descriptor(
            input_class="CANONICAL_PRIMITIVE_STATE",
            canonical_owner="generated_research/primitives/registry/generated_primitive_registry.v1.json",
            producer="generated_primitive_registry",
            scope="primitive_inventory",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["NEW_CANONICAL_PRIMITIVE"],
            value={"primitive_inventory_version": primitive_inventory_version},
        ),
        _external_input_descriptor(
            input_class="CANONICAL_HYPOTHESIS_TEMPLATE_STATE",
            canonical_owner="manual_thesis_digest",
            producer="packages.qre_research.automated_hypothesis_generation.build_evidence_snapshot",
            scope="canonical_hypothesis_templates",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["NEW_HYPOTHESIS_TEMPLATE"],
            value={"hypothesis_catalog_version": hypothesis_catalog_version},
        ),
        _external_input_descriptor(
            input_class="ADE_EXTERNAL_RESOLUTION_STATE",
            canonical_owner="logs/development_work_queue/latest.json",
            producer="development_work_queue",
            scope="ade_lifecycle_resolution",
            eligible_as_material_trigger=True,
            eligible_trigger_types=["CAPABILITY_GAP_RESOLVED"],
            value=ade_resolution_state,
        ),
        _external_input_descriptor(
            input_class="QRE_LOOP_OUTPUT",
            canonical_owner=RUN_PATH.as_posix(),
            producer="packages.qre_research.autonomous_opportunity_loop",
            scope="loop_run_summary",
            eligible_as_material_trigger=False,
            eligible_trigger_types=[],
            value={"tracked_request_statuses": _tracked_request_statuses(previous_checkpoint)},
        ),
    ]
    return {
        "watermark_id": "",
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "bootstrap_state": "",
        "source_manifest_identities": source_identities,
        "dataset_fingerprints": dataset_fingerprints,
        "latest_complete_bar_by_asset_timeframe": latest_complete_bar,
        "usable_history_end_by_cell": usable_history_end,
        "usable_oos_end_by_cell": usable_oos_end,
        "quality_status_by_source": quality_status,
        "identity_status_by_universe": identity_status,
        "regime_signature": regime_signature,
        "capability_inventory_version": capability_inventory_version,
        "primitive_inventory_version": primitive_inventory_version,
        "hypothesis_catalog_version": hypothesis_catalog_version,
        "research_memory_version": research_memory_version,
        "cooldown_state_version": cooldown_state_version,
        "latest_empirical_history_identity": stable_digest(empirical_history),
        "contradictory_evidence_identity": contradictory_evidence,
        "ade_resolution_state_by_request": ade_resolution_state,
        "inputs": inputs,
    }


def build_watermark(
    *,
    repo_root: Path,
    previous_state_identity: str = "",
    previous_checkpoint: dict[str, Any] | None = None,
    bootstrap_state: str = "",
) -> dict[str, Any]:
    payload = _watermark_components(repo_root, previous_checkpoint=previous_checkpoint)
    payload["bootstrap_state"] = bootstrap_state
    payload["last_processed_state_identity"] = previous_state_identity
    content_basis = dict(payload)
    content_basis["bootstrap_state"] = ""
    content_basis["last_processed_state_identity"] = ""
    payload["content_identity"] = _content_id("qrow", content_basis)
    payload["watermark_id"] = _content_id("qrwm", payload["content_identity"])
    return payload


def _collect_triggers(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if previous is None:
        return []
    trigger_map = {
        "dataset_fingerprints": "MATERIAL_DATASET_CHANGE",
        "latest_complete_bar_by_asset_timeframe": "NEW_COMPLETE_MARKET_DATA",
        "usable_oos_end_by_cell": "NEW_USABLE_OOS_WINDOW",
        "quality_status_by_source": "SOURCE_QUALITY_CHANGE",
        "identity_status_by_universe": "IDENTITY_CHANGE",
        "regime_signature": "NEW_REGIME_SEGMENT",
        "primitive_inventory_version": "NEW_CANONICAL_PRIMITIVE",
        "capability_inventory_version": "CAPABILITY_GAP_RESOLVED",
        "cooldown_state_version": "COOLDOWN_EXPIRED",
        "hypothesis_catalog_version": "NEW_HYPOTHESIS_TEMPLATE",
        "contradictory_evidence_identity": "NEW_CONTRADICTORY_EVIDENCE",
    }
    triggers: list[str] = []
    for field, trigger in trigger_map.items():
        if previous.get(field) != current.get(field):
            triggers.append(trigger)
    if previous.get("usable_history_end_by_cell") != current.get("usable_history_end_by_cell"):
        triggers.append("NEW_ADMISSIBLE_UNIVERSE")
    if previous.get("source_manifest_identities") != current.get("source_manifest_identities"):
        triggers.append("NEW_CANONICAL_TIMEFRAME")
    return sorted(set(triggers))


def build_precheck(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    triggers = _collect_triggers(previous, current)
    bootstrap = previous is None
    if bootstrap or not triggers:
        status = "NO_MATERIAL_CHANGE"
    elif len(triggers) > 1:
        status = "MULTIPLE_MATERIAL_CHANGES"
    elif triggers[0] in {
        "NEW_COMPLETE_MARKET_DATA",
        "NEW_USABLE_OOS_WINDOW",
        "MATERIAL_DATASET_CHANGE",
        "SOURCE_QUALITY_CHANGE",
        "IDENTITY_CHANGE",
    }:
        status = "MATERIAL_DATA_CHANGE"
    elif triggers[0] in {"CAPABILITY_GAP_RESOLVED", "NEW_CANONICAL_PRIMITIVE"}:
        status = "CAPABILITY_CHANGE"
    else:
        status = "RESEARCH_CONTEXT_CHANGE"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_material_change_detection",
        "previous_watermark_id": str(previous.get("watermark_id") or "") if previous else "",
        "current_watermark_id": str(current.get("watermark_id") or ""),
        "bootstrap_state": BOOTSTRAP_BASELINE if bootstrap else "",
        "triggers": triggers,
        "precheck_status": status,
        "exact_reason": BOOTSTRAP_BASELINE if bootstrap else ("no_material_change" if not triggers else ",".join(triggers)),
        "content_identity": _content_id(
            "qrpc",
            {
                "previous": str(previous.get("watermark_id") or "") if previous else "",
                "current": current["watermark_id"],
                "triggers": triggers,
                "status": status,
                "bootstrap": bootstrap,
            },
        ),
    }
    return payload


def _opportunity_trigger(row: dict[str, Any], triggers: list[str]) -> str:
    if row.get("opportunity_class") == "GENERATOR_CAPABILITY_GAP":
        return "NEW_CANONICAL_PRIMITIVE" if "NEW_CANONICAL_PRIMITIVE" in triggers else "CAPABILITY_GAP_RESOLVED"
    if row.get("opportunity_class") == "CONTRADICTION_OPPORTUNITY":
        return "NEW_CONTRADICTORY_EVIDENCE"
    return triggers[0] if triggers else "NEW_HYPOTHESIS_TEMPLATE"


def discover_opportunities(*, repo_root: Path, precheck: dict[str, Any], max_items: int) -> dict[str, Any]:
    if precheck["precheck_status"] == "NO_MATERIAL_CHANGE":
        rows: list[dict[str, Any]] = []
    else:
        source_payload = a20.detect_opportunities(repo_root=repo_root)
        rows = []
        for source_row in source_payload.get("rows", [])[:max_items]:
            related_hypotheses = list(source_row.get("related_theses") or [])
            payload = {
                "opportunity_id": str(source_row.get("opportunity_id") or ""),
                "trigger_type": _opportunity_trigger(source_row, list(precheck.get("triggers") or [])),
                "trigger_artifacts": [precheck["current_watermark_id"]],
                "affected_assets": [str(source_row.get("assets") or "")],
                "affected_timeframes": [str(source_row.get("timeframe") or "")],
                "affected_universes": [str(source_row.get("assets") or "")],
                "affected_regimes": [str(source_row.get("regime") or "")],
                "related_hypotheses": related_hypotheses,
                "related_campaigns": [],
                "prior_failures": list(source_row.get("prior_failures") or []),
                "active_contradictions": list(source_row.get("contradicting_observations") or []),
                "resolved_contradictions": [],
                "available_primitives": [],
                "data_readiness": str(source_row.get("data_readiness") or ""),
                "identity_readiness": str(source_row.get("identity_readiness") or ""),
                "expected_information_value": str(source_row.get("expected_information_gain") or ""),
                "estimated_compute_cost": "low",
                "opportunity_status": "eligible" if precheck["precheck_status"] != "NO_MATERIAL_CHANGE" else "blocked",
            }
            payload["content_identity"] = _content_id("qrop", payload)
            rows.append(payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_research_opportunity_registry",
        "rows": rows,
        "summary": {
            "opportunity_count": len(rows),
            "eligible_count": sum(1 for row in rows if row["opportunity_status"] == "eligible"),
        },
        "content_identity": _content_id("qror", rows),
    }


def _novelty_dimensions(candidate: dict[str, Any]) -> list[str]:
    dimensions: list[str] = []
    novelty = str(candidate.get("novelty_outcome") or "")
    mechanism = str(candidate.get("mechanism_class") or "")
    if novelty == "NOVEL":
        dimensions.append("new_causal_mechanism")
    if novelty == "NOVEL_WITH_OVERLAP":
        dimensions.append("new_contradiction_changing_research_question")
    if mechanism == "cross_sectional_continuation":
        dimensions.append("new_relevant_universe")
    if mechanism == "volatility_compression_and_expansion":
        dimensions.append("new_preregistered_regime_segment")
    return dimensions


def generate_hypothesis_batch(*, repo_root: Path, opportunities: dict[str, Any], max_generated: int, write_outputs: bool) -> dict[str, Any]:
    closeout = a20.run_automated_hypothesis_generation(repo_root=repo_root, write_outputs=write_outputs)
    compiled = a20.compile_candidate_theses(repo_root=repo_root)
    rows: list[dict[str, Any]] = []
    for row in compiled.get("rows", [])[:max_generated]:
        novelty_outcome = str(row.get("novelty_outcome") or "")
        lifecycle_state = str(row.get("lifecycle_state") or "")
        if lifecycle_state == "HYPOTHESIS_ADMITTED_AUTOMATED":
            admission = "HYPOTHESIS_ADMITTED"
        elif novelty_outcome == "DUPLICATE":
            admission = "HYPOTHESIS_DUPLICATE"
        elif novelty_outcome in {"NOVEL_WITH_OVERLAP", "MECHANISM_NOT_DISTINCT"}:
            admission = "HYPOTHESIS_NEAR_DUPLICATE"
        elif str(row.get("primitive_compatibility") or "") == "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION":
            admission = "HYPOTHESIS_PRIMITIVE_BLOCKED"
        elif str(row.get("primitive_compatibility") or "") == "REQUIRES_UNRESOLVED_IDENTITY":
            admission = "HYPOTHESIS_IDENTITY_BLOCKED"
        elif str(row.get("testability_state") or "") in {"DATA_BLOCKED", "INSUFFICIENT_HISTORY"}:
            admission = "HYPOTHESIS_DATA_BLOCKED"
        else:
            admission = "HYPOTHESIS_POLICY_BLOCKED"
        payload = {
            "hypothesis_id": str(row.get("thesis_id") or ""),
            "schema_version": SCHEMA_VERSION,
            "generation_policy_version": POLICY_VERSION,
            "mechanism_family": str(row.get("mechanism_class") or ""),
            "behavior_family": str(row.get("behavior_family") or ""),
            "causal_mechanism_statement": str(row.get("causal_mechanism") or row.get("title") or ""),
            "expected_direction_or_relation": str(row.get("expected_signal_density_range") or ""),
            "universe_definition": str(row.get("universe") or ""),
            "timeframe": str(row.get("timeframe") or ""),
            "regime_scope": list(row.get("regimes") or []),
            "entry_condition_semantics": list(row.get("entry_relevant_observations") or []),
            "exit_or_evaluation_semantics": list(row.get("falsification_criteria") or []),
            "required_primitives": list(row.get("required_features") or []),
            "required_sources": ["logs/qre_data_cache_manifest/latest.json"],
            "required_diagnostics": list(row.get("required_diagnostics") or []),
            "required_controls": list(row.get("null_control_requirements") or []),
            "null_hypothesis": str(row.get("null_hypothesis") or ""),
            "falsification_conditions": list(row.get("falsification_criteria") or []),
            "supporting_prior_context": list(row.get("strongest_supporting_evidence") or []),
            "contradicting_prior_context": list(row.get("strongest_contradicting_evidence") or []),
            "novelty_dimensions": _novelty_dimensions(row),
            "prior_related_hypotheses": [str(row.get("source_hypothesis_id") or "")],
            "prior_related_campaigns": [],
            "data_requirements": list(row.get("required_data") or []),
            "minimum_activity_requirements": str(row.get("testability_state") or ""),
            "cost_assumptions": {"estimated_compute_cost": "low"},
            "slippage_assumptions": {"bounded": True},
            "parameter_schema": list(row.get("parameter_schema", []) or [])[:3],
            "parameter_count": min(int(len(row.get("parameter_schema", []) or [])), 3),
            "provenance": list(closeout.get("provenance") or []),
            "content_identity": "",
            "admission_status": admission,
            "novelty_status": novelty_outcome,
            "duplicate_of": str(row.get("duplicate_of") or ""),
            "near_duplicate_of": str(row.get("near_duplicate_of") or ""),
            "suppression_reason": "" if admission == "HYPOTHESIS_ADMITTED" else admission.lower(),
            "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
            "primitive_compatibility": str(row.get("primitive_compatibility") or ""),
            "testability_state": str(row.get("testability_state") or ""),
        }
        payload["content_identity"] = _content_id("qrhy", payload)
        rows.append(payload)
    novelty_rows = [
        {
            "hypothesis_id": row["hypothesis_id"],
            "novelty_status": row["novelty_status"],
            "novelty_dimensions": row["novelty_dimensions"],
            "duplicate_of": row["duplicate_of"],
            "near_duplicate_of": row["near_duplicate_of"],
            "suppression_reason": row["suppression_reason"],
            "content_identity": _content_id("qrhn", row["content_identity"]),
        }
        for row in rows
    ]
    return {
        "batch": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_generated_hypothesis_batch",
            "rows": rows,
            "summary": {
                "generated": len(rows),
                "admitted": sum(1 for row in rows if row["admission_status"] == "HYPOTHESIS_ADMITTED"),
                "exact_duplicates": sum(1 for row in rows if row["admission_status"] == "HYPOTHESIS_DUPLICATE"),
                "near_duplicates": sum(1 for row in rows if row["admission_status"] == "HYPOTHESIS_NEAR_DUPLICATE"),
            },
            "content_identity": _content_id("qrhb", rows),
        },
        "novelty": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_hypothesis_novelty_decisions",
            "rows": novelty_rows,
            "content_identity": _content_id("qrhnr", novelty_rows),
        },
    }


def _executed_window_keys(repo_root: Path) -> set[str]:
    keys: set[str] = set()
    for row in _load_empirical_history(repo_root):
        keys.add(
            "|".join(
                [
                    str(row.get("source_hypothesis_id") or ""),
                    str(row.get("timeframe") or ""),
                    str((row.get("oos_window") or {}).get("end") or ""),
                ]
            )
        )
    return keys


def materialize_campaign_cells(*, repo_root: Path, hypotheses: dict[str, Any], max_cells: int) -> dict[str, Any]:
    strategy_rows = _load_strategy_registry(repo_root)
    portfolio_rows = _load_portfolio_rows(repo_root)
    strategies_by_source = {
        str(row.get("source_hypothesis_id") or ""): dict(row)
        for row in strategy_rows
        if str(row.get("source_hypothesis_id") or "")
    }
    executed_keys = _executed_window_keys(repo_root)
    cell_rows: list[dict[str, Any]] = []
    novelty_rows: list[dict[str, Any]] = []
    for hypothesis in hypotheses.get("rows", []):
        if hypothesis["admission_status"] != "HYPOTHESIS_ADMITTED":
            continue
        strategy = strategies_by_source.get(hypothesis["source_hypothesis_id"])
        if not strategy:
            continue
        strategy_id = str(strategy.get("generated_strategy_id") or "")
        for portfolio_row in sorted(
            [row for row in portfolio_rows if str(row.get("generated_strategy_id") or "") == strategy_id],
            key=lambda row: (str(row.get("timeframe") or ""), str(row.get("campaign_cell_id") or "")),
        ):
            if len(cell_rows) >= max_cells:
                break
            oos_end = str((portfolio_row.get("oos_window") or {}).get("end") or "")
            novelty_dimensions = []
            if hypothesis["novelty_dimensions"]:
                novelty_dimensions.extend(hypothesis["novelty_dimensions"])
            if oos_end:
                novelty_dimensions.append("new_real_oos_period")
            if str(portfolio_row.get("timeframe") or "") != str(hypothesis.get("timeframe") or ""):
                novelty_dimensions.append("different_preregistered_timeframe")
            novelty_dimensions = sorted(set(novelty_dimensions))
            novelty_key = "|".join(
                [
                    hypothesis["source_hypothesis_id"],
                    str(portfolio_row.get("timeframe") or ""),
                    oos_end,
                ]
            )
            if novelty_key in executed_keys:
                decision = "SUPPRESSED"
                reason_codes = ["identical_frozen_campaign_already_executed"]
            elif novelty_dimensions:
                decision = "ADMITTED"
                reason_codes = []
            else:
                decision = "SUPPRESSED"
                reason_codes = ["same_frozen_question_without_new_novelty"]
            cell_payload = {
                "campaign_cell_id": str(portfolio_row.get("campaign_cell_id") or ""),
                "hypothesis_id": hypothesis["hypothesis_id"],
                "mechanism_family": hypothesis["mechanism_family"],
                "universe": hypothesis["universe_definition"],
                "timeframe": str(portfolio_row.get("timeframe") or ""),
                "regime_scope": hypothesis["regime_scope"],
                "dataset_fingerprint": str(portfolio_row.get("dataset_identity") or ""),
                "source_manifest_ids": list(_load_cache_manifest(repo_root).get("cache_roots", [])),
                "identity_manifest_id": str(portfolio_row.get("snapshot_identity") or ""),
                "primitive_mapping": list(hypothesis["required_primitives"]),
                "executor_mapping": "second_preregistered_campaign",
                "sampling_plan": {
                    "train_window": dict(portfolio_row.get("train_window") or {}),
                    "validation_window": dict(portfolio_row.get("validation_window") or {}),
                    "locked_oos_window": dict(portfolio_row.get("oos_window") or {}),
                },
                "train_window": dict(portfolio_row.get("train_window") or {}),
                "validation_window": dict(portfolio_row.get("validation_window") or {}),
                "locked_oos_window": dict(portfolio_row.get("oos_window") or {}),
                "embargo": "existing_policy",
                "warmup": "existing_policy",
                "cost_assumptions": hypothesis["cost_assumptions"],
                "slippage_assumptions": hypothesis["slippage_assumptions"],
                "null_control_plan": list(hypothesis["required_controls"]),
                "stability_plan": "existing_validation",
                "outlier_plan": "existing_validation",
                "parameter_fragility_plan": "existing_validation",
                "novelty_identity": novelty_key,
                "prior_related_campaigns": [],
                "expected_information_gain": "high" if novelty_dimensions else "low",
                "estimated_compute_cost": "low",
                "readiness": str(portfolio_row.get("status") or ""),
                "blockers": list(portfolio_row.get("blockers") or []),
                "content_identity": "",
                "genuine_novelty_decision": decision,
            }
            cell_payload["content_identity"] = _content_id("qrcell", cell_payload)
            cell_rows.append(cell_payload)
            novelty_rows.append(
                {
                    "cell_id": cell_payload["campaign_cell_id"],
                    "prior_campaign_ids": [],
                    "novelty_type": novelty_dimensions[0] if novelty_dimensions else "none",
                    "novelty_artifacts": [novelty_key],
                    "changed_frozen_dimensions": novelty_dimensions,
                    "unchanged_frozen_dimensions": ["same_parameters"],
                    "decision": decision,
                    "reason_codes": reason_codes,
                    "content_identity": _content_id("qrcn", {"cell_id": cell_payload["campaign_cell_id"], "decision": decision, "reason_codes": reason_codes}),
                }
            )
    return {
        "registry": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_campaign_cell_registry",
            "rows": cell_rows[:max_cells],
            "summary": {
                "materialized": min(len(cell_rows), max_cells),
                "admitted": sum(1 for row in cell_rows[:max_cells] if row["genuine_novelty_decision"] == "ADMITTED"),
            },
            "content_identity": _content_id("qrcg", cell_rows[:max_cells]),
        },
        "novelty": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_campaign_cell_novelty_decisions",
            "rows": novelty_rows[:max_cells],
            "content_identity": _content_id("qrcnd", novelty_rows[:max_cells]),
        },
    }


def _rank_cells(cell_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ready_rows = [
        row
        for row in cell_rows
        if row["genuine_novelty_decision"] == "ADMITTED" and row["readiness"] == "READY_FOR_PREREGISTRATION"
    ]
    ready_rows.sort(
        key=lambda row: (
            0 if row["expected_information_gain"] == "high" else 1,
            str(row["timeframe"]),
            str(row["campaign_cell_id"]),
        )
    )
    return ready_rows[:limit]


def _generic_gap_class(blockers: list[str], admission_status: str) -> str:
    blocker_set = set(blockers)
    if "required_primitives_missing" in blocker_set or admission_status == "HYPOTHESIS_PRIMITIVE_BLOCKED":
        return "PRIMITIVE_CAPABILITY_GAP"
    if "identity_unresolved" in blocker_set or admission_status == "HYPOTHESIS_IDENTITY_BLOCKED":
        return "IDENTITY_GAP"
    if "data_binding_not_ready" in blocker_set or "cache_row_missing" in blocker_set:
        return "CACHE_CAPABILITY_GAP"
    if "source_quality_failed" in blocker_set:
        return "SOURCE_QUALITY_GAP"
    if "generated_strategy_missing" in blocker_set:
        return "EXECUTOR_CAPABILITY_GAP"
    if "missing_falsification_criteria" in blocker_set or "missing_expected_observables" in blocker_set:
        return "DIAGNOSTIC_CAPABILITY_GAP"
    if "usable_history_below_minimum_policy_span" in blocker_set:
        return "DATA_AVAILABILITY_WAIT"
    return "LOW_SIGNAL_DENSITY"


def _is_ade_eligible_gap(gap_class: str) -> bool:
    return gap_class in {
        "CACHE_CAPABILITY_GAP",
        "PRIMITIVE_CAPABILITY_GAP",
        "EXECUTOR_CAPABILITY_GAP",
        "DIAGNOSTIC_CAPABILITY_GAP",
        "ORCHESTRATION_CAPABILITY_GAP",
        "IDENTITY_GAP",
        "SOURCE_QUALITY_GAP",
    }


def build_gap_registry(
    *,
    repo_root: Path,
    hypotheses: dict[str, Any],
    cells: dict[str, Any],
    run_id: str,
    opportunity_rows: list[dict[str, Any]],
    precheck: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = _read_json(GAP_REGISTRY_PATH, repo_root=repo_root) or {"rows": []}
    previous_by_key = {
        str(row.get("deduplication_key") or ""): dict(row)
        for row in previous.get("rows", [])
        if isinstance(row, dict)
    }
    rows = list(previous.get("rows", []))
    current_rows: list[dict[str, Any]] = []
    trigger_origin_class = "CANONICAL_SOURCE_STATE"
    trigger_authority = str(precheck.get("current_watermark_id") or "") if isinstance(precheck, dict) else ""
    for hypothesis in hypotheses.get("rows", []):
        if hypothesis["admission_status"] in {"HYPOTHESIS_ADMITTED", "HYPOTHESIS_DUPLICATE", "HYPOTHESIS_NEAR_DUPLICATE"}:
            continue
        gap_class = _generic_gap_class([], hypothesis["admission_status"])
        dedup_key = stable_digest({"gap_class": gap_class, "hypothesis_id": hypothesis["hypothesis_id"]})
        prior = previous_by_key.get(dedup_key, {})
        occurrence_count = int(prior.get("occurrence_count") or 0) + 1
        payload = {
            "gap_id": str(prior.get("gap_id") or _content_id("qrgp", {"gap_class": gap_class, "hypothesis": hypothesis["hypothesis_id"]})),
            "gap_class": gap_class,
            "persistent": occurrence_count > 1,
            "code_addressable": _is_ade_eligible_gap(gap_class),
            "deduplication_key": dedup_key,
            "occurrence_count": occurrence_count,
            "first_seen_state": str(prior.get("first_seen_state") or hypothesis["hypothesis_id"]),
            "latest_seen_state": hypothesis["content_identity"],
            "evidence_refs": [HYPOTHESIS_BATCH_PATH.as_posix()],
            "run_id": run_id,
            "source_hypothesis_id": hypothesis["source_hypothesis_id"],
            "trigger_origin_class": trigger_origin_class,
            "trigger_authority": trigger_authority,
            "content_identity": "",
        }
        payload["content_identity"] = _content_id("qrgc", payload)
        current_rows.append(payload)
    for cell in cells.get("rows", []):
        blockers = list(cell.get("blockers") or [])
        if not blockers:
            continue
        gap_class = _generic_gap_class(blockers, "")
        dedup_key = stable_digest({"gap_class": gap_class, "cell_id": cell["campaign_cell_id"], "blockers": blockers})
        prior = previous_by_key.get(dedup_key, {})
        occurrence_count = int(prior.get("occurrence_count") or 0) + 1
        payload = {
            "gap_id": str(prior.get("gap_id") or _content_id("qrgp", {"gap_class": gap_class, "cell": cell["campaign_cell_id"]})),
            "gap_class": gap_class,
            "persistent": occurrence_count > 1 or len(blockers) > 1,
            "code_addressable": _is_ade_eligible_gap(gap_class),
            "deduplication_key": dedup_key,
            "occurrence_count": occurrence_count,
            "first_seen_state": str(prior.get("first_seen_state") or cell["campaign_cell_id"]),
            "latest_seen_state": cell["content_identity"],
            "evidence_refs": [CAMPAIGN_CELL_PATH.as_posix()],
            "run_id": run_id,
            "source_hypothesis_id": "",
            "campaign_cell_id": cell["campaign_cell_id"],
            "trigger_origin_class": trigger_origin_class,
            "trigger_authority": trigger_authority,
            "content_identity": "",
        }
        payload["content_identity"] = _content_id("qrgc", payload)
        current_rows.append(payload)
    merged = {
        row["deduplication_key"]: row
        for row in rows + current_rows
        if isinstance(row, dict) and str(row.get("deduplication_key") or "")
    }
    merged_rows = sorted(merged.values(), key=lambda row: (str(row.get("gap_class") or ""), str(row.get("gap_id") or "")))
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_capability_gap_registry",
        "rows": merged_rows,
        "summary": {"gap_count": len(merged_rows)},
        "content_identity": _content_id("qrg", merged_rows),
    }


def _request_owner(gap_class: str) -> tuple[str, str]:
    mapping = {
        "CACHE_CAPABILITY_GAP": ("reporting/qre_research_operations.py", "reporting"),
        "DIAGNOSTIC_CAPABILITY_GAP": ("reporting/qre_executable_validation_request.py", "reporting"),
        "ORCHESTRATION_CAPABILITY_GAP": ("reporting/qre_research_operations.py", "reporting"),
        "PRIMITIVE_CAPABILITY_GAP": ("packages/qre_research/automated_primitive_expansion.py", "packages"),
        "EXECUTOR_CAPABILITY_GAP": ("packages/qre_research/second_preregistered_campaign.py", "packages"),
        "IDENTITY_GAP": ("packages/qre_data/symbology_resolver.py", "packages"),
        "SOURCE_QUALITY_GAP": ("packages/qre_data/source_quality_readiness.py", "packages"),
    }
    return mapping.get(gap_class, ("reporting/qre_research_operations.py", "reporting"))


def _build_request_proposal(request: dict[str, Any]) -> dict[str, Any]:
    status = "eligible" if request["execution_authority_result"] == ea.DECISION_AUTO_ALLOWED else (
        "needs_human" if request["execution_authority_result"] == ea.DECISION_NEEDS_HUMAN else "blocked"
    )
    return {
        "proposal_id": request["request_id"],
        "source_type": "qre_autonomous_opportunity_loop",
        "proposal_type": "qre_capability_request",
        "title": request["gap_summary"],
        "status": status,
        "risk_class": request["risk_class"],
        "execution_authority_decision": request["execution_authority_result"],
        "affected_files": [request["canonical_owner"]],
        "required_tests": list(request["acceptance_tests"]),
        "suggested_branch_name": f"fix/{request['request_id'][:40]}",
        "forbidden_actions": [
            "launch_codex",
            "mutate_campaign_queue",
            "mutate_strategy_or_preset",
            "enable_paper_runtime",
            "enable_shadow_runtime",
            "enable_live_runtime",
            "place_order",
            "allocate_capital",
        ],
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "human_needed_reason": "execution_authority_requires_operator_review" if status == "needs_human" else "",
    }


def _read_request_lifecycle(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(REQUEST_LIFECYCLE_PATH, repo_root=repo_root)
    if isinstance(payload, dict):
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_ade_request_lifecycle",
        "rows": [],
    }


def _request_lifecycle_by_id(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_request_lifecycle(repo_root)
    return {
        str(row.get("request_id") or ""): dict(row)
        for row in payload.get("rows", [])
        if isinstance(row, dict) and str(row.get("request_id") or "")
    }


def _active_request_rows(*, repo_root: Path, request_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lifecycle = _request_lifecycle_by_id(repo_root)
    active_rows: list[dict[str, Any]] = []
    for row in request_rows:
        request_id = str(row.get("request_id") or "")
        override = lifecycle.get(request_id, {})
        if override.get("active") is False:
            continue
        active_rows.append(row)
    return active_rows


def _build_request_lifecycle(
    *,
    repo_root: Path,
    root_cause: dict[str, Any],
) -> dict[str, Any]:
    previous = _read_request_lifecycle(repo_root)
    rows = [
        dict(row)
        for row in previous.get("rows", [])
        if isinstance(row, dict)
    ]
    by_id = {
        str(row.get("request_id") or ""): row
        for row in rows
        if str(row.get("request_id") or "")
    }
    observed_status = ""
    for path in (
        PROPOSAL_INTAKE_PATH,
        Path("logs/qre_development_intake_promotion/latest.json"),
        Path("logs/qre_development_queue_admission_policy/latest.json"),
    ):
        payload = _read_json(path, repo_root=repo_root) or {}
        for key in ("proposals", "rows"):
            items = payload.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                request_id = str(
                    item.get("proposal_id")
                    or item.get("candidate_id")
                    or ""
                )
                if request_id == KNOWN_FALSE_POSITIVE_REQUEST_ID:
                    observed_status = str(
                        item.get("status")
                        or item.get("upstream_proposal_status")
                        or item.get("decision_state")
                        or ""
                    )
                    break
            if observed_status:
                break
        if observed_status:
            break
    prior = by_id.get(KNOWN_FALSE_POSITIVE_REQUEST_ID, {})
    lifecycle_row = {
        "request_id": KNOWN_FALSE_POSITIVE_REQUEST_ID,
        "previous_status": str(prior.get("final_status") or observed_status or "needs_human"),
        "final_status": "SUPERSEDED",
        "effective_status": "SUPERSEDED",
        "active": False,
        "operator_action_required": False,
        "resolution_reason": SELF_TRIGGER_FALSE_POSITIVE_REASON,
        "superseded_by": str(prior.get("superseded_by") or "opportunity_loop_idempotence_fix"),
        "root_cause_artifact": ROOT_CAUSE_PATH.as_posix(),
        "root_cause_identity": str(root_cause.get("content_identity") or ""),
        "historical_provenance_refs": [
            PROPOSAL_INTAKE_PATH.as_posix(),
            "logs/qre_development_intake_promotion/latest.json",
            "logs/qre_development_queue_admission_policy/latest.json",
        ],
        "content_identity": "",
    }
    lifecycle_row["content_identity"] = _content_id("qrlc", lifecycle_row)
    by_id[KNOWN_FALSE_POSITIVE_REQUEST_ID] = lifecycle_row
    materialized_rows = sorted(
        by_id.values(),
        key=lambda row: (str(row.get("request_id") or ""), str(row.get("effective_status") or "")),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_ade_request_lifecycle",
        "rows": materialized_rows,
        "summary": {
            "inactive_false_positives": sum(
                1
                for row in materialized_rows
                if row.get("resolution_reason") == SELF_TRIGGER_FALSE_POSITIVE_REASON
                and row.get("active") is False
            )
        },
        "content_identity": _content_id("qrlcf", materialized_rows),
    }


def _proposal_intake_payload(*, request_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": "qre_research_action_proposal_intake",
        "generated_at_utc": _iso_now(),
        "safe_to_execute": False,
        "proposals": [_build_request_proposal(row) for row in request_rows],
    }


def build_ade_requests(
    *,
    repo_root: Path,
    gap_registry: dict[str, Any],
    run_id: str,
    precheck: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = _read_json(ADE_REQUESTS_PATH, repo_root=repo_root) or {"rows": []}
    previous_by_key = {
        str(row.get("deduplication_key") or ""): dict(row)
        for row in previous.get("rows", [])
        if isinstance(row, dict)
    }
    new_requests: list[dict[str, Any]] = []
    for gap in gap_registry.get("rows", []):
        if not _is_ade_eligible_gap(str(gap.get("gap_class") or "")):
            continue
        if not gap.get("persistent") or not gap.get("code_addressable"):
            continue
        trigger_origin_class = str(gap.get("trigger_origin_class") or "")
        if trigger_origin_class in NON_MATERIAL_INPUT_CLASSES:
            continue
        owner_path, _ = _request_owner(str(gap["gap_class"]))
        dedup_key = stable_digest(
            {
                "gap_class": gap["gap_class"],
                "owner": owner_path,
                "reproduction": gap["deduplication_key"],
            }
        )
        prior = previous_by_key.get(dedup_key, {})
        authority = ea.classify(action_type="file_edit", target_path=owner_path, risk_class=ea.RISK_LOW)
        request = {
            "request_id": str(prior.get("request_id") or _content_id("qrdr", {"owner": owner_path, "gap": gap["gap_id"]})),
            "schema_version": SCHEMA_VERSION,
            "origin": "QRE",
            "loop_run_id": run_id,
            "originating_opportunity_id": "",
            "originating_hypothesis_id": str(gap.get("source_hypothesis_id") or ""),
            "originating_campaign_cell_id": str(gap.get("campaign_cell_id") or ""),
            "gap_class": str(gap["gap_class"]),
            "gap_summary": f"QRE capability gap: {gap['gap_class']}",
            "reproduction_steps": [
                "Run the bounded autonomous opportunity loop.",
                f"Observe deterministic blocker {gap['gap_class']}.",
            ],
            "evidence_artifact_refs": list(gap.get("evidence_refs") or []),
            "first_seen_state": str(prior.get("first_seen_state") or gap["first_seen_state"]),
            "latest_seen_state": str(gap["latest_seen_state"]),
            "occurrence_count": int(prior.get("occurrence_count") or 0) + int(gap.get("occurrence_count") or 1),
            "persistence_proof": {"persistent": True, "gap_occurrence_count": int(gap.get("occurrence_count") or 0)},
            "affected_capabilities": [str(gap["gap_class"])],
            "research_impact": "blocks bounded autonomous research continuation",
            "smallest_generic_capability_required": str(gap["gap_class"]).lower(),
            "canonical_owner": owner_path,
            "allowed_roots": ["packages/qre_research/**", "packages/qre_data/**", "reporting/qre_*.py"],
            "forbidden_roots": ["research/research_latest.json", "research/strategy_matrix.csv", ".claude/**", "shadow/**", "paper/**", "live/**"],
            "acceptance_tests": [
                "python -m pytest tests/unit/test_qre_autonomous_opportunity_loop.py -q",
            ],
            "expected_research_unlock": "reopen blocked opportunity after capability resolution",
            "risk_class": ea.RISK_LOW,
            "execution_authority_action": "file_edit",
            "execution_authority_result": authority.decision,
            "self_trigger_check": "PASS",
            "trigger_origin_class": trigger_origin_class or "CANONICAL_SOURCE_STATE",
            "trigger_authority": str(gap.get("trigger_authority") or "canonical_gap_registry"),
            "deduplication_key": dedup_key,
            "status": authority.decision,
            "supersedes": str(prior.get("request_id") or ""),
            "content_identity": "",
        }
        request["content_identity"] = _content_id("qrad", request)
        previous_by_key[dedup_key] = request
        new_requests.append(request)
    merged = sorted(previous_by_key.values(), key=lambda row: (str(row.get("gap_class") or ""), str(row.get("request_id") or "")))
    active_requests = _active_request_rows(repo_root=repo_root, request_rows=merged)
    proposal_payload = _proposal_intake_payload(request_rows=active_requests)
    qdip_snapshot = qdip.collect_snapshot(
        input_artifact_path=_repo_path(PROPOSAL_INTAKE_PATH, repo_root=repo_root),
        generated_at_utc=_iso_now(),
    ) if not active_requests else None
    return {
        "requests": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_ade_development_requests",
            "rows": merged,
            "summary": {
                "request_count": len(merged),
                "active_request_count": len(active_requests),
                "new_requests": len(new_requests),
                "auto_allowed": sum(1 for row in merged if row["execution_authority_result"] == ea.DECISION_AUTO_ALLOWED),
                "needs_human": sum(1 for row in merged if row["execution_authority_result"] == ea.DECISION_NEEDS_HUMAN),
                "permanently_denied": sum(1 for row in merged if row["execution_authority_result"] == ea.DECISION_PERMANENTLY_DENIED),
            },
            "content_identity": _content_id("qrar", merged),
        },
        "active_requests": active_requests,
        "proposal_intake_payload": proposal_payload,
        "promotion_snapshot": qdip_snapshot,
    }


def _write_ade_bridge_artifacts(*, repo_root: Path, proposal_intake_payload: dict[str, Any]) -> dict[str, Any]:
    intake_path = _repo_path(PROPOSAL_INTAKE_PATH, repo_root=repo_root)
    _atomic_write(
        intake_path,
        json.dumps(proposal_intake_payload, indent=2, sort_keys=True) + "\n",
        repo_root=repo_root,
    )
    promotion_snapshot = qdip.collect_snapshot(input_artifact_path=intake_path, generated_at_utc=_iso_now())
    qdip.write_outputs(promotion_snapshot)
    admission_snapshot = qdap.collect_snapshot(
        input_artifact_path=_repo_path(Path(qdip.OUTPUT_ARTIFACT_RELATIVE_PATH), repo_root=repo_root),
        generated_at_utc=_iso_now(),
    )
    qdap.write_outputs(admission_snapshot)
    return {"promotion_snapshot": promotion_snapshot, "admission_snapshot": admission_snapshot}


def consume_resolution_feedback(*, repo_root: Path, request_rows: list[dict[str, Any]]) -> dict[str, Any]:
    work_queue = _read_json(Path("logs/development_work_queue/latest.json"), repo_root=repo_root) or {}
    items = work_queue.get("items") if isinstance(work_queue.get("items"), list) else []
    resolved_rows: list[dict[str, Any]] = []
    for request in request_rows:
        request_id = str(request.get("request_id") or "")
        matched = False
        for item in items:
            if not isinstance(item, dict):
                continue
            text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("notes") or ""),
                    str(item.get("item_id") or ""),
                ]
            )
            if request_id and request_id in text and str(item.get("status") or "") in {"done", "archived"}:
                matched = True
                break
        if matched:
            resolved_rows.append(
                {
                    "request_id": request_id,
                    "resolution_status": "RESOLVED",
                    "capability_gap_resolved_trigger": "CAPABILITY_GAP_RESOLVED",
                    "content_identity": _content_id("qraf", {"request_id": request_id, "status": "RESOLVED"}),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_ade_request_resolution_feedback",
        "rows": resolved_rows,
        "summary": {"resolved_request_count": len(resolved_rows)},
        "content_identity": _content_id("qraff", resolved_rows),
    }


def _build_output_checkpoint(
    *,
    opportunities: dict[str, Any],
    hypotheses: dict[str, Any],
    cells: dict[str, Any],
    ade_requests: dict[str, Any],
    loop_status: dict[str, Any],
) -> dict[str, Any]:
    tracked_request_statuses = {
        str(row.get("request_id") or ""): str(row.get("status") or "")
        for row in ade_requests.get("rows", [])
        if isinstance(row, dict) and str(row.get("request_id") or "")
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_loop_output_checkpoint",
        "opportunity_identity": str(opportunities.get("content_identity") or ""),
        "hypothesis_identity": str(hypotheses.get("content_identity") or ""),
        "campaign_cell_identity": str(cells.get("content_identity") or ""),
        "ade_request_identity": str(ade_requests.get("content_identity") or ""),
        "loop_state_identity": str(loop_status.get("content_identity") or ""),
        "tracked_request_statuses": tracked_request_statuses,
        "content_identity": "",
    }
    payload["content_identity"] = _content_id("qroc", payload)
    return payload


def _acquire_lock(*, repo_root: Path) -> LoopLock:
    now = _utcnow()
    current = _read_json(LOCK_PATH, repo_root=repo_root)
    if current:
        expires_at = _parse_iso(str(current.get("lease_expires_at_utc") or ""))
        if expires_at and expires_at > now:
            raise RuntimeError("opportunity_loop_lock_active")
    run_id = _content_id("qrlo", {"now": _iso(now)})
    lock = LoopLock(run_id=run_id, lease_expires_at_utc=_iso(now + timedelta(seconds=LOCK_LEASE_SECONDS)))
    _write_json(
        LOCK_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "qre_opportunity_loop_lock",
            "run_id": lock.run_id,
            "lease_expires_at_utc": lock.lease_expires_at_utc,
        },
        repo_root=repo_root,
    )
    return lock


def _release_lock(*, repo_root: Path) -> None:
    with suppress(FileNotFoundError):
        _repo_path(LOCK_PATH, repo_root=repo_root).unlink()


def _loop_status_payload(
    *,
    run_id: str,
    state: str,
    precheck: dict[str, Any],
    opportunities: dict[str, Any],
    hypotheses: dict[str, Any],
    cells: dict[str, Any],
    executed_campaigns: list[dict[str, Any]],
    ade_requests: dict[str, Any],
    current_wait_reason: str,
    next_wake_conditions: list[str],
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    payload = {
        "loop_run_id": run_id,
        "state": state,
        "started_at": started_at,
        "completed_at": completed_at,
        "trigger_summary": list(precheck.get("triggers") or []),
        "material_change_status": precheck.get("precheck_status"),
        "opportunities_detected": int(opportunities.get("summary", {}).get("opportunity_count") or 0),
        "hypotheses_generated": int(hypotheses.get("summary", {}).get("generated") or 0),
        "hypotheses_admitted": int(hypotheses.get("summary", {}).get("admitted") or 0),
        "hypotheses_suppressed": int(hypotheses.get("summary", {}).get("exact_duplicates") or 0)
        + int(hypotheses.get("summary", {}).get("near_duplicates") or 0),
        "campaign_cells_materialized": int(cells.get("summary", {}).get("materialized") or 0),
        "campaigns_admitted": len(executed_campaigns),
        "campaigns_executed": len(executed_campaigns),
        "terminal_dispositions": [str(row.get("terminal_outcome") or "") for row in executed_campaigns],
        "memory_updates": len(executed_campaigns),
        "ADE_requests_created": int(ade_requests.get("summary", {}).get("new_requests") or 0),
        "ADE_requests_deduplicated": max(int(ade_requests.get("summary", {}).get("request_count") or 0) - int(ade_requests.get("summary", {}).get("new_requests") or 0), 0),
        "ADE_requests_needing_human": int(ade_requests.get("summary", {}).get("needs_human") or 0),
        "current_wait_reason": current_wait_reason,
        "next_wake_conditions": next_wake_conditions,
        "budget_used": dict(DEFAULT_LIMITS),
    }
    payload["content_identity"] = _content_id("qrls", payload)
    return payload


def run_opportunity_loop(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    lock = _acquire_lock(repo_root=repo_root)
    started_at = _iso_now()
    try:
        previous_watermark = _read_json(WATERMARK_PATH, repo_root=repo_root)
        previous_checkpoint = _read_json(OUTPUT_CHECKPOINT_PATH, repo_root=repo_root)
        previous_state = _read_json(STATE_PATH, repo_root=repo_root) or {}
        bootstrap_state = BOOTSTRAP_BASELINE if previous_watermark is None else ""
        current_watermark = build_watermark(
            repo_root=repo_root,
            previous_state_identity=str(previous_state.get("content_identity") or ""),
            previous_checkpoint=previous_checkpoint,
            bootstrap_state=bootstrap_state,
        )
        precheck = build_precheck(previous_watermark, current_watermark)
        root_cause = _load_root_cause_payload(repo_root=repo_root, previous_checkpoint=previous_checkpoint)
        root_cause["content_identity"] = _content_id("qrrc", root_cause)
        request_lifecycle = _build_request_lifecycle(repo_root=repo_root, root_cause=root_cause)
        executed_campaigns: list[dict[str, Any]] = []
        if precheck["precheck_status"] == "NO_MATERIAL_CHANGE":
            opportunities = {
                "schema_version": SCHEMA_VERSION,
                "policy_version": POLICY_VERSION,
                "report_kind": "qre_research_opportunity_registry",
                "rows": [],
                "summary": {"opportunity_count": 0},
                "content_identity": _content_id("qrop", []),
            }
            hypotheses_payload = {
                "batch": {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": POLICY_VERSION,
                    "report_kind": "qre_generated_hypothesis_batch",
                    "rows": [],
                    "summary": {
                        "generated": 0,
                        "admitted": 0,
                        "exact_duplicates": 0,
                        "near_duplicates": 0,
                    },
                    "content_identity": _content_id("qrhb", []),
                },
                "novelty": {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": POLICY_VERSION,
                    "report_kind": "qre_hypothesis_novelty_decisions",
                    "rows": [],
                    "content_identity": _content_id("qrhnr", []),
                },
            }
            cells_payload = {
                "registry": {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": POLICY_VERSION,
                    "report_kind": "qre_campaign_cell_registry",
                    "rows": [],
                    "summary": {
                        "materialized": 0,
                        "admitted": 0,
                        "suppressed": 0,
                    },
                    "content_identity": _content_id("qrcg", []),
                },
                "novelty": {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": POLICY_VERSION,
                    "report_kind": "qre_campaign_cell_novelty_decisions",
                    "rows": [],
                    "content_identity": _content_id("qrcn", []),
                },
            }
            gap_registry = {
                "schema_version": SCHEMA_VERSION,
                "policy_version": POLICY_VERSION,
                "report_kind": "qre_capability_gap_registry",
                "rows": [],
                "summary": {"gap_count": 0},
                "content_identity": _content_id("qrg", []),
            }
            ade_bundle = {
                "requests": {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": POLICY_VERSION,
                    "report_kind": "qre_ade_development_requests",
                    "rows": [],
                    "summary": {
                    "request_count": 0,
                    "active_request_count": 0,
                    "new_requests": 0,
                    "auto_allowed": 0,
                    "needs_human": 0,
                        "permanently_denied": 0,
                    },
                    "content_identity": _content_id("qrar", []),
                },
                "active_requests": [],
                "proposal_intake_payload": {
                    "schema_version": 1,
                    "report_kind": "qre_research_action_proposal_intake",
                    "generated_at_utc": _iso_now(),
                    "safe_to_execute": False,
                    "proposals": [],
                },
                "promotion_snapshot": None,
            }
            promotion_artifacts = {"promotion_snapshot": None, "admission_snapshot": None}
            feedback = {
                "schema_version": SCHEMA_VERSION,
                "policy_version": POLICY_VERSION,
                "report_kind": "qre_ade_request_resolution_feedback",
                "rows": [],
                "summary": {"resolved_request_count": 0},
                "content_identity": _content_id("qrafb", []),
            }
            qhl.run_trusted_hypothesis_loop(repo_root=repo_root, write_outputs=write_outputs)
        else:
            opportunities = discover_opportunities(
                repo_root=repo_root,
                precheck=precheck,
                max_items=max_cycles or DEFAULT_LIMITS["maximum_cycles_per_run"],
            )
            hypotheses_payload = generate_hypothesis_batch(
                repo_root=repo_root,
                opportunities=opportunities,
                max_generated=DEFAULT_LIMITS["maximum_generated_hypotheses_per_cycle"],
                write_outputs=write_outputs,
            )
            cells_payload = materialize_campaign_cells(
                repo_root=repo_root,
                hypotheses=hypotheses_payload["batch"],
                max_cells=DEFAULT_LIMITS["maximum_campaign_cells_per_run"],
            )
            admitted_cells = _rank_cells(
                cells_payload["registry"]["rows"],
                DEFAULT_LIMITS["maximum_campaign_executions_per_run"],
            )
            for cell in admitted_cells:
                closeout = spc.run_second_preregistered_campaign(
                    repo_root=repo_root,
                    write_outputs=write_outputs,
                    campaign_cell_id=str(cell["campaign_cell_id"]),
                )
                executed_campaigns.append(closeout)
                qhl.run_trusted_hypothesis_loop(repo_root=repo_root, write_outputs=write_outputs)
            gap_registry = build_gap_registry(
                repo_root=repo_root,
                hypotheses=hypotheses_payload["batch"],
                cells=cells_payload["registry"],
                run_id=lock.run_id,
                opportunity_rows=opportunities.get("rows", []),
                precheck=precheck,
            )
            ade_bundle = build_ade_requests(
                repo_root=repo_root,
                gap_registry=gap_registry,
                run_id=lock.run_id,
                precheck=precheck,
            )
            feedback = consume_resolution_feedback(
                repo_root=repo_root,
                request_rows=list(ade_bundle.get("active_requests") or []),
            )

        if precheck["precheck_status"] == "NO_MATERIAL_CHANGE":
            final_state = "WAITING_FOR_NOVELTY"
            wait_reason = BOOTSTRAP_BASELINE if bootstrap_state else "no_material_change"
        elif ade_bundle["requests"]["summary"]["new_requests"]:
            final_state = "CAPABILITY_REQUESTED"
            wait_reason = "persistent_generic_capability_gap"
        elif executed_campaigns:
            final_state = "RESEARCH_EXECUTED"
            wait_reason = "campaigns_executed"
        elif opportunities["summary"]["opportunity_count"] == 0:
            final_state = "WAITING_FOR_NOVELTY"
            wait_reason = "no_eligible_opportunity"
        else:
            final_state = "WAITING_FOR_NOVELTY"
            wait_reason = "cells_blocked_or_duplicate"
        continuation = _load_trust_continuation(repo_root)
        loop_status = _loop_status_payload(
            run_id=lock.run_id,
            state=final_state,
            precheck=precheck,
            opportunities=opportunities,
            hypotheses=hypotheses_payload["batch"],
            cells=cells_payload["registry"],
            executed_campaigns=executed_campaigns,
            ade_requests=ade_bundle["requests"],
            current_wait_reason=wait_reason,
            next_wake_conditions=list(continuation.get("required_novelty") or []),
            started_at=started_at,
            completed_at=_iso_now(),
        )
        output_checkpoint = _build_output_checkpoint(
            opportunities=opportunities,
            hypotheses=hypotheses_payload["batch"],
            cells=cells_payload["registry"],
            ade_requests=ade_bundle["requests"],
            loop_status=loop_status,
        )
        latest_run_summary = {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_latest_run_summary",
            "run_id": lock.run_id,
            "state": final_state,
            "precheck_status": precheck["precheck_status"],
            "watermark_id": current_watermark["watermark_id"],
            "content_identity": _content_id(
                "qrlrs",
                {
                    "run_id": lock.run_id,
                    "state": final_state,
                    "precheck_status": precheck["precheck_status"],
                    "watermark_id": current_watermark["watermark_id"],
                },
            ),
        }
        promotion_artifacts = {"promotion_snapshot": None, "admission_snapshot": None}
        if write_outputs:
            promotion_artifacts = _write_ade_bridge_artifacts(
                repo_root=repo_root,
                proposal_intake_payload=_proposal_intake_payload(
                    request_rows=list(ade_bundle.get("active_requests") or []),
                ),
            )
        if write_outputs:
            _write_json(PRECHECK_PATH, precheck, repo_root=repo_root)
            _write_json(OPPORTUNITIES_PATH, opportunities, repo_root=repo_root)
            _write_json(HYPOTHESIS_BATCH_PATH, hypotheses_payload["batch"], repo_root=repo_root)
            _write_json(HYPOTHESIS_NOVELTY_PATH, hypotheses_payload["novelty"], repo_root=repo_root)
            _write_json(CAMPAIGN_CELL_PATH, cells_payload["registry"], repo_root=repo_root)
            _write_json(CAMPAIGN_CELL_NOVELTY_PATH, cells_payload["novelty"], repo_root=repo_root)
            _write_json(GAP_REGISTRY_PATH, gap_registry, repo_root=repo_root)
            _write_json(ADE_REQUESTS_PATH, ade_bundle["requests"], repo_root=repo_root)
            _write_json(ADE_FEEDBACK_PATH, feedback, repo_root=repo_root)
            _write_json(REQUEST_LIFECYCLE_PATH, request_lifecycle, repo_root=repo_root)
            _write_json(CONTINUATION_PLAN_PATH, continuation, repo_root=repo_root)
            _write_json(STATE_PATH, loop_status, repo_root=repo_root)
            _write_json(OUTPUT_CHECKPOINT_PATH, output_checkpoint, repo_root=repo_root)
            _write_json(LATEST_RUN_SUMMARY_PATH, latest_run_summary, repo_root=repo_root)
            _write_json(ROOT_CAUSE_PATH, root_cause, repo_root=repo_root)
            _write_json(
                RUN_PATH,
                {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": POLICY_VERSION,
                    "report_kind": REPORT_KIND,
                    "run_id": lock.run_id,
                    "state": final_state,
                    "precheck": precheck,
                    "watermark_id": current_watermark["watermark_id"],
                    "executed_campaigns": executed_campaigns,
                    "promotion_snapshot": promotion_artifacts["promotion_snapshot"],
                    "admission_snapshot": promotion_artifacts["admission_snapshot"],
                    "content_identity": _content_id("qrlr", {"run_id": lock.run_id, "state": final_state, "watermark": current_watermark["watermark_id"]}),
                },
                repo_root=repo_root,
            )
            _write_json(WATERMARK_PATH, current_watermark, repo_root=repo_root)
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "run_id": lock.run_id,
            "state": final_state,
            "watermark": current_watermark,
            "precheck": precheck,
            "opportunities": opportunities["summary"],
            "hypotheses": hypotheses_payload["batch"]["summary"],
            "campaign_cells": cells_payload["registry"]["summary"],
            "campaigns": {"executed": len(executed_campaigns)},
            "ade_requests": ade_bundle["requests"]["summary"],
            "resolution_feedback": feedback["summary"],
            "loop_status": loop_status,
        }
    finally:
        _release_lock(repo_root=repo_root)


__all__ = [
    "ADE_FEEDBACK_PATH",
    "ADE_REQUESTS_PATH",
    "CAMPAIGN_CELL_NOVELTY_PATH",
    "CAMPAIGN_CELL_PATH",
    "CAPABILITY_GAP_CLASSES",
    "CONTINUATION_PLAN_PATH",
    "DEFAULT_LIMITS",
    "GAP_REGISTRY_PATH",
    "HYPOTHESIS_BATCH_PATH",
    "HYPOTHESIS_NOVELTY_PATH",
    "LOCK_PATH",
    "LOOP_ROOT",
    "MODULE_VERSION",
    "OPPORTUNITIES_PATH",
    "POLICY_VERSION",
    "PRECHECK_PATH",
    "PRECHECK_STATUSES",
    "PROPOSAL_INTAKE_PATH",
    "REPORT_KIND",
    "RUN_PATH",
    "SCHEMA_VERSION",
    "STATE_PATH",
    "STATE_VALUES",
    "TRIGGER_TYPES",
    "WATERMARK_PATH",
    "build_precheck",
    "build_watermark",
    "consume_resolution_feedback",
    "discover_opportunities",
    "generate_hypothesis_batch",
    "materialize_campaign_cells",
    "run_opportunity_loop",
    "stable_digest",
]
