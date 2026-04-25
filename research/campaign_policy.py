"""Campaign policy engine — the pure ``decide(...)`` function.

Executes the 5-phase, 8-step flow from plan §R3.2. Consumes only its
explicit inputs; produces a single ``CampaignDecision`` and an artifact
trace. Same inputs → byte-identical artifact (invariant I6).

The engine never writes state itself. The launcher takes the decision
and applies the corresponding side-effect inside the queue-lock critical
section.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_budget import (
    BudgetState,
    remaining_for_tier,
    tier1_fairness_engaged,
)
from research.campaign_evidence_ledger import time_since_last
from research.campaign_family_policy import FamilyPolicyState
from research.campaign_os_artifacts import build_pin_block
from research.campaign_preset_policy import PresetPolicyState
from research.campaign_registry import (
    has_child_of_type,
    has_duplicate,
    records_for_preset,
    records_in_states,
)
from research.campaign_templates import (
    CampaignOsConfig,
    CampaignTemplate,
    CampaignType,
    EligibilityPredicate,
)
from research.presets import get_preset
from research.registry import STRATEGIES
from research.strategy_hypothesis_catalog import (
    get_by_family as _hypothesis_get_by_family,
)

POLICY_SCHEMA_VERSION: str = "1.0"
POLICY_DECISION_PATH: Path = Path(
    "research/campaign_policy_decision_latest.v1.json"
)

PolicyAction = Literal[
    "spawn",
    "skip_cooldown",
    "skip_budget",
    "skip_frozen",
    "idle_noop",
    "reclaim_stale_lease",
    "cancel_duplicate",
    "cancel_upstream_stale",
]


@dataclass(frozen=True)
class DecisionRecord:
    """What the launcher should do this tick."""

    action: PolicyAction
    reason: str
    campaign_id: str | None = None
    template_id: str | None = None
    preset_name: str | None = None
    campaign_type: CampaignType | None = None
    priority_tier: int | None = None
    spawn_reason: str | None = None
    parent_campaign_id: str | None = None
    lineage_root_campaign_id: str | None = None
    subtype: str | None = None
    estimate_seconds: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateRejection:
    template_id: str
    preset_name: str
    campaign_type: CampaignType
    appended_in_phase: str
    appended_index: int
    reject_reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CampaignDecision:
    decision: DecisionRecord
    rules_evaluated: tuple[dict[str, Any], ...]
    candidates_considered: tuple[dict[str, Any], ...]
    tie_break_key: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_payload(),
            "rules_evaluated": [dict(r) for r in self.rules_evaluated],
            "candidates_considered": [dict(c) for c in self.candidates_considered],
            "tie_break_key": list(self.tie_break_key),
        }


@dataclass(frozen=True)
class _CandidateSpec:
    template: CampaignTemplate
    appended_in_phase: str  # "A" / "B" / "C" / "D"
    appended_index: int
    preset_name: str
    campaign_type: CampaignType
    parent_campaign_id: str | None
    lineage_root_campaign_id: str
    spawn_reason: str
    subtype: str | None
    input_artifact_fingerprint: str
    estimate_seconds: int
    effective_priority_tier: int

    def tie_break_key(self) -> tuple[int, str, int, str]:
        return (
            int(self.effective_priority_tier),
            self.appended_in_phase,
            int(self.appended_index),
            self.template.template_id,
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def decide(
    *,
    registry: dict[str, Any],
    queue: dict[str, Any],
    events: list[dict[str, Any]],
    budget: BudgetState,
    templates: tuple[CampaignTemplate, ...],
    config: CampaignOsConfig,
    preset_state_by_name: dict[str, PresetPolicyState],
    family_state_by_key: dict[str, FamilyPolicyState],
    upstream_artifact_states: dict[str, str],
    follow_up_candidate_specs: tuple[_CandidateSpec, ...] = (),
    weekly_control_candidate_specs: tuple[_CandidateSpec, ...] = (),
    now_utc: datetime,
) -> CampaignDecision:
    """Pure policy decision for one launcher tick.

    ``follow_up_candidate_specs`` / ``weekly_control_candidate_specs``
    are provided by the launcher after running ``derive_followups`` and
    ``derive_weekly_controls`` — the engine does not scan parents
    itself, so its input surface is fully explicit.
    """
    rules: list[dict[str, Any]] = []

    # Step 1 — reclaim stale leases.
    stale = _find_stale_lease(queue, now_utc)
    if stale is not None:
        rules.append(
            {
                "rule_id": "R0_stale_lease_reclaim",
                "result": "trigger",
                "campaign_id": stale,
            }
        )
        return _build_decision(
            decision=DecisionRecord(
                action="reclaim_stale_lease",
                reason="lease_expired",
                campaign_id=stale,
            ),
            rules=rules,
            candidates=(),
        )
    rules.append({"rule_id": "R0_stale_lease_reclaim", "result": "n/a"})

    # Step 2 — cancel invalid pending entries (R1 + R2).
    upstream_stale_cid = _find_upstream_stale(
        queue, upstream_artifact_states=upstream_artifact_states
    )
    if upstream_stale_cid is not None:
        rules.append(
            {
                "rule_id": "R1_upstream_stale_cancel",
                "result": "trigger",
                "campaign_id": upstream_stale_cid,
            }
        )
        return _build_decision(
            decision=DecisionRecord(
                action="cancel_upstream_stale",
                reason="upstream_stale",
                campaign_id=upstream_stale_cid,
            ),
            rules=rules,
            candidates=(),
        )
    rules.append({"rule_id": "R1_upstream_stale_cancel", "result": "n/a"})

    duplicate_cid = _find_registry_duplicate_pending(registry, queue)
    if duplicate_cid is not None:
        rules.append(
            {
                "rule_id": "R2_cancel_duplicate",
                "result": "trigger",
                "campaign_id": duplicate_cid,
            }
        )
        return _build_decision(
            decision=DecisionRecord(
                action="cancel_duplicate",
                reason="duplicate_detected",
                campaign_id=duplicate_cid,
            ),
            rules=rules,
            candidates=(),
        )
    rules.append({"rule_id": "R2_cancel_duplicate", "result": "n/a"})

    # Step 3 — single-worker admission.
    active_leases = [
        r
        for r in records_in_states(registry, ("leased", "running"))
    ]
    if len(active_leases) >= int(config.max_concurrent_campaigns):
        rules.append({"rule_id": "R3_single_worker", "result": "block"})
        return _build_decision(
            decision=DecisionRecord(action="idle_noop", reason="worker_busy"),
            rules=rules,
            candidates=(),
        )
    rules.append({"rule_id": "R3_single_worker", "result": "allow"})

    # Step 4 — build global candidate set.
    candidate_set = list(follow_up_candidate_specs)
    candidate_set.extend(
        _phase_b_primary(
            templates=templates,
            registry=registry,
            events=events,
            preset_state_by_name=preset_state_by_name,
            now_utc=now_utc,
        )
    )
    candidate_set.extend(weekly_control_candidate_specs)
    candidate_set.extend(
        _phase_d_weekly_retest(
            templates=templates,
            preset_state_by_name=preset_state_by_name,
            events=events,
            now_utc=now_utc,
        )
    )

    # Step 5 — filtering pipeline.
    surviving: list[_CandidateSpec] = []
    rejections: list[CandidateRejection] = []
    for spec in candidate_set:
        reject = _filter_candidate(
            spec,
            registry=registry,
            events=events,
            budget=budget,
            preset_state_by_name=preset_state_by_name,
            family_state_by_key=family_state_by_key,
            all_follow_up_specs=follow_up_candidate_specs,
        )
        if reject is None:
            surviving.append(spec)
        else:
            rejections.append(reject)
    rules.append(
        {
            "rule_id": "R4_R7_filtering",
            "result": "candidates",
            "surviving": len(surviving),
            "rejected": len(rejections),
        }
    )

    # Step 6 — global deterministic sort.
    surviving.sort(key=lambda s: s.tie_break_key())

    # Step 7 — select first candidate.
    if not surviving:
        rules.append({"rule_id": "R8_idle", "result": "fire"})
        return _build_decision(
            decision=DecisionRecord(action="idle_noop", reason="no_candidates"),
            rules=rules,
            candidates=_rejections_payload(rejections),
        )

    chosen = surviving[0]
    rules.append(
        {
            "rule_id": "R8_idle",
            "result": "n/a",
            "selected": chosen.template.template_id,
        }
    )
    decision = DecisionRecord(
        action="spawn",
        reason=chosen.spawn_reason,
        campaign_id=None,  # launcher mints the id post-policy
        template_id=chosen.template.template_id,
        preset_name=chosen.preset_name,
        campaign_type=chosen.campaign_type,
        priority_tier=chosen.effective_priority_tier,
        spawn_reason=chosen.spawn_reason,
        parent_campaign_id=chosen.parent_campaign_id,
        lineage_root_campaign_id=chosen.lineage_root_campaign_id,
        subtype=chosen.subtype,
        estimate_seconds=chosen.estimate_seconds,
        extra={
            "input_artifact_fingerprint": chosen.input_artifact_fingerprint,
            "appended_in_phase": chosen.appended_in_phase,
            "appended_index": chosen.appended_index,
        },
    )
    candidate_payload = _rejections_payload(rejections) + tuple(
        {
            "template_id": s.template.template_id,
            "preset_name": s.preset_name,
            "campaign_type": s.campaign_type,
            "appended_in_phase": s.appended_in_phase,
            "appended_index": s.appended_index,
            "effective_priority_tier": s.effective_priority_tier,
            "result": "surviving",
        }
        for s in surviving
    )
    return _build_decision(
        decision=decision,
        rules=rules,
        candidates=candidate_payload,
    )


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def _find_stale_lease(
    queue: dict[str, Any],
    now_utc: datetime,
) -> str | None:
    for entry in queue.get("queue") or []:
        if entry.get("state") not in ("leased", "running"):
            continue
        lease = entry.get("lease")
        if not isinstance(lease, dict):
            continue
        expires = lease.get("expires_utc")
        if not isinstance(expires, str):
            continue
        try:
            expires_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            return str(entry.get("campaign_id") or "")
        if now_utc.astimezone(UTC) >= expires_dt.astimezone(UTC):
            return str(entry.get("campaign_id") or "")
    return None


def _find_upstream_stale(
    queue: dict[str, Any],
    *,
    upstream_artifact_states: dict[str, str],
) -> str | None:
    if not any(state == "stale" for state in upstream_artifact_states.values()):
        return None
    for entry in queue.get("queue") or []:
        if entry.get("state") == "pending":
            return str(entry.get("campaign_id") or "")
    return None


def _find_registry_duplicate_pending(
    registry: dict[str, Any],
    queue: dict[str, Any],
) -> str | None:
    """Detect a pending queue entry whose key already exists elsewhere."""
    campaigns = registry.get("campaigns") or {}
    for entry in queue.get("queue") or []:
        if entry.get("state") != "pending":
            continue
        cid = entry.get("campaign_id")
        record = campaigns.get(cid) if isinstance(cid, str) else None
        if not record:
            continue
        dup = has_duplicate(
            registry,
            campaign_type=str(record.get("campaign_type") or ""),  # type: ignore[arg-type]
            preset_name=str(record.get("preset_name") or ""),
            parent_or_lineage_root=(
                record.get("parent_campaign_id")
                or record.get("lineage_root_campaign_id")
            ),
            input_artifact_fingerprint=str(
                record.get("input_artifact_fingerprint") or ""
            ),
            exclude_campaign_id=str(cid),
        )
        if dup:
            return str(cid)
    return None


def _phase_b_primary(
    *,
    templates: tuple[CampaignTemplate, ...],
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    preset_state_by_name: dict[str, PresetPolicyState],
    now_utc: datetime,
) -> list[_CandidateSpec]:
    out: list[_CandidateSpec] = []
    sorted_templates = sorted(
        [t for t in templates if t.campaign_type == "daily_primary"],
        key=lambda t: t.template_id,
    )
    for idx, template in enumerate(sorted_templates):
        state = preset_state_by_name.get(template.preset_name)
        if state is not None and state.policy_state == "frozen":
            continue
        effective_cooldown = int(template.cooldown_seconds)
        if state is not None:
            effective_cooldown = max(
                effective_cooldown,
                int(state.effective_cooldown_seconds),
            )
        last_spawn = time_since_last(
            events,
            preset_name=template.preset_name,
            event_type="campaign_spawned",
            now_utc=now_utc,
        )
        if last_spawn is not None and last_spawn < effective_cooldown:
            continue
        priority_tier = int(template.priority_tier)
        if state is not None:
            priority_tier = min(
                priority_tier + int(state.priority_tier_delta),
                3,
            )
        out.append(
            _CandidateSpec(
                template=template,
                appended_in_phase="B",
                appended_index=idx,
                preset_name=template.preset_name,
                campaign_type="daily_primary",
                parent_campaign_id=None,
                lineage_root_campaign_id="",
                spawn_reason="cron_tick",
                subtype=None,
                input_artifact_fingerprint="",
                estimate_seconds=int(template.estimated_runtime_seconds_default),
                effective_priority_tier=priority_tier,
            )
        )
    return out


def _phase_d_weekly_retest(
    *,
    templates: tuple[CampaignTemplate, ...],
    preset_state_by_name: dict[str, PresetPolicyState],
    events: list[dict[str, Any]],
    now_utc: datetime,
) -> list[_CandidateSpec]:
    out: list[_CandidateSpec] = []
    sorted_templates = sorted(
        [t for t in templates if t.campaign_type == "weekly_retest"],
        key=lambda t: t.template_id,
    )
    for idx, template in enumerate(sorted_templates):
        state = preset_state_by_name.get(template.preset_name)
        if state is None or state.policy_state == "active":
            continue
        # Require cooldown-based gap since the last retest spawn.
        last_spawn = time_since_last(
            events,
            preset_name=template.preset_name,
            event_type="campaign_spawned",
            now_utc=now_utc,
        )
        if last_spawn is not None and last_spawn < int(template.cooldown_seconds):
            continue
        out.append(
            _CandidateSpec(
                template=template,
                appended_in_phase="D",
                appended_index=idx,
                preset_name=template.preset_name,
                campaign_type="weekly_retest",
                parent_campaign_id=None,
                lineage_root_campaign_id="",
                spawn_reason=f"retest_{state.policy_state}",
                subtype=state.policy_state,
                input_artifact_fingerprint="",
                estimate_seconds=int(template.estimated_runtime_seconds_default),
                effective_priority_tier=3,
            )
        )
    return out


def _filter_candidate(
    spec: _CandidateSpec,
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    budget: BudgetState,
    preset_state_by_name: dict[str, PresetPolicyState],
    family_state_by_key: dict[str, FamilyPolicyState],
    all_follow_up_specs: tuple[_CandidateSpec, ...],
) -> CandidateRejection | None:
    template = spec.template

    # Filter 0 — template eligibility predicate (v3.15.2 hotfix).
    # Honours operator-set preset flags before any other gate so that
    # ``excluded_from_daily_scheduler``, ``diagnostic_only``, ``enabled``,
    # and ``status`` are enforced uniformly across every phase
    # (follow-ups, daily_primary, daily_control, weekly_retest). A
    # missing preset rejects defensively.
    eligibility_rejection = _check_template_eligibility(spec)
    if eligibility_rejection is not None:
        return eligibility_rejection

    # Filter 1 — already guarded upstream for primaries/retests; for
    # follow-ups we re-check frozen-preset gate here so eligibility is
    # uniform.
    preset_state = preset_state_by_name.get(spec.preset_name)
    if preset_state is not None and preset_state.policy_state == "frozen":
        if spec.campaign_type != "weekly_retest":
            return CandidateRejection(
                template_id=template.template_id,
                preset_name=spec.preset_name,
                campaign_type=spec.campaign_type,
                appended_in_phase=spec.appended_in_phase,
                appended_index=spec.appended_index,
                reject_reason="preset_frozen",
            )

    # Filter 3 — family deprioritized / frozen.
    family_key = _guess_family_key(registry, spec.preset_name)
    family_state = family_state_by_key.get(family_key)
    if family_state is not None:
        if family_state.policy_state == "frozen" and spec.campaign_type in (
            "survivor_confirmation",
            "paper_followup",
        ):
            return CandidateRejection(
                template_id=template.template_id,
                preset_name=spec.preset_name,
                campaign_type=spec.campaign_type,
                appended_in_phase=spec.appended_in_phase,
                appended_index=spec.appended_index,
                reject_reason=f"family_frozen:{family_state.strategy_family}",
            )
        if (
            family_state.policy_state == "deprioritized"
            and spec.campaign_type == "survivor_confirmation"
        ):
            return CandidateRejection(
                template_id=template.template_id,
                preset_name=spec.preset_name,
                campaign_type=spec.campaign_type,
                appended_in_phase=spec.appended_in_phase,
                appended_index=spec.appended_index,
                reject_reason="family_deprioritized_survivor_confirmation",
            )

    # Filter 5 — duplicate prevention.
    if has_duplicate(
        registry,
        campaign_type=spec.campaign_type,
        preset_name=spec.preset_name,
        parent_or_lineage_root=spec.parent_campaign_id or spec.lineage_root_campaign_id,
        input_artifact_fingerprint=spec.input_artifact_fingerprint,
    ):
        return CandidateRejection(
            template_id=template.template_id,
            preset_name=spec.preset_name,
            campaign_type=spec.campaign_type,
            appended_in_phase=spec.appended_in_phase,
            appended_index=spec.appended_index,
            reject_reason="duplicate_forbidden",
        )

    # Filter 4 — follow-up idempotency (R3.6.3).
    if spec.parent_campaign_id and has_child_of_type(
        registry,
        parent_campaign_id=spec.parent_campaign_id,
        followup_campaign_type=spec.campaign_type,
    ):
        return CandidateRejection(
            template_id=template.template_id,
            preset_name=spec.preset_name,
            campaign_type=spec.campaign_type,
            appended_in_phase=spec.appended_in_phase,
            appended_index=spec.appended_index,
            reject_reason="followup_already_exists",
        )

    # Filter 6 — budget pre-check with dynamic reservation.
    active_followup_estimates = tuple(
        s.estimate_seconds for s in all_follow_up_specs
    )
    if tier1_fairness_engaged(budget) and spec.effective_priority_tier == 1:
        # Fairness demotion for this tick.
        effective_tier = 2
    else:
        effective_tier = int(spec.effective_priority_tier)
    remaining = remaining_for_tier(
        budget,
        tier=effective_tier,
        active_followup_candidate_estimates=active_followup_estimates,
    )
    if spec.estimate_seconds > remaining:
        return CandidateRejection(
            template_id=template.template_id,
            preset_name=spec.preset_name,
            campaign_type=spec.campaign_type,
            appended_in_phase=spec.appended_in_phase,
            appended_index=spec.appended_index,
            reject_reason="budget",
            details={
                "estimate_seconds": spec.estimate_seconds,
                "remaining": remaining,
                "effective_tier": effective_tier,
            },
        )

    # Filter 7 — per-template daily cap.
    used_today = int(
        budget.per_template_used_today.get(template.template_id, 0)
    )
    if used_today >= int(template.max_per_day):
        return CandidateRejection(
            template_id=template.template_id,
            preset_name=spec.preset_name,
            campaign_type=spec.campaign_type,
            appended_in_phase=spec.appended_in_phase,
            appended_index=spec.appended_index,
            reject_reason="daily_cap_reached",
        )
    return None


def _check_template_eligibility(
    spec: _CandidateSpec,
) -> CandidateRejection | None:
    """Apply the template's ``EligibilityPredicate`` against the live preset.

    v3.15.2 hotfix: prior to this filter the policy engine appended
    candidates without consulting ``template.eligibility``, so presets
    flagged ``excluded_from_daily_scheduler=True`` or
    ``diagnostic_only=True`` could still be selected for ``daily_primary``.
    Centralising the check here covers every phase (A/B/C/D) and every
    follow-up template.

    A preset whose name is no longer in the catalog is rejected with
    ``preset_not_in_catalog`` so a stale follow-up cannot run against
    a removed preset definition.

    v3.15.3: when the template declares ``require_hypothesis_status``
    (default ``()``), the bridged strategy_hypothesis_catalog row must
    carry one of the allowed statuses. The bridge is preset →
    bundle[0] → registry.strategy_family → catalog. Empty bundles or
    missing strategies / families surface as canonical reject reasons
    so the campaign launcher records *why* a tick stalled.
    """
    template = spec.template
    eligibility: EligibilityPredicate = template.eligibility
    try:
        preset = get_preset(spec.preset_name)
    except KeyError:
        return _build_eligibility_rejection(spec, "preset_not_in_catalog")

    if eligibility.require_preset_enabled and not preset.enabled:
        return _build_eligibility_rejection(spec, "preset_disabled")
    if (
        eligibility.forbid_excluded_from_daily_scheduler
        and preset.excluded_from_daily_scheduler
    ):
        return _build_eligibility_rejection(
            spec, "preset_excluded_from_daily_scheduler"
        )
    if eligibility.forbid_diagnostic_only and preset.diagnostic_only:
        return _build_eligibility_rejection(spec, "preset_diagnostic_only")
    if (
        eligibility.require_preset_status
        and preset.status not in eligibility.require_preset_status
    ):
        return _build_eligibility_rejection(
            spec,
            f"preset_status_{preset.status}_not_in_required",
        )
    if eligibility.require_hypothesis_status:
        rejection = _check_hypothesis_status(spec, preset, eligibility)
        if rejection is not None:
            return rejection
    return None


def _check_hypothesis_status(
    spec: _CandidateSpec,
    preset: Any,
    eligibility: EligibilityPredicate,
) -> CandidateRejection | None:
    """Resolve the preset's hypothesis and gate on its catalog status.

    Bridge: preset.bundle[0] → STRATEGIES[strategy_family] →
    STRATEGY_HYPOTHESIS_CATALOG[strategy_family]. The first bundle
    entry is treated as the controlling strategy for the hypothesis
    bridge — multi-strategy bundles carry diagnostic intent and are
    out of scope for v3.15.3.
    """
    if not preset.bundle:
        return _build_eligibility_rejection(spec, "preset_bundle_empty")
    strategy_name = preset.bundle[0]
    strategy_family = _strategy_family_for(strategy_name)
    if strategy_family is None:
        return _build_eligibility_rejection(
            spec, "strategy_not_in_registry"
        )
    try:
        hypothesis = _hypothesis_get_by_family(strategy_family)
    except KeyError:
        return _build_eligibility_rejection(
            spec, "hypothesis_not_in_catalog"
        )
    if hypothesis.status not in eligibility.require_hypothesis_status:
        return _build_eligibility_rejection(
            spec,
            f"hypothesis_status_{hypothesis.status}_not_in_required",
        )
    return None


def _strategy_family_for(strategy_name: str) -> str | None:
    """Look up the registry strategy_family for ``strategy_name``."""
    for entry in STRATEGIES:
        if entry.get("name") == strategy_name:
            family = entry.get("strategy_family")
            return str(family) if family is not None else None
    return None


def _build_eligibility_rejection(
    spec: _CandidateSpec,
    reject_reason: str,
) -> CandidateRejection:
    return CandidateRejection(
        template_id=spec.template.template_id,
        preset_name=spec.preset_name,
        campaign_type=spec.campaign_type,
        appended_in_phase=spec.appended_in_phase,
        appended_index=spec.appended_index,
        reject_reason=reject_reason,
        details={
            "require_preset_enabled": (
                spec.template.eligibility.require_preset_enabled
            ),
            "forbid_excluded_from_daily_scheduler": (
                spec.template.eligibility.forbid_excluded_from_daily_scheduler
            ),
            "forbid_diagnostic_only": (
                spec.template.eligibility.forbid_diagnostic_only
            ),
            "require_preset_status": list(
                spec.template.eligibility.require_preset_status
            ),
            "require_hypothesis_status": list(
                spec.template.eligibility.require_hypothesis_status
            ),
        },
    )


def _guess_family_key(registry: dict[str, Any], preset_name: str) -> str:
    """Best-effort family key lookup from any completed record for the preset."""
    for record in records_for_preset(registry, preset_name):
        family = record.get("strategy_family")
        asset = record.get("asset_class")
        if family and asset:
            return f"{family}|{asset}"
    return "unknown|unknown"


def _rejections_payload(
    rejections: list[CandidateRejection],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "template_id": r.template_id,
            "preset_name": r.preset_name,
            "campaign_type": r.campaign_type,
            "appended_in_phase": r.appended_in_phase,
            "appended_index": r.appended_index,
            "reject_reason": r.reject_reason,
            "details": dict(r.details),
            "result": "rejected",
        }
        for r in rejections
    )


def _build_decision(
    *,
    decision: DecisionRecord,
    rules: list[dict[str, Any]],
    candidates: tuple[dict[str, Any], ...],
) -> CampaignDecision:
    return CampaignDecision(
        decision=decision,
        rules_evaluated=tuple(rules),
        candidates_considered=candidates,
        tie_break_key=("effective_priority_tier", "appended_in_phase", "appended_index", "template_id"),
    )


def write_decision(
    decision: CampaignDecision,
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    path: Path = POLICY_DECISION_PATH,
) -> None:
    pins = build_pin_block(
        schema_version=POLICY_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    payload = {**pins, **decision.to_payload()}
    write_sidecar_atomic(path, payload)


__all__ = [
    "POLICY_DECISION_PATH",
    "POLICY_SCHEMA_VERSION",
    "CampaignDecision",
    "CandidateRejection",
    "DecisionRecord",
    "PolicyAction",
    "decide",
    "write_decision",
]


# Re-export the private _CandidateSpec so the launcher can build and
# pass follow-up/control candidate specs to ``decide`` without the
# engine re-walking the registry.
CandidateSpec = _CandidateSpec  # noqa: E305
__all__.append("CandidateSpec")
