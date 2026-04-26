"""Campaign registry — source of truth for the v3.15.2 Campaign OS.

Per R3.3.2 the registry is the authoritative record of every campaign
spawned by the COL. The queue artifact is a *view* over non-terminal
registry entries plus lease metadata; if the two diverge, the queue is
rebuilt from the registry.

This module exposes:

- ``CampaignRecord`` — the frozen field set for a single campaign entry.
- ``build_campaign_id`` — deterministic, collision-proof id factory.
- Readers / writers over ``research/campaign_registry_latest.v1.json``.
- Pure transition helpers: ``transition_state``, ``record_outcome``.

Writers are pure transforms: they take the current registry dict, apply
a change, and return the new dict. The launcher is responsible for
persisting the result under the queue file lock.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_os_artifacts import build_pin_block, iso_utc
from research.campaign_templates import CampaignType

REGISTRY_SCHEMA_VERSION: str = "1.0"
REGISTRY_ARTIFACT_PATH: Path = Path(
    "research/campaign_registry_latest.v1.json"
)

CampaignState = Literal[
    "pending",
    "leased",
    "running",
    "completed",
    "failed",
    "canceled",
    "archived",
]

CAMPAIGN_STATES: tuple[str, ...] = (
    "pending",
    "leased",
    "running",
    "completed",
    "failed",
    "canceled",
    "archived",
)

CampaignOutcome = Literal[
    "completed_with_candidates",
    "completed_no_survivor",
    "degenerate_no_survivors",
    "research_rejection",
    "technical_failure",
    "paper_blocked",
    "integrity_failed",
    # DEPRECATED in v3.15.5 — kept only to validate historical records.
    # Post-v3.15.5 launcher emissions never produce ``worker_crashed``;
    # the runtime invariant in ``campaign_launcher`` enforces this. See
    # ``docs/handoffs/v3.15.5.md`` for the migration guidance.
    "worker_crashed",
    "aborted",
    "canceled_duplicate",
    "canceled_upstream_stale",
]

CAMPAIGN_OUTCOMES: tuple[str, ...] = (
    "completed_with_candidates",
    "completed_no_survivor",
    "degenerate_no_survivors",
    "research_rejection",
    "technical_failure",
    "paper_blocked",
    "integrity_failed",
    "worker_crashed",  # DEPRECATED v3.15.5; historical records only.
    "aborted",
    "canceled_duplicate",
    "canceled_upstream_stale",
)

# v3.15.5 — outcomes the campaign launcher is allowed to emit on a
# non-terminated, freshly classified run. ``worker_crashed`` is excluded
# on purpose: post-v3.15.5 the launcher must never produce it. The
# runtime invariant in ``campaign_launcher._apply_decision`` enforces
# this contract; the deprecated alias remains in ``CAMPAIGN_OUTCOMES``
# only for reading legacy records.
LAUNCHER_EMITTABLE_OUTCOMES: frozenset[str] = frozenset({
    "completed_with_candidates",
    "completed_no_survivor",
    "degenerate_no_survivors",
    "research_rejection",
    "technical_failure",
    "paper_blocked",
    "integrity_failed",
    "aborted",
    "canceled_duplicate",
    "canceled_upstream_stale",
})

MeaningfulClassification = Literal[
    "meaningful_candidate_found",
    "meaningful_family_falsified",
    "meaningful_failure_confirmed",
    "uninformative_technical_failure",
    "duplicate_low_value_run",
    "too_early_to_classify",
]

MEANINGFUL_CLASSIFICATIONS: tuple[str, ...] = (
    "meaningful_candidate_found",
    "meaningful_family_falsified",
    "meaningful_failure_confirmed",
    "uninformative_technical_failure",
    "duplicate_low_value_run",
    "too_early_to_classify",
)

# State machine — (from, to) tuples that are legal. Any other edge
# raises ``IllegalTransitionError``.
_LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pending", "leased"),
        ("pending", "canceled"),
        ("leased", "running"),
        ("leased", "pending"),          # R0 stale reclaim
        ("leased", "failed"),           # subprocess never started
        ("running", "completed"),
        ("running", "failed"),
        ("running", "pending"),         # R0 stale reclaim
        ("failed", "pending"),          # backoff retry
        ("completed", "archived"),
        ("failed", "archived"),
        ("canceled", "archived"),
    }
)


class IllegalTransitionError(RuntimeError):
    """Raised when a registry state transition violates the state machine."""


@dataclass(frozen=True)
class CampaignRecord:
    campaign_id: str
    template_id: str
    preset_name: str
    campaign_type: CampaignType
    state: CampaignState
    priority_tier: int
    spawned_at_utc: str
    leased_at_utc: str | None = None
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    attempt_count: int = 1
    run_id: str | None = None
    run_campaign_id: str | None = None
    outcome: CampaignOutcome | None = None
    meaningful_classification: MeaningfulClassification | None = None
    estimated_runtime_seconds: int = 0
    actual_runtime_seconds: int | None = None
    spawn_reason: str = "cron_tick"
    parent_campaign_id: str | None = None
    lineage_root_campaign_id: str = ""
    input_artifact_fingerprint: str = ""
    subtype: str | None = None
    strategy_family: str | None = None
    asset_class: str | None = None
    reason_code: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Campaign id (R3.3.3) — collision-proof, hashed-suffix
# ---------------------------------------------------------------------------


def build_campaign_id(
    *,
    preset_name: str,
    now_utc: datetime,
    parent_or_lineage_root: str | None,
    input_artifact_fingerprint: str,
    attempt_nonce: str | None = None,
) -> str:
    """Return a collision-proof ``col-*`` campaign id.

    Nonce defaults to ``uuid4().hex`` — does not break determinism of
    the policy output because the nonce is stored in the registry for
    the spawned campaign and re-used on replay.
    """
    ts = now_utc.astimezone(tz=None).strftime("%Y%m%dT%H%M%S%fZ")
    nonce = attempt_nonce if attempt_nonce is not None else uuid.uuid4().hex
    parent_key = parent_or_lineage_root if parent_or_lineage_root else "root"
    raw = (
        f"{ts}|{preset_name}|{parent_key}|{input_artifact_fingerprint}|{nonce}"
    ).encode("utf-8")
    suffix = hashlib.sha256(raw).hexdigest()[:10]
    return f"col-{ts}-{preset_name}-{suffix}"


def fingerprint_inputs(paths_and_hashes: dict[str, str]) -> str:
    """Derive the campaign's ``input_artifact_fingerprint``.

    Input: mapping of upstream artifact path → content hash (or
    mtime string — policy-agnostic). The output is a stable sha256 over
    the sorted key-value pairs.
    """
    items = sorted(paths_and_hashes.items())
    raw = "|".join(f"{k}={v}" for k, v in items).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def load_registry(path: Path = REGISTRY_ARTIFACT_PATH) -> dict[str, Any]:
    """Return the on-disk registry dict, or an empty skeleton if absent."""
    if not path.exists():
        return {"campaigns": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"campaigns": {}}
    if not isinstance(payload, dict):
        return {"campaigns": {}}
    payload.setdefault("campaigns", {})
    return payload


def write_registry(
    registry: dict[str, Any],
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    path: Path = REGISTRY_ARTIFACT_PATH,
) -> None:
    """Emit the canonical registry artifact with a fresh pin block."""
    pins = build_pin_block(
        schema_version=REGISTRY_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    campaigns = registry.get("campaigns", {}) or {}
    sorted_campaigns = {cid: campaigns[cid] for cid in sorted(campaigns)}
    payload = {**pins, "campaigns": sorted_campaigns}
    write_sidecar_atomic(path, payload)


# ---------------------------------------------------------------------------
# Pure state transformations
# ---------------------------------------------------------------------------


def get_record(
    registry: dict[str, Any],
    campaign_id: str,
) -> dict[str, Any] | None:
    return (registry.get("campaigns") or {}).get(campaign_id)


def upsert_record(
    registry: dict[str, Any],
    record: CampaignRecord,
) -> dict[str, Any]:
    """Return a new registry with ``record`` installed at its id."""
    campaigns = dict(registry.get("campaigns") or {})
    campaigns[record.campaign_id] = record.to_payload()
    return {**registry, "campaigns": campaigns}


def _require_record(
    registry: dict[str, Any],
    campaign_id: str,
) -> dict[str, Any]:
    record = get_record(registry, campaign_id)
    if record is None:
        raise KeyError(f"campaign_id {campaign_id!r} not in registry")
    return record


def transition_state(
    registry: dict[str, Any],
    *,
    campaign_id: str,
    to_state: CampaignState,
    at_utc: datetime,
    attempt_delta: int = 0,
    extra_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a new registry where ``campaign_id`` moves to ``to_state``.

    Raises ``IllegalTransitionError`` if the transition is not allowed.
    Writes ``leased_at_utc`` / ``started_at_utc`` / ``finished_at_utc``
    as appropriate.
    """
    current = _require_record(registry, campaign_id)
    from_state = str(current.get("state"))
    if (from_state, to_state) not in _LEGAL_TRANSITIONS:
        raise IllegalTransitionError(
            f"illegal transition {from_state!r} -> {to_state!r} for "
            f"campaign {campaign_id!r}"
        )
    updated = dict(current)
    updated["state"] = to_state
    ts_iso = iso_utc(at_utc)
    if to_state == "leased":
        updated["leased_at_utc"] = ts_iso
    elif to_state == "running":
        updated["started_at_utc"] = ts_iso
    elif to_state in ("completed", "failed", "canceled", "archived"):
        updated["finished_at_utc"] = ts_iso
    if attempt_delta:
        updated["attempt_count"] = int(updated.get("attempt_count") or 1) + int(
            attempt_delta
        )
    if extra_updates:
        updated.update(extra_updates)
    campaigns = dict(registry.get("campaigns") or {})
    campaigns[campaign_id] = updated
    return {**registry, "campaigns": campaigns}


