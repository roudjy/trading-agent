"""v3.15.10 — pure campaign funnel policy.

Reads ``research/screening_evidence_latest.v1.json`` (v3.15.9
artifact) plus the existing campaign registry / evidence ledger
and emits deterministic ``FunnelDecision`` records.

Pure module: NO I/O, NO subprocess, NO tracker calls. The
launcher consumes the returned decisions and applies them
(side-effecting work lives in ``research.campaign_launcher``).

Decision codes (REV 3 §7.1):

  - confirmation_from_exploratory_pass         : exploratory pass /
                                                  needs_investigation
  - follow_up_from_near_pass                   : near-pass evidence
  - alternate_timeframe_from_insufficient_trades : insufficient_trades
                                                  AND alt-timeframe
                                                  support exists
  - cooldown_from_repeat_rejection             : streak >= 3 OR
                                                  insufficient_trades
                                                  with no alt-timeframe
  - coverage_followup_from_low_sampling_coverage : sampling defect
                                                  signal (no spawn)
  - no_action_technical_failure                : registry record
                                                  has outcome ==
                                                  "technical_failure"

Spawn vs no-spawn (REV 3 §7.4 + MF-8 vocabulary):

  v3.15.10 IS allowed to enqueue spawn requests for
  ``confirmation_from_exploratory_pass`` and
  ``follow_up_from_near_pass``. The spawned campaign uses
  ``campaign_type="survivor_confirmation"`` (the closest existing
  CampaignType — no taxonomy change in v3.15.10) with funnel
  metadata in ``extra``. ``extra.requested_screening_phase`` is
  recorded as decision-only metadata: the spawned campaign runs
  at the parent preset's natural ``screening_phase``. v3.15.11+
  will wire executor support for the requested-phase override.

Ownership (REV 3 §7.2 + MF-7):

  Evidence is matched to a campaign via
  ``col_campaign_id`` first, falling back to ``campaign_id``.
  Mismatch / missing evidence does NOT block a
  ``no_action_technical_failure`` decision derived from the
  registry record.

Dedupe (REV 3 §7.9 + MF-15):

  ``has_funnel_spawn_for(...)`` matches on
  ``(parent_campaign_id, decision_code, extra.lineage_candidate_id,
   extra.screening_evidence_fingerprint)``. Same-candidate same-
  fingerprint blocks; same-candidate different-fingerprint blocks
  only while a prior matching campaign is in
  ``ACTIVE_CAMPAIGN_STATES``; different-candidate always allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from research.campaign_followup import SpawnRequest


FUNNEL_DECISION_CONFIRMATION: Final[str] = "confirmation_from_exploratory_pass"
FUNNEL_DECISION_NEAR_PASS_FOLLOWUP: Final[str] = "follow_up_from_near_pass"
FUNNEL_DECISION_ALT_TIMEFRAME: Final[str] = (
    "alternate_timeframe_from_insufficient_trades"
)
FUNNEL_DECISION_COVERAGE_FOLLOWUP: Final[str] = (
    "coverage_followup_from_low_sampling_coverage"
)
FUNNEL_DECISION_COOLDOWN_REPEAT: Final[str] = "cooldown_from_repeat_rejection"
FUNNEL_DECISION_NO_ACTION_TECHNICAL: Final[str] = "no_action_technical_failure"


DECISION_PRIORITY: Final[dict[str, int]] = {
    FUNNEL_DECISION_CONFIRMATION:        10,
    FUNNEL_DECISION_NEAR_PASS_FOLLOWUP:  20,
    FUNNEL_DECISION_ALT_TIMEFRAME:       30,
    FUNNEL_DECISION_COVERAGE_FOLLOWUP:   40,
    FUNNEL_DECISION_COOLDOWN_REPEAT:     50,
    FUNNEL_DECISION_NO_ACTION_TECHNICAL: 60,
}


REPEAT_REJECTION_STREAK_THRESHOLD: Final[int] = 3
LOW_COVERAGE_TRIGGER_PCT: Final[float] = 0.80


# Closed sets of campaign states (REV 3 §7.9). Sourced from
# CAMPAIGN_STATES at research/campaign_registry.py:39-57.
TERMINAL_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset(
    {"completed", "failed", "canceled", "archived"}
)
ACTIVE_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset(
    {"pending", "leased", "running"}
)


# Stage-result strings exported by screening_evidence (kept as
# string literals here so this module does not import from
# screening_evidence and create a cycle).
_EXPLORATORY_PASS_STAGE_RESULT: Final[str] = "needs_investigation"
_NEAR_PASS_STAGE_RESULT: Final[str] = "near_pass"


@dataclass(frozen=True)
class FunnelDecision:
    """One funnel-policy decision (pure record).

    ``spawn_request`` is populated for
    ``confirmation_from_exploratory_pass`` and
    ``follow_up_from_near_pass`` so the launcher can append a
    ``survivor_confirmation`` CampaignRecord with funnel metadata
    in ``extra``. All other decision codes carry
    ``spawn_request=None`` — they exist for ledger / digest
    visibility and for upstream policy escalation
    (e.g. cooldown_from_repeat_rejection feeds the existing
    preset cooldown derivation).
    """

    decision_code: str
    candidate_id: str | None
    strategy_id: str | None
    preset_name: str | None
    priority: int
    spawn_request: SpawnRequest | None
    rationale: dict[str, Any] = field(default_factory=dict)


def evidence_owns_campaign(
    evidence: dict[str, Any] | None,
    expected_campaign_id: str | None,
) -> bool:
    """True iff evidence's owner matches ``expected_campaign_id``.

    Mirrors the v3.15.4 paper_readiness ownership pattern from
    ``research.campaign_launcher._check_paper_readiness_outcome``.
    Empty / None evidence or expected id → False.
    """
    if not evidence or expected_campaign_id is None:
        return False
    owner = evidence.get("col_campaign_id") or evidence.get("campaign_id")
    if owner is None:
        return False
    return str(owner) == str(expected_campaign_id)


def _dominant_reason(
    *,
    evidence_summary: dict[str, Any] | None,
    campaign_record: dict[str, Any] | None,
) -> str | None:
    """Source order:
      1) evidence.summary.dominant_failure_reasons[0]
      2) campaign_record.reason_code
      3) campaign_record.extra.dominant_reason
    """
    summary = evidence_summary or {}
    drf = summary.get("dominant_failure_reasons") or []
    if drf:
        return str(drf[0])
    if campaign_record:
        rc = campaign_record.get("reason_code")
        if rc:
            return str(rc)
        extra = campaign_record.get("extra")
        if isinstance(extra, dict):
            v = extra.get("dominant_reason")
            if v:
                return str(v)
    return None


def repeat_rejection_streak(
    *,
    ledger_events: list[dict[str, Any]],
    preset_name: str,
    dominant_reason: str,
) -> int:
    """Walk the tail of ``campaign_completed`` events for ``preset_name``.

    Increment when the event's outcome is ``research_rejection`` AND
    its event-level dominant reason matches ``dominant_reason``.
    The event-level dominant reason is read from
    ``event.reason_code`` first, then ``event.extra.dominant_reason``.

    SKIP (neutral, do not increment, do not break streak):
      - ``technical_failure`` outcomes
      - ``degenerate_no_survivors`` outcomes

    BREAK on any other outcome (completed_with_candidates,
    completed_no_survivor, paper_blocked, integrity_failed, ...).
    """
    if not preset_name or not dominant_reason:
        return 0
    ordered = [
        ev
        for ev in ledger_events
        if ev.get("preset_name") == preset_name
        and ev.get("event_type") == "campaign_completed"
    ]
    ordered.sort(key=lambda ev: str(ev.get("at_utc") or ""))
    streak = 0
    for ev in reversed(ordered):
        outcome = ev.get("outcome")
        if outcome in ("technical_failure", "degenerate_no_survivors"):
            continue
        if outcome != "research_rejection":
            break
        ev_reason = ev.get("reason_code")
        if not ev_reason and isinstance(ev.get("extra"), dict):
            ev_reason = ev["extra"].get("dominant_reason")
        if str(ev_reason or "") != dominant_reason:
            break
        streak += 1
    return streak


def has_alternate_timeframe_support(
    preset_catalog: dict[str, Any] | None,
    preset_name: str | None,
) -> bool:
    """No catalog mechanism today (REV 3 §7.7). Always returns False;
    v3.15.10 falls back to cooldown with rationale
    ``alternate_timeframe_unavailable=True``.
    """
    return False


def has_funnel_spawn_for(
    registry: dict[str, Any] | None,
    *,
    parent_campaign_id: str | None,
    decision_code: str,
    lineage_candidate_id: str | None,
    evidence_fingerprint: str | None,
) -> bool:
    """v3.15.10 dedupe (REV 3 §7.9). Strictly additive; existing
    ``has_child_of_type`` / ``has_followup_for`` semantics intact.

    Match on
        (parent_campaign_id,
         spawn_reason == decision_code,
         extra.lineage_candidate_id,
         extra.screening_evidence_fingerprint).

    Cases:
      - same parent + decision + candidate + fingerprint
        ALREADY present (any state)         -> True (block)
      - same parent + decision + candidate +
        DIFFERENT fingerprint, prior in
        ACTIVE_CAMPAIGN_STATES              -> True (block)
      - same parent + decision + candidate +
        DIFFERENT fingerprint, all prior in
        TERMINAL_CAMPAIGN_STATES            -> False (allowed)
      - different candidate                 -> False (allowed)
      - registry empty / None               -> False (allowed)
    """
    if not registry or not parent_campaign_id or not lineage_candidate_id:
        return False
    campaigns = registry.get("campaigns") or {}
    if not isinstance(campaigns, dict):
        return False

    same_candidate_active_or_match = False
    different_fingerprint_active = False
    for record in campaigns.values():
        if not isinstance(record, dict):
            continue
        if record.get("parent_campaign_id") != parent_campaign_id:
            continue
        if str(record.get("spawn_reason") or "") != decision_code:
            continue
        extra = record.get("extra")
        if not isinstance(extra, dict):
            continue
        if str(extra.get("lineage_candidate_id") or "") != str(lineage_candidate_id):
            continue
        record_fp = str(extra.get("screening_evidence_fingerprint") or "")
        state = str(record.get("state") or "")
        if record_fp == str(evidence_fingerprint or ""):
            # exact-match fingerprint blocks regardless of state
            return True
        # different fingerprint: block iff prior is still in flight
        if state in ACTIVE_CAMPAIGN_STATES:
            different_fingerprint_active = True
        # else (terminal) — allow new fingerprint
    return same_candidate_active_or_match or different_fingerprint_active


def _build_funnel_spawn_request(
    *,
    decision_code: str,
    parent_campaign_id: str,
    parent_lineage_root: str,
    preset_name: str,
    candidate_id: str,
    evidence_fingerprint: str,
    run_id: str,
    request_promotion_grade: bool,
    near_pass_payload: dict[str, Any] | None,
    priority_tier: int,
) -> SpawnRequest:
    """Build a survivor_confirmation SpawnRequest with funnel
    metadata in ``extra``. The spawned campaign runs at the
    parent preset's natural screening_phase; the
    ``requested_screening_phase`` extra field is decision-only
    metadata in v3.15.10 (MF-15) and v3.15.11+ may wire executor
    support.
    """
    extra: dict[str, Any] = {
        "lineage_candidate_id": candidate_id,
        "screening_evidence_fingerprint": evidence_fingerprint,
        "spawned_by_run_id": run_id,
        "funnel_decision_code": decision_code,
    }
    if request_promotion_grade:
        extra["requested_screening_phase"] = "promotion_grade"
    if near_pass_payload:
        extra["near_pass"] = dict(near_pass_payload)
    return SpawnRequest(
        campaign_type="survivor_confirmation",
        preset_name=preset_name,
        template_id=f"survivor_confirmation__{preset_name}",
        parent_campaign_id=parent_campaign_id,
        lineage_root_campaign_id=parent_lineage_root or parent_campaign_id,
        spawn_reason=decision_code,
        subtype=(
            "funnel_confirmation_request"
            if decision_code == FUNNEL_DECISION_CONFIRMATION
            else "funnel_near_pass_followup"
        ),
        priority_tier=int(priority_tier),
        extra=extra,
    )


def _coverage_warning_signals_low(sampling: dict[str, Any]) -> bool:
    warning = sampling.get("coverage_warning")
    policy = sampling.get("sampling_policy")
    return (
        warning == "below_threshold_for_small_grid"
        or warning == "grid_size_unavailable"
        or policy == "grid_size_unavailable"
    )


def derive_funnel_decisions(
    *,
    evidence: dict[str, Any] | None,
    expected_campaign_id: str | None,
    parent_campaign_record: dict[str, Any] | None,
    registry: dict[str, Any] | None,
    ledger_events: list[dict[str, Any]],
    preset_catalog: dict[str, Any] | None,
    technical_failure_record: dict[str, Any] | None = None,
) -> list[FunnelDecision]:
    """Pure entry point. Returns the sorted, deduped list of
    funnel decisions for the current campaign tick.

    Ownership (MF-7 / MF-13): if the evidence does not own
    ``expected_campaign_id``, evidence-derived decisions are
    skipped, but the technical-failure decision (derived from
    ``technical_failure_record`` alone) still fires.
    """
    decisions: list[FunnelDecision] = []
    parent_campaign_id = (
        str(parent_campaign_record.get("campaign_id") or "")
        if parent_campaign_record
        else (str(expected_campaign_id) if expected_campaign_id else "")
    )
    parent_lineage_root = (
        str(parent_campaign_record.get("lineage_root_campaign_id") or "")
        if parent_campaign_record
        else ""
    )
    preset_name = (
        str(parent_campaign_record.get("preset_name") or "")
        if parent_campaign_record
        else (
            str(evidence.get("preset_name") or "")
            if evidence
            else ""
        )
    )
    evidence_summary = (evidence or {}).get("summary") or {}
    run_id = str((evidence or {}).get("run_id") or "")

    evidence_owned = evidence_owns_campaign(evidence, expected_campaign_id)

    # ---- Technical-failure decision (independent of evidence) ----
    if (
        technical_failure_record is not None
        and str(technical_failure_record.get("outcome") or "") == "technical_failure"
    ):
        tf_preset = (
            str(technical_failure_record.get("preset_name") or "")
            or preset_name
        )
        decisions.append(
            FunnelDecision(
                decision_code=FUNNEL_DECISION_NO_ACTION_TECHNICAL,
                candidate_id=None,
                strategy_id=None,
                preset_name=tf_preset,
                priority=DECISION_PRIORITY[FUNNEL_DECISION_NO_ACTION_TECHNICAL],
                spawn_request=None,
                rationale={
                    "campaign_id": str(
                        technical_failure_record.get("campaign_id") or ""
                    ),
                    "research_freeze_blocked": True,
                },
            )
        )

    # ---- Per-candidate decisions (require evidence ownership) ----
    if not evidence_owned or not evidence:
        return sort_funnel_decisions(decisions)

    for record in evidence.get("candidates") or []:
        if not isinstance(record, dict):
            continue
        candidate_id = str(record.get("candidate_id") or "")
        strategy_id = str(record.get("strategy_id") or "")
        evidence_fp = str(record.get("evidence_fingerprint") or "")
        sampling = record.get("sampling") or {}
        stage_result = str(record.get("stage_result") or "")
        failure_reasons = list(record.get("failure_reasons") or [])
        near_pass_block = record.get("near_pass") or {}

        # 1) Confirmation from exploratory pass
        if stage_result == _EXPLORATORY_PASS_STAGE_RESULT:
            spawn = _build_funnel_spawn_request(
                decision_code=FUNNEL_DECISION_CONFIRMATION,
                parent_campaign_id=parent_campaign_id,
                parent_lineage_root=parent_lineage_root,
                preset_name=preset_name,
                candidate_id=candidate_id,
                evidence_fingerprint=evidence_fp,
                run_id=run_id,
                request_promotion_grade=True,
                near_pass_payload=None,
                priority_tier=1,
            )
            decisions.append(
                FunnelDecision(
                    decision_code=FUNNEL_DECISION_CONFIRMATION,
                    candidate_id=candidate_id,
                    strategy_id=strategy_id,
                    preset_name=preset_name,
                    priority=DECISION_PRIORITY[FUNNEL_DECISION_CONFIRMATION],
                    spawn_request=spawn,
                    rationale={"pass_kind": record.get("pass_kind")},
                )
            )
            continue  # exploratory pass overrides other per-candidate paths

        # 2) Near-pass follow-up
        if stage_result == _NEAR_PASS_STAGE_RESULT and near_pass_block.get("is_near_pass"):
            spawn = _build_funnel_spawn_request(
                decision_code=FUNNEL_DECISION_NEAR_PASS_FOLLOWUP,
                parent_campaign_id=parent_campaign_id,
                parent_lineage_root=parent_lineage_root,
                preset_name=preset_name,
                candidate_id=candidate_id,
                evidence_fingerprint=evidence_fp,
                run_id=run_id,
                request_promotion_grade=False,
                near_pass_payload={
                    "nearest_failed_criterion": near_pass_block.get(
                        "nearest_failed_criterion"
                    ),
                    "distance": near_pass_block.get("distance"),
                },
                priority_tier=2,
            )
            decisions.append(
                FunnelDecision(
                    decision_code=FUNNEL_DECISION_NEAR_PASS_FOLLOWUP,
                    candidate_id=candidate_id,
                    strategy_id=strategy_id,
                    preset_name=preset_name,
                    priority=DECISION_PRIORITY[FUNNEL_DECISION_NEAR_PASS_FOLLOWUP],
                    spawn_request=spawn,
                    rationale={
                        "nearest_failed_criterion": near_pass_block.get(
                            "nearest_failed_criterion"
                        ),
                        "distance": near_pass_block.get("distance"),
                    },
                )
            )
            continue

        # 3) Insufficient trades — alt-timeframe never supported today
        if (
            len(failure_reasons) == 1
            and failure_reasons[0] == "insufficient_trades"
        ):
            if has_alternate_timeframe_support(preset_catalog, preset_name):
                # Reserved for v3.15.11+; never reached today.
                pass  # pragma: no cover
            else:
                decisions.append(
                    FunnelDecision(
                        decision_code=FUNNEL_DECISION_COOLDOWN_REPEAT,
                        candidate_id=candidate_id,
                        strategy_id=strategy_id,
                        preset_name=preset_name,
                        priority=DECISION_PRIORITY[FUNNEL_DECISION_COOLDOWN_REPEAT],
                        spawn_request=None,
                        rationale={
                            "alternate_timeframe_unavailable": True,
                            "dominant_reason": "insufficient_trades",
                        },
                    )
                )
                continue

        # 4) Low coverage signal (sampling defect; no spawn)
        if _coverage_warning_signals_low(sampling):
            decisions.append(
                FunnelDecision(
                    decision_code=FUNNEL_DECISION_COVERAGE_FOLLOWUP,
                    candidate_id=candidate_id,
                    strategy_id=strategy_id,
                    preset_name=preset_name,
                    priority=DECISION_PRIORITY[FUNNEL_DECISION_COVERAGE_FOLLOWUP],
                    spawn_request=None,
                    rationale={
                        "sampling_defect_review_required": True,
                        "grid_size": sampling.get("grid_size"),
                        "coverage_pct": sampling.get("coverage_pct"),
                        "coverage_warning": sampling.get("coverage_warning"),
                        "grid_size_unavailable": (
                            sampling.get("sampling_policy")
                            == "grid_size_unavailable"
                            or sampling.get("coverage_warning")
                            == "grid_size_unavailable"
                        ),
                    },
                )
            )
            continue

    # ---- Repeat-rejection cooldown (preset-level, after per-candidate loop) ----
    dom_reason = _dominant_reason(
        evidence_summary=evidence_summary,
        campaign_record=parent_campaign_record,
    )
    if preset_name and dom_reason:
        streak = repeat_rejection_streak(
            ledger_events=ledger_events,
            preset_name=preset_name,
            dominant_reason=dom_reason,
        )
        if streak >= REPEAT_REJECTION_STREAK_THRESHOLD:
            decisions.append(
                FunnelDecision(
                    decision_code=FUNNEL_DECISION_COOLDOWN_REPEAT,
                    candidate_id=None,
                    strategy_id=None,
                    preset_name=preset_name,
                    priority=DECISION_PRIORITY[FUNNEL_DECISION_COOLDOWN_REPEAT],
                    spawn_request=None,
                    rationale={
                        "streak": streak,
                        "dominant_reason": dom_reason,
                    },
                )
            )

    return sort_funnel_decisions(decisions)


def sort_funnel_decisions(
    decisions: list[FunnelDecision],
) -> list[FunnelDecision]:
    """Stable sort by (priority, decision_code, preset_name,
    strategy_id, candidate_id) so the launcher applies decisions
    in a fully deterministic order independent of evidence input
    ordering.
    """
    return sorted(
        decisions,
        key=lambda d: (
            int(d.priority),
            str(d.decision_code),
            str(d.preset_name or ""),
            str(d.strategy_id or ""),
            str(d.candidate_id or ""),
        ),
    )


__all__ = [
    "ACTIVE_CAMPAIGN_STATES",
    "DECISION_PRIORITY",
    "FUNNEL_DECISION_ALT_TIMEFRAME",
    "FUNNEL_DECISION_CONFIRMATION",
    "FUNNEL_DECISION_COOLDOWN_REPEAT",
    "FUNNEL_DECISION_COVERAGE_FOLLOWUP",
    "FUNNEL_DECISION_NEAR_PASS_FOLLOWUP",
    "FUNNEL_DECISION_NO_ACTION_TECHNICAL",
    "FunnelDecision",
    "LOW_COVERAGE_TRIGGER_PCT",
    "REPEAT_REJECTION_STREAK_THRESHOLD",
    "TERMINAL_CAMPAIGN_STATES",
    "derive_funnel_decisions",
    "evidence_owns_campaign",
    "has_alternate_timeframe_support",
    "has_funnel_spawn_for",
    "repeat_rejection_streak",
    "sort_funnel_decisions",
]
