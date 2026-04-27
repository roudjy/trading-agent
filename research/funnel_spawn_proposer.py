"""v3.15.12 — Funnel Spawn Proposer (advisory observability).

Forward-looking complement to the v3.15.11 backward-looking
intelligence layer. Reads:

  - screening_evidence (v3.15.9)
  - evidence_ledger (v3.15.11)
  - information_gain (v3.15.11)
  - stop_conditions (v3.15.11)
  - dead_zones (v3.15.11)
  - viability (v3.15.11)
  - campaign_registry (v3.15.2)
  - spawn_proposal_history.jsonl (this module, append-only)

Emits:

  - spawn_proposals_latest.v1.json — current proposal snapshot
  - spawn_proposal_history.jsonl  — append-only fingerprint log

Hard positioning:

- Advisory only. Top-level enforcement_state="advisory_only" and
  mode="shadow". Future modes ("evaluation", "gated_consumption")
  are out of scope for v3.15.12.
- Never mutates the queue, the registry, the ledger JSONL, or any
  frozen contract.
- Never modifies campaign_policy.decide() — pinned by regression
  test in v3.15.11.

Six hardenings vs the original sketch:

1. proposal_fingerprint covers 6 fields (hypothesis, preset,
   parameter_grid_signature, timeframe, asset, proposal_type).
2. Per-fingerprint cooldown (FINGERPRINT_COOLDOWN_DAYS, default 7).
3. Exploration coverage enforced over BOTH percentage AND scope
   spread (families ≥ 3, assets ≥ 3, timeframes ≥ 2 with graceful
   fallback).
4. Dead-zone suppression decays after DEAD_ZONE_DECAY_DAYS
   (default 14) — never permanent on low data.
5. viability == stop_or_pivot toggles proposal_mode =
   "diagnostic_only", drops HIGH-tier proposals, caps at
   MAX_PROPOSALS_PER_RUN_DIAGNOSTIC (3).
6. Deterministic priority_tier enum (HIGH / MEDIUM / LOW /
   SUPPRESSED) plus reason_trace[] on every proposal AND every
   suppressed zone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal

from research._sidecar_io import write_sidecar_atomic

# ── constants ──────────────────────────────────────────────────────────

SPAWN_PROPOSALS_SCHEMA_VERSION: Final[str] = "1.0"
SPAWN_PROPOSALS_PATH: Final[Path] = Path(
    "research/campaigns/evidence/spawn_proposals_latest.v1.json"
)
SPAWN_PROPOSAL_HISTORY_PATH: Final[Path] = Path(
    "research/campaigns/evidence/spawn_proposal_history.jsonl"
)

ENFORCEMENT_STATE_ADVISORY: Final[str] = "advisory_only"
MODE_SHADOW: Final[str] = "shadow"
PROPOSAL_MODE_NORMAL: Final[str] = "normal"
PROPOSAL_MODE_DIAGNOSTIC: Final[str] = "diagnostic_only"

# Coverage targets — single inspection point.
EXPLORATION_RESERVATION_PCT: Final[float] = 0.20
EXPLORATION_MIN_DISTINCT_FAMILIES: Final[int] = 3
EXPLORATION_MIN_DISTINCT_ASSETS: Final[int] = 3
EXPLORATION_MIN_DISTINCT_TIMEFRAMES: Final[int] = 2

MAX_PROPOSALS_PER_RUN_NORMAL: Final[int] = 10
MAX_PROPOSALS_PER_RUN_DIAGNOSTIC: Final[int] = 3

FINGERPRINT_COOLDOWN_DAYS: Final[int] = 7
DEAD_ZONE_DECAY_DAYS: Final[int] = 14

# Priority tier enum + ordering.
PriorityTier = Literal["HIGH", "MEDIUM", "LOW", "SUPPRESSED"]
PRIORITY_TIER_ORDER: Final[tuple[str, ...]] = (
    "HIGH",
    "MEDIUM",
    "LOW",
    "SUPPRESSED",
)
PRIORITY_TIER_RANK: Final[dict[str, int]] = {
    tier: idx for idx, tier in enumerate(PRIORITY_TIER_ORDER)
}

# Proposal type vocabulary (closed set, kept in sync with rules).
PROPOSAL_TYPE_CONFIRMATION: Final[str] = "confirmation_campaign"
PROPOSAL_TYPE_PARAM_RETRY: Final[str] = "parameter_adjacent_retry"
PROPOSAL_TYPE_ADJACENT_PRESET: Final[str] = "adjacent_preset_campaign"
PROPOSAL_TYPE_EXPLORATION: Final[str] = "exploration_reservation_unknown_zone"
PROPOSAL_TYPE_DEAD_ZONE_REVISIT: Final[str] = "dead_zone_decayed_revisit"
PROPOSAL_TYPE_DIVERSIFICATION: Final[str] = "hypothesis_diversification"

UNKNOWN: Final[str] = "unknown"


# ── dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProposedCampaign:
    preset_name: str
    hypothesis_id: str
    asset: str
    timeframe: str
    strategy_family: str
    parameter_grid_signature: str
    proposal_type: str
    spawn_reason: str
    priority_tier: str
    lineage: dict[str, Any]
    rationale_codes: list[str]
    reason_trace: list[str]
    expected_information_gain_bucket: str | None
    source_signal: str
    proposal_fingerprint: str


@dataclass(frozen=True)
class SuppressedZone:
    asset: str
    strategy_family: str
    reason_codes: list[str]
    reason_trace: list[str]
    suppression_until_utc: str | None
    time_since_last_attempt_days: int | None


@dataclass
class _ProposalDraft:
    """Mutable assembly form. Becomes ProposedCampaign once finalized."""

    preset_name: str
    hypothesis_id: str
    asset: str
    timeframe: str
    strategy_family: str
    parameter_grid_signature: str
    proposal_type: str
    spawn_reason: str
    priority_tier: str
    source_signal: str
    expected_information_gain_bucket: str | None = None
    lineage: dict[str, Any] = field(default_factory=dict)
    rationale_codes: list[str] = field(default_factory=list)
    reason_trace: list[str] = field(default_factory=list)


# ── fingerprint + history ──────────────────────────────────────────────


def compute_proposal_fingerprint(
    *,
    hypothesis_id: str,
    preset_name: str,
    parameter_grid_signature: str,
    timeframe: str,
    asset: str,
    proposal_type: str,
) -> str:
    """Six-field deterministic sha1.

    Includes proposal_type so two different proposal kinds on the
    same scope (e.g. confirmation vs parameter_adjacent_retry on the
    same preset) cannot collapse to a single fingerprint.
    """
    payload = json.dumps(
        {
            "hypothesis_id": str(hypothesis_id or ""),
            "preset_name": str(preset_name or ""),
            "parameter_grid_signature": str(parameter_grid_signature or ""),
            "timeframe": str(timeframe or ""),
            "asset": str(asset or ""),
            "proposal_type": str(proposal_type or ""),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


def load_recent_proposal_fingerprints(
    *,
    history_path: Path,
    now_utc: datetime,
    cooldown_days: int = FINGERPRINT_COOLDOWN_DAYS,
) -> set[str]:
    """Return fingerprints emitted within the cooldown window."""
    if not history_path.exists():
        return set()
    cutoff = (now_utc - timedelta(days=cooldown_days)).astimezone(UTC)
    fingerprints: set[str] = set()
    try:
        with history_path.open("r", encoding="utf-8") as h:
            for line in h:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = record.get("generated_at_utc")
                fp = record.get("fingerprint")
                if not isinstance(fp, str) or not isinstance(ts_raw, str):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts.astimezone(UTC) >= cutoff:
                    fingerprints.add(fp)
    except OSError:
        return set()
    return fingerprints


def append_proposal_history(
    *,
    history_path: Path,
    proposals: list[ProposedCampaign],
    run_id: str | None,
    generated_at_utc: datetime,
) -> int:
    """Append fingerprints of kept proposals. Returns count appended."""
    if not proposals:
        return 0
    history_path.parent.mkdir(parents=True, exist_ok=True)
    iso_ts = generated_at_utc.astimezone(UTC).isoformat()
    written = 0
    with history_path.open("a", encoding="utf-8", newline="\n") as h:
        for p in proposals:
            record = {
                "fingerprint": p.proposal_fingerprint,
                "generated_at_utc": iso_ts,
                "run_id": run_id,
                "preset_name": p.preset_name,
                "proposal_type": p.proposal_type,
                "priority_tier": p.priority_tier,
            }
            h.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            h.write("\n")
            written += 1
    return written


# ── helper queries ─────────────────────────────────────────────────────


def _registry_active_fingerprints(
    *,
    campaign_registry: dict[str, Any] | None,
    now_utc: datetime,
    window_days: int = FINGERPRINT_COOLDOWN_DAYS,
) -> set[str]:
    """Synthesise fingerprints for active/recent registry entries.

    Best-effort: if the registry doesn't carry the necessary fields,
    we just return a minimal hypothesis+preset hash. Idempotency
    against the queue is enforced by COL itself; this filter is
    defensive against the proposer re-emitting work that's clearly
    already in flight.
    """
    if campaign_registry is None:
        return set()
    cutoff = (now_utc - timedelta(days=window_days)).astimezone(UTC)
    fingerprints: set[str] = set()
    entries = campaign_registry.get("campaigns")
    if isinstance(entries, dict):
        records: list[dict[str, Any]] = list(entries.values())
    elif isinstance(entries, list):
        records = entries
    else:
        records = []
    for record in records:
        if not isinstance(record, dict):
            continue
        spawned_at = record.get("spawned_at_utc") or record.get("created_at_utc")
        if isinstance(spawned_at, str):
            try:
                ts = datetime.fromisoformat(spawned_at.replace("Z", "+00:00"))
            except ValueError:
                ts = None
            if ts is not None and ts.astimezone(UTC) < cutoff:
                # Old enough — don't block re-proposal.
                continue
        preset = str(record.get("preset_name") or "")
        if not preset:
            continue
        # Approximate fingerprint: zero-out fields we don't know.
        fp = compute_proposal_fingerprint(
            hypothesis_id=str(record.get("hypothesis_id") or UNKNOWN),
            preset_name=preset,
            parameter_grid_signature=str(record.get("parameter_grid_signature") or ""),
            timeframe=str(record.get("timeframe") or ""),
            asset=str(record.get("asset_class") or record.get("asset") or ""),
            proposal_type=PROPOSAL_TYPE_CONFIRMATION,
        )
        fingerprints.add(fp)
    return fingerprints


def _hypothesis_protection(
    *,
    evidence_ledger: dict[str, Any] | None,
    preset_name: str,
) -> bool:
    """True iff the rolled hypothesis_evidence shows existing
    promotion/paper protection for this preset."""
    if evidence_ledger is None:
        return False
    rows = evidence_ledger.get("hypothesis_evidence") or []
    for row in rows:
        if str(row.get("preset_name") or "") != preset_name:
            continue
        if int(row.get("promotion_candidate_count") or 0) > 0:
            return True
        if int(row.get("paper_ready_count") or 0) > 0:
            return True
    return False


def _preset_blocked_by_stop_conditions(
    *,
    stop_conditions: dict[str, Any] | None,
    preset_name: str,
    strategy_family: str,
) -> tuple[bool, list[str]]:
    """True iff stop_conditions has a RETIRE/FREEZE recommendation
    for this preset (or its family).

    Returns (blocked, reason_codes_for_trace).
    """
    if stop_conditions is None:
        return (False, [])
    decisions = stop_conditions.get("decisions") or []
    blockers = {"RETIRE_HYPOTHESIS", "RETIRE_FAMILY", "FREEZE_PRESET"}
    matched: list[str] = []
    for d in decisions:
        if str(d.get("recommended_decision") or "") not in blockers:
            continue
        scope_id = str(d.get("scope_id") or "")
        scope_type = str(d.get("scope_type") or "")
        if scope_type == "preset" and scope_id == preset_name:
            matched.append(f"stop_condition:{scope_type}:{scope_id}")
        if scope_type == "strategy_family" and scope_id == strategy_family:
            matched.append(f"stop_condition:{scope_type}:{scope_id}")
    return (len(matched) > 0, matched)


def _zone_for(
    dead_zones: dict[str, Any] | None,
    *,
    asset: str,
    strategy_family: str,
) -> dict[str, Any] | None:
    if dead_zones is None:
        return None
    for z in dead_zones.get("zones") or []:
        if str(z.get("asset") or "") != asset:
            continue
        if str(z.get("strategy_family") or "") != strategy_family:
            continue
        return z
    return None


def _zone_last_attempt_days(
    *,
    evidence_ledger: dict[str, Any] | None,
    asset: str,
    strategy_family: str,
    now_utc: datetime,
) -> int | None:
    """Days since the most-recent campaign in this zone.

    Walks the rolled hypothesis_evidence (per-preset, but each carries
    strategy_family). If no row matches the zone or no last_seen_at_utc
    is available, returns None.
    """
    if evidence_ledger is None:
        return None
    rows = evidence_ledger.get("hypothesis_evidence") or []
    latest: datetime | None = None
    for row in rows:
        if str(row.get("strategy_family") or "") != strategy_family:
            continue
        # Asset isn't on hypothesis_evidence rows directly, so we
        # accept any preset in this family as a proxy for "last
        # attempt in zone". This is conservative (reports more
        # recent activity than reality) which favors NOT decaying
        # — safer.
        ts_raw = row.get("last_seen_at_utc")
        if not isinstance(ts_raw, str):
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        return None
    delta = now_utc.astimezone(UTC) - latest.astimezone(UTC)
    return max(0, delta.days)


# ── rules ──────────────────────────────────────────────────────────────


def _propose_from_screening_evidence(
    *,
    screening_evidence: dict[str, Any] | None,
    stop_conditions: dict[str, Any] | None,
    dead_zones: dict[str, Any] | None,
    evidence_ledger: dict[str, Any] | None,
    information_gain: dict[str, Any] | None,
    now_utc: datetime,
) -> list[_ProposalDraft]:
    """R1 (confirmation) + R2 (parameter_adjacent_retry).

    Iterates per-candidate, building drafts that downstream rules
    will filter.
    """
    drafts: list[_ProposalDraft] = []
    if screening_evidence is None:
        return drafts
    candidates = screening_evidence.get("candidates") or []
    ig_bucket = (
        (information_gain.get("information_gain") or {}).get("bucket")
        if information_gain
        else None
    )
    for record in candidates:
        if not isinstance(record, dict):
            continue
        stage_result = record.get("stage_result")
        pass_kind = record.get("pass_kind")
        preset = str(record.get("preset_name") or "")
        hypothesis = str(record.get("hypothesis_id") or UNKNOWN)
        asset = str(record.get("asset") or UNKNOWN)
        timeframe = str(record.get("interval") or UNKNOWN)
        strategy_family = str(record.get("strategy_family") or UNKNOWN)
        sampling = record.get("sampling") or {}
        grid_sig = str(sampling.get("sampled_parameter_digest") or "")
        if not preset:
            continue

        # R1 — confirmation
        if (
            stage_result == "needs_investigation"
            and pass_kind == "exploratory"
        ):
            trace = ["exploratory_pass_detected"]
            blocked, scope_traces = _preset_blocked_by_stop_conditions(
                stop_conditions=stop_conditions,
                preset_name=preset,
                strategy_family=strategy_family,
            )
            if blocked:
                continue
            trace.append("stop_conditions_clear_for_scope")
            zone = _zone_for(
                dead_zones, asset=asset, strategy_family=strategy_family
            )
            if zone and zone.get("zone_status") == "dead":
                # Active-deadzone: skip even confirmation. R4 will
                # log it as a suppressed zone.
                continue
            trace.append("not_in_dead_zone")
            drafts.append(
                _ProposalDraft(
                    preset_name=preset,
                    hypothesis_id=hypothesis,
                    asset=asset,
                    timeframe=timeframe,
                    strategy_family=strategy_family,
                    parameter_grid_signature=grid_sig,
                    proposal_type=PROPOSAL_TYPE_CONFIRMATION,
                    spawn_reason="confirmation_from_exploratory_pass",
                    priority_tier="HIGH",
                    source_signal="screening_evidence",
                    expected_information_gain_bucket=ig_bucket,
                    rationale_codes=[
                        "exploratory_pass_observed",
                        "no_confirmation_run_in_recent_window",
                    ],
                    reason_trace=trace,
                )
            )
            continue

        # R2 — near-pass parameter retry
        near = record.get("near_pass") or {}
        if (
            stage_result == "near_pass"
            and bool(near.get("is_near_pass"))
        ):
            trace = ["near_pass_detected"]
            failed = near.get("nearest_failed_criterion")
            if failed:
                trace.append(f"nearest_failed_criterion={failed}")
            blocked, _ = _preset_blocked_by_stop_conditions(
                stop_conditions=stop_conditions,
                preset_name=preset,
                strategy_family=strategy_family,
            )
            if blocked:
                continue
            trace.append("stop_conditions_clear_for_scope")
            zone = _zone_for(
                dead_zones, asset=asset, strategy_family=strategy_family
            )
            if zone and zone.get("zone_status") == "dead":
                continue
            trace.append("not_in_dead_zone")
            drafts.append(
                _ProposalDraft(
                    preset_name=preset,
                    hypothesis_id=hypothesis,
                    asset=asset,
                    timeframe=timeframe,
                    strategy_family=strategy_family,
                    parameter_grid_signature=grid_sig,
                    proposal_type=PROPOSAL_TYPE_PARAM_RETRY,
                    spawn_reason="parameter_adjacent_retry_from_near_pass",
                    priority_tier="MEDIUM",
                    source_signal="screening_evidence",
                    expected_information_gain_bucket=ig_bucket,
                    rationale_codes=[
                        "near_pass_observed",
                        f"nearest_failed_criterion={failed}" if failed else "near_pass",
                    ],
                    reason_trace=trace,
                )
            )
    return drafts


def _propose_from_dead_zones(
    *,
    dead_zones: dict[str, Any] | None,
    evidence_ledger: dict[str, Any] | None,
    information_gain: dict[str, Any] | None,
    now_utc: datetime,
) -> tuple[list[_ProposalDraft], list[SuppressedZone]]:
    """R4 (dead suppression w/ decay), R5 (weak adjacent),
    R6 (exploration candidates), R6-IG (high-IG expansion)."""
    drafts: list[_ProposalDraft] = []
    suppressed: list[SuppressedZone] = []
    if dead_zones is None:
        return drafts, suppressed
    zones = dead_zones.get("zones") or []
    ig_bucket = (
        (information_gain.get("information_gain") or {}).get("bucket")
        if information_gain
        else None
    )
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        status = zone.get("zone_status")
        asset = str(zone.get("asset") or UNKNOWN)
        family = str(zone.get("strategy_family") or UNKNOWN)
        last_attempt_days = _zone_last_attempt_days(
            evidence_ledger=evidence_ledger,
            asset=asset,
            strategy_family=family,
            now_utc=now_utc,
        )

        if status == "dead":
            decayed = (
                last_attempt_days is not None
                and last_attempt_days > DEAD_ZONE_DECAY_DAYS
            )
            if not decayed:
                # R4: active dead-zone suppression.
                until = (
                    (
                        now_utc
                        + timedelta(
                            days=DEAD_ZONE_DECAY_DAYS - (last_attempt_days or 0)
                        )
                    )
                    .astimezone(UTC)
                    .isoformat()
                )
                suppressed.append(
                    SuppressedZone(
                        asset=asset,
                        strategy_family=family,
                        reason_codes=["dead_zone_active_within_decay_window"],
                        reason_trace=[
                            "dead_zone_status_active",
                            f"time_since_last_attempt_days={last_attempt_days}",
                            f"<= DEAD_ZONE_DECAY_DAYS={DEAD_ZONE_DECAY_DAYS}",
                        ],
                        suppression_until_utc=until,
                        time_since_last_attempt_days=last_attempt_days,
                    )
                )
                continue
            # R4-decay: dead but old enough → eligible LOW revisit.
            drafts.append(
                _ProposalDraft(
                    preset_name=f"{family}_{asset}_revisit",
                    hypothesis_id=UNKNOWN,
                    asset=asset,
                    timeframe=UNKNOWN,
                    strategy_family=family,
                    parameter_grid_signature="",
                    proposal_type=PROPOSAL_TYPE_DEAD_ZONE_REVISIT,
                    spawn_reason="dead_zone_decay_passed",
                    priority_tier="LOW",
                    source_signal="dead_zones",
                    expected_information_gain_bucket=ig_bucket,
                    rationale_codes=["dead_zone_decay_passed"],
                    reason_trace=[
                        "dead_zone_status_active",
                        f"time_since_last_attempt_days={last_attempt_days} > "
                        f"DEAD_ZONE_DECAY_DAYS={DEAD_ZONE_DECAY_DAYS}",
                        "dead_zone_decay_passed",
                    ],
                )
            )
            continue

        if status == "weak":
            drafts.append(
                _ProposalDraft(
                    preset_name=f"{family}_{asset}_adjacent",
                    hypothesis_id=UNKNOWN,
                    asset=asset,
                    timeframe=UNKNOWN,
                    strategy_family=family,
                    parameter_grid_signature="",
                    proposal_type=PROPOSAL_TYPE_ADJACENT_PRESET,
                    spawn_reason="adjacent_from_weak_zone",
                    priority_tier="MEDIUM",
                    source_signal="dead_zones",
                    expected_information_gain_bucket=ig_bucket,
                    rationale_codes=["zone_status=weak"],
                    reason_trace=["zone_status=weak"],
                )
            )
            continue

        if status in {"unknown", "insufficient_data"}:
            drafts.append(
                _ProposalDraft(
                    preset_name=f"{family}_{asset}_explore",
                    hypothesis_id=UNKNOWN,
                    asset=asset,
                    timeframe=UNKNOWN,
                    strategy_family=family,
                    parameter_grid_signature="",
                    proposal_type=PROPOSAL_TYPE_EXPLORATION,
                    spawn_reason="exploration_reservation_unknown_zone",
                    priority_tier="LOW",
                    source_signal="dead_zones",
                    expected_information_gain_bucket=ig_bucket,
                    rationale_codes=[f"zone_status={status}"],
                    reason_trace=[f"zone_status={status}"],
                )
            )
            continue

        if (
            status == "alive"
            and ig_bucket == "high"
            and (last_attempt_days or 0) > 3
        ):
            # R6-IG: high-IG zone hasn't been touched recently.
            drafts.append(
                _ProposalDraft(
                    preset_name=f"{family}_{asset}_expand",
                    hypothesis_id=UNKNOWN,
                    asset=asset,
                    timeframe=UNKNOWN,
                    strategy_family=family,
                    parameter_grid_signature="",
                    proposal_type=PROPOSAL_TYPE_ADJACENT_PRESET,
                    spawn_reason="high_information_gain_expansion",
                    priority_tier="MEDIUM",
                    source_signal="information_gain",
                    expected_information_gain_bucket=ig_bucket,
                    rationale_codes=[
                        "information_gain_bucket=high",
                        f"time_since_last_attempt_days={last_attempt_days}",
                    ],
                    reason_trace=[
                        "zone_status=alive",
                        "information_gain_bucket=high",
                        f"time_since_last_attempt_days={last_attempt_days}>3",
                    ],
                )
            )

    return drafts, suppressed


def _filter_by_fingerprint_cooldown(
    drafts: list[_ProposalDraft],
    *,
    cooldown_fingerprints: set[str],
) -> tuple[list[_ProposalDraft], int]:
    """R9-cooldown."""
    kept: list[_ProposalDraft] = []
    blocked = 0
    for draft in drafts:
        fp = compute_proposal_fingerprint(
            hypothesis_id=draft.hypothesis_id,
            preset_name=draft.preset_name,
            parameter_grid_signature=draft.parameter_grid_signature,
            timeframe=draft.timeframe,
            asset=draft.asset,
            proposal_type=draft.proposal_type,
        )
        if fp in cooldown_fingerprints:
            blocked += 1
            continue
        draft.reason_trace.append("fingerprint_not_in_cooldown")
        kept.append(draft)
    return kept, blocked


def _filter_by_active_registry(
    drafts: list[_ProposalDraft],
    *,
    active_fingerprints: set[str],
) -> list[_ProposalDraft]:
    """R9-active."""
    kept: list[_ProposalDraft] = []
    for draft in drafts:
        fp = compute_proposal_fingerprint(
            hypothesis_id=draft.hypothesis_id,
            preset_name=draft.preset_name,
            parameter_grid_signature=draft.parameter_grid_signature,
            timeframe=draft.timeframe,
            asset=draft.asset,
            proposal_type=draft.proposal_type,
        )
        if fp in active_fingerprints:
            continue
        draft.reason_trace.append("no_active_or_queued_duplicate")
        kept.append(draft)
    return kept


def _enforce_exploration_reservation(
    drafts: list[_ProposalDraft],
    *,
    pct_target: float = EXPLORATION_RESERVATION_PCT,
    family_target: int = EXPLORATION_MIN_DISTINCT_FAMILIES,
    asset_target: int = EXPLORATION_MIN_DISTINCT_ASSETS,
    timeframe_target: int = EXPLORATION_MIN_DISTINCT_TIMEFRAMES,
) -> tuple[list[_ProposalDraft], list[str]]:
    """R7. Enforce both pct AND scope spread; record shortfalls."""
    if not drafts:
        return drafts, []
    exploration_drafts = [
        d
        for d in drafts
        if d.proposal_type
        in (
            PROPOSAL_TYPE_EXPLORATION,
            PROPOSAL_TYPE_DEAD_ZONE_REVISIT,
            PROPOSAL_TYPE_DIVERSIFICATION,
        )
    ]
    pct_actual = len(exploration_drafts) / len(drafts) if drafts else 0.0
    families = {d.strategy_family for d in drafts}
    assets = {d.asset for d in drafts}
    timeframes = {d.timeframe for d in drafts}

    shortfalls: list[str] = []
    if pct_actual < pct_target:
        shortfalls.append("exploration_reservation_pct_below_target")
    if len(families) < family_target:
        shortfalls.append("distinct_families_below_target")
    if len(assets) < asset_target:
        shortfalls.append("distinct_assets_below_target")
    if len(timeframes) < timeframe_target:
        shortfalls.append("distinct_timeframes_below_target")

    # Graceful fallback: this release records shortfalls but does
    # not synthesise new exploration proposals out of thin air.
    # When the catalog supplies enough zones (Phase 2 evaluation
    # validates this), a future release can lift the lowest-priority
    # confirmation/adjacent and replace.
    return drafts, shortfalls


def _apply_proposal_mode(
    *,
    drafts: list[_ProposalDraft],
    viability: dict[str, Any] | None,
) -> tuple[list[_ProposalDraft], str, bool]:
    """R8.

    Returns (drafts, proposal_mode, human_review_required).
    """
    verdict = (viability.get("verdict") if viability else None) or {}
    status = verdict.get("status")
    if status != "stop_or_pivot":
        return drafts, PROPOSAL_MODE_NORMAL, False
    # Diagnostic mode: drop HIGH, allow only LOW.
    pruned: list[_ProposalDraft] = []
    for d in drafts:
        if d.priority_tier == "HIGH":
            continue
        if d.priority_tier == "MEDIUM":
            continue
        d.reason_trace.append(
            "proposal_mode=diagnostic_only_kept_low_only"
        )
        pruned.append(d)
    return pruned, PROPOSAL_MODE_DIAGNOSTIC, True


def _sort_and_cap(
    drafts: list[_ProposalDraft],
    *,
    proposal_mode: str,
) -> list[_ProposalDraft]:
    """R10. Sort by tier then fingerprint asc; cap by mode."""
    fingerprinted = []
    for d in drafts:
        fp = compute_proposal_fingerprint(
            hypothesis_id=d.hypothesis_id,
            preset_name=d.preset_name,
            parameter_grid_signature=d.parameter_grid_signature,
            timeframe=d.timeframe,
            asset=d.asset,
            proposal_type=d.proposal_type,
        )
        fingerprinted.append((PRIORITY_TIER_RANK.get(d.priority_tier, 99), fp, d))
    fingerprinted.sort(key=lambda t: (t[0], t[1]))
    cap = (
        MAX_PROPOSALS_PER_RUN_DIAGNOSTIC
        if proposal_mode == PROPOSAL_MODE_DIAGNOSTIC
        else MAX_PROPOSALS_PER_RUN_NORMAL
    )
    return [t[2] for t in fingerprinted[:cap]]


def _finalize(
    drafts: list[_ProposalDraft],
) -> list[ProposedCampaign]:
    finalized: list[ProposedCampaign] = []
    for d in drafts:
        fp = compute_proposal_fingerprint(
            hypothesis_id=d.hypothesis_id,
            preset_name=d.preset_name,
            parameter_grid_signature=d.parameter_grid_signature,
            timeframe=d.timeframe,
            asset=d.asset,
            proposal_type=d.proposal_type,
        )
        d.reason_trace.append(f"priority_tier_assigned={d.priority_tier}")
        finalized.append(
            ProposedCampaign(
                preset_name=d.preset_name,
                hypothesis_id=d.hypothesis_id,
                asset=d.asset,
                timeframe=d.timeframe,
                strategy_family=d.strategy_family,
                parameter_grid_signature=d.parameter_grid_signature,
                proposal_type=d.proposal_type,
                spawn_reason=d.spawn_reason,
                priority_tier=d.priority_tier,
                lineage=dict(d.lineage),
                rationale_codes=list(d.rationale_codes),
                reason_trace=list(d.reason_trace),
                expected_information_gain_bucket=d.expected_information_gain_bucket,
                source_signal=d.source_signal,
                proposal_fingerprint=fp,
            )
        )
    return finalized


# ── builder ────────────────────────────────────────────────────────────


def build_spawn_proposals_payload(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    screening_evidence: dict[str, Any] | None,
    evidence_ledger: dict[str, Any] | None,
    information_gain: dict[str, Any] | None,
    stop_conditions: dict[str, Any] | None,
    dead_zones: dict[str, Any] | None,
    viability: dict[str, Any] | None,
    campaign_registry: dict[str, Any] | None,
    cooldown_fingerprints: set[str] | None = None,
) -> dict[str, Any]:
    """Pure builder. No I/O."""
    cooldown = cooldown_fingerprints or set()
    active = _registry_active_fingerprints(
        campaign_registry=campaign_registry,
        now_utc=as_of_utc,
    )

    drafts_a = _propose_from_screening_evidence(
        screening_evidence=screening_evidence,
        stop_conditions=stop_conditions,
        dead_zones=dead_zones,
        evidence_ledger=evidence_ledger,
        information_gain=information_gain,
        now_utc=as_of_utc,
    )
    drafts_b, suppressed = _propose_from_dead_zones(
        dead_zones=dead_zones,
        evidence_ledger=evidence_ledger,
        information_gain=information_gain,
        now_utc=as_of_utc,
    )
    drafts = drafts_a + drafts_b

    drafts, cooldown_blocks = _filter_by_fingerprint_cooldown(
        drafts, cooldown_fingerprints=cooldown
    )
    drafts = _filter_by_active_registry(drafts, active_fingerprints=active)
    drafts, shortfalls = _enforce_exploration_reservation(drafts)
    drafts, proposal_mode, human_review = _apply_proposal_mode(
        drafts=drafts, viability=viability
    )
    drafts = _sort_and_cap(drafts, proposal_mode=proposal_mode)
    final_proposals = _finalize(drafts)

    families = {p.strategy_family for p in final_proposals}
    assets = {p.asset for p in final_proposals}
    timeframes = {p.timeframe for p in final_proposals}
    exploration_proposals = [
        p
        for p in final_proposals
        if p.proposal_type
        in (
            PROPOSAL_TYPE_EXPLORATION,
            PROPOSAL_TYPE_DEAD_ZONE_REVISIT,
            PROPOSAL_TYPE_DIVERSIFICATION,
        )
    ]
    pct_actual = (
        len(exploration_proposals) / len(final_proposals)
        if final_proposals
        else 0.0
    )

    candidate_zones = []
    for z in (dead_zones or {}).get("zones") or []:
        if z.get("zone_status") in {"unknown", "insufficient_data"}:
            candidate_zones.append(
                {
                    "asset": str(z.get("asset") or UNKNOWN),
                    "strategy_family": str(z.get("strategy_family") or UNKNOWN),
                    "current_status": str(z.get("zone_status") or UNKNOWN),
                }
            )

    verdict_block = (viability.get("verdict") if viability else None) or {}
    return {
        "schema_version": SPAWN_PROPOSALS_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": run_id,
        "enforcement_state": ENFORCEMENT_STATE_ADVISORY,
        "mode": MODE_SHADOW,
        "proposal_mode": proposal_mode,
        "summary": {
            "proposed_count": len(final_proposals),
            "suppressed_zone_count": len(suppressed),
            "human_review_required": human_review,
            "exploration_coverage": {
                "pct_target": EXPLORATION_RESERVATION_PCT,
                "pct_actual": round(pct_actual, 4),
                "distinct_families_target": EXPLORATION_MIN_DISTINCT_FAMILIES,
                "distinct_families_actual": len(families),
                "distinct_assets_target": EXPLORATION_MIN_DISTINCT_ASSETS,
                "distinct_assets_actual": len(assets),
                "distinct_timeframes_target": EXPLORATION_MIN_DISTINCT_TIMEFRAMES,
                "distinct_timeframes_actual": len(timeframes),
                "shortfall_reason_codes": shortfalls,
            },
            "fingerprint_cooldown_blocks": cooldown_blocks,
        },
        "proposed_campaigns": [
            {
                "preset_name": p.preset_name,
                "hypothesis_id": p.hypothesis_id,
                "asset": p.asset,
                "timeframe": p.timeframe,
                "strategy_family": p.strategy_family,
                "parameter_grid_signature": p.parameter_grid_signature,
                "proposal_type": p.proposal_type,
                "spawn_reason": p.spawn_reason,
                "priority_tier": p.priority_tier,
                "lineage": p.lineage,
                "rationale_codes": p.rationale_codes,
                "reason_trace": p.reason_trace,
                "expected_information_gain_bucket": p.expected_information_gain_bucket,
                "source_signal": p.source_signal,
                "proposal_fingerprint": p.proposal_fingerprint,
            }
            for p in final_proposals
        ],
        "suppressed_zones": [
            {
                "asset": s.asset,
                "strategy_family": s.strategy_family,
                "reason_codes": s.reason_codes,
                "reason_trace": s.reason_trace,
                "suppression_until_utc": s.suppression_until_utc,
                "time_since_last_attempt_days": s.time_since_last_attempt_days,
            }
            for s in suppressed
        ],
        "exploration_reservation": {
            "pct_target": EXPLORATION_RESERVATION_PCT,
            "candidate_zones": candidate_zones,
        },
        "human_review_required": {
            "active": human_review,
            "reason_codes": list(verdict_block.get("reason_codes") or [])
            if human_review
            else [],
        },
    }


def write_spawn_proposals_artifact(
    *,
    run_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    screening_evidence: dict[str, Any] | None,
    evidence_ledger: dict[str, Any] | None,
    information_gain: dict[str, Any] | None,
    stop_conditions: dict[str, Any] | None,
    dead_zones: dict[str, Any] | None,
    viability: dict[str, Any] | None,
    campaign_registry: dict[str, Any] | None,
    output_path: Path = SPAWN_PROPOSALS_PATH,
    history_path: Path = SPAWN_PROPOSAL_HISTORY_PATH,
) -> dict[str, Any]:
    """Build payload, write sidecar, append kept proposals to history."""
    cooldown = load_recent_proposal_fingerprints(
        history_path=history_path, now_utc=as_of_utc
    )
    payload = build_spawn_proposals_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        git_revision=git_revision,
        screening_evidence=screening_evidence,
        evidence_ledger=evidence_ledger,
        information_gain=information_gain,
        stop_conditions=stop_conditions,
        dead_zones=dead_zones,
        viability=viability,
        campaign_registry=campaign_registry,
        cooldown_fingerprints=cooldown,
    )
    write_sidecar_atomic(output_path, payload)
    proposals_for_history = [
        ProposedCampaign(
            preset_name=p["preset_name"],
            hypothesis_id=p["hypothesis_id"],
            asset=p["asset"],
            timeframe=p["timeframe"],
            strategy_family=p["strategy_family"],
            parameter_grid_signature=p["parameter_grid_signature"],
            proposal_type=p["proposal_type"],
            spawn_reason=p["spawn_reason"],
            priority_tier=p["priority_tier"],
            lineage=p["lineage"],
            rationale_codes=p["rationale_codes"],
            reason_trace=p["reason_trace"],
            expected_information_gain_bucket=p["expected_information_gain_bucket"],
            source_signal=p["source_signal"],
            proposal_fingerprint=p["proposal_fingerprint"],
        )
        for p in payload["proposed_campaigns"]
    ]
    append_proposal_history(
        history_path=history_path,
        proposals=proposals_for_history,
        run_id=run_id,
        generated_at_utc=as_of_utc,
    )
    return payload


__all__ = [
    "DEAD_ZONE_DECAY_DAYS",
    "ENFORCEMENT_STATE_ADVISORY",
    "EXPLORATION_MIN_DISTINCT_ASSETS",
    "EXPLORATION_MIN_DISTINCT_FAMILIES",
    "EXPLORATION_MIN_DISTINCT_TIMEFRAMES",
    "EXPLORATION_RESERVATION_PCT",
    "FINGERPRINT_COOLDOWN_DAYS",
    "MAX_PROPOSALS_PER_RUN_DIAGNOSTIC",
    "MAX_PROPOSALS_PER_RUN_NORMAL",
    "MODE_SHADOW",
    "PRIORITY_TIER_ORDER",
    "PRIORITY_TIER_RANK",
    "PROPOSAL_MODE_DIAGNOSTIC",
    "PROPOSAL_MODE_NORMAL",
    "PROPOSAL_TYPE_ADJACENT_PRESET",
    "PROPOSAL_TYPE_CONFIRMATION",
    "PROPOSAL_TYPE_DEAD_ZONE_REVISIT",
    "PROPOSAL_TYPE_DIVERSIFICATION",
    "PROPOSAL_TYPE_EXPLORATION",
    "PROPOSAL_TYPE_PARAM_RETRY",
    "ProposedCampaign",
    "SPAWN_PROPOSALS_PATH",
    "SPAWN_PROPOSALS_SCHEMA_VERSION",
    "SPAWN_PROPOSAL_HISTORY_PATH",
    "SuppressedZone",
    "append_proposal_history",
    "build_spawn_proposals_payload",
    "compute_proposal_fingerprint",
    "load_recent_proposal_fingerprints",
    "write_spawn_proposals_artifact",
]