def record_outcome(
    registry: dict[str, Any],
    *,
    campaign_id: str,
    outcome: CampaignOutcome,
    meaningful: MeaningfulClassification,
    actual_runtime_seconds: int,
    reason_code: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Set outcome metadata on a registry entry (typically on completion)."""
    current = _require_record(registry, campaign_id)
    if outcome not in CAMPAIGN_OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}")
    if meaningful not in MEANINGFUL_CLASSIFICATIONS:
        raise ValueError(f"unknown meaningful_classification {meaningful!r}")
    updated = dict(current)
    updated["outcome"] = outcome
    updated["meaningful_classification"] = meaningful
    updated["actual_runtime_seconds"] = int(actual_runtime_seconds)
    if reason_code is not None:
        updated["reason_code"] = reason_code
    if run_id is not None:
        updated["run_id"] = run_id
    campaigns = dict(registry.get("campaigns") or {})
    campaigns[campaign_id] = updated
    return {**registry, "campaigns": campaigns}


def records_in_states(
    registry: dict[str, Any],
    states: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        record
        for record in (registry.get("campaigns") or {}).values()
        if record.get("state") in states
    ]


def records_for_preset(
    registry: dict[str, Any],
    preset_name: str,
) -> list[dict[str, Any]]:
    return [
        record
        for record in (registry.get("campaigns") or {}).values()
        if record.get("preset_name") == preset_name
    ]


def has_duplicate(
    registry: dict[str, Any],
    *,
    campaign_type: CampaignType,
    preset_name: str,
    parent_or_lineage_root: str | None,
    input_artifact_fingerprint: str,
    exclude_campaign_id: str | None = None,
) -> bool:
    """Return True iff a non-archived, non-canceled duplicate exists.

    Uniqueness key per R3.6.1:
    ``(campaign_type, preset_name, parent_or_lineage_root, fingerprint)``

    For a root campaign the caller passes ``parent_or_lineage_root=None``
    and the function matches records whose ``parent_campaign_id`` is
    null (ignoring their self-referential ``lineage_root_campaign_id``,
    which is always the record's own id). For a child campaign the
    caller passes the parent id; the function matches records whose
    ``parent_campaign_id`` equals that value.
    """
    for cid, record in (registry.get("campaigns") or {}).items():
        if exclude_campaign_id is not None and cid == exclude_campaign_id:
            continue
        if record.get("state") in ("archived", "canceled"):
            continue
        if record.get("campaign_type") != campaign_type:
            continue
        if record.get("preset_name") != preset_name:
            continue
        record_parent = record.get("parent_campaign_id")
        if parent_or_lineage_root is None:
            if record_parent not in (None, ""):
                continue
        else:
            if record_parent != parent_or_lineage_root:
                continue
        if record.get("input_artifact_fingerprint") != input_artifact_fingerprint:
            continue
        return True
    return False


def has_child_of_type(
    registry: dict[str, Any],
    *,
    parent_campaign_id: str,
    followup_campaign_type: CampaignType,
) -> bool:
    """True iff the registry already carries a non-canceled child."""
    for record in (registry.get("campaigns") or {}).values():
        if record.get("parent_campaign_id") != parent_campaign_id:
            continue
        if record.get("campaign_type") != followup_campaign_type:
            continue
        if record.get("state") in ("canceled", "archived"):
            continue
        return True
    return False


__all__ = [
    "CAMPAIGN_OUTCOMES",
    "CAMPAIGN_STATES",
    "MEANINGFUL_CLASSIFICATIONS",
    "CampaignOutcome",
    "CampaignRecord",
    "CampaignState",
    "IllegalTransitionError",
    "MeaningfulClassification",
    "REGISTRY_ARTIFACT_PATH",
    "REGISTRY_SCHEMA_VERSION",
    "build_campaign_id",
    "fingerprint_inputs",
    "get_record",
    "has_child_of_type",
    "has_duplicate",
    "load_registry",
    "record_outcome",
    "records_for_preset",
    "records_in_states",
    "transition_state",
    "upsert_record",
    "write_registry",
]


def records_for_lineage_root(
    registry: dict[str, Any],
    lineage_root_campaign_id: str,
) -> list[dict[str, Any]]:
    return [
        record
        for record in (registry.get("campaigns") or {}).values()
        if record.get("lineage_root_campaign_id") == lineage_root_campaign_id
    ]
