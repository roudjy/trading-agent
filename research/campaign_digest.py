"""Daily operations digest for the v3.15.2 Campaign OS.

Pure roll-up: reads registry + ledger + budget and emits
``research/campaign_digest_latest.v1.json``. No new trading-performance
metrics — strictly operations:

- campaigns by type
- meaningful classifications
- compute per meaningful / per candidate / per paper-worthy candidate
- queue efficiency, worker utilisation
- top failure reasons
- frozen / thawed presets

Also surfaces the lineage- and family-level cost attribution added in
R3.3.6.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic
from research.campaign_budget import BudgetState
from research.campaign_os_artifacts import build_pin_block
from research.campaign_preset_policy import PresetPolicyState

DIGEST_SCHEMA_VERSION: str = "1.1"
DIGEST_ARTIFACT_PATH: Path = Path(
    "research/campaign_digest_latest.v1.json"
)


def _aggregate_funnel_decisions(
    events: list[dict[str, Any]],
) -> dict[str, int]:
    """v3.15.10 — count ``funnel_decision_emitted`` events for the
    digest window by ``extra.decision_code``. Returns a dict
    sorted alphabetically by decision_code so the digest payload
    is deterministic across runs.
    """
    counts: dict[str, int] = {}
    for ev in events:
        if ev.get("event_type") != "funnel_decision_emitted":
            continue
        extra = ev.get("extra")
        if not isinstance(extra, dict):
            continue
        code = extra.get("decision_code")
        if not code:
            continue
        counts[str(code)] = counts.get(str(code), 0) + 1
    return dict(sorted(counts.items()))


def _parse_utc(ts: str | None) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _is_today(ts: datetime | None, today: str) -> bool:
    if ts is None:
        return False
    return ts.date().isoformat() == today


@dataclass(frozen=True)
class DigestInputs:
    registry: dict[str, Any]
    events: list[dict[str, Any]]
    budget: BudgetState
    preset_states: dict[str, PresetPolicyState]
    previous_digest: dict[str, Any] | None
    max_concurrent_campaigns: int


def _build_campaigns_by_type(
    records_today: list[dict[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for r in records_today:
        counts[str(r.get("campaign_type") or "")] += 1
    for campaign_type in (
        "daily_primary",
        "daily_control",
        "survivor_confirmation",
        "paper_followup",
        "weekly_retest",
    ):
        counts.setdefault(campaign_type, 0)
    return dict(counts)


def _build_meaningful_by_classification(
    records_today: list[dict[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for r in records_today:
        if r.get("state") not in ("completed", "failed", "canceled"):
            continue
        key = str(r.get("meaningful_classification") or "too_early_to_classify")
        counts[key] += 1
    for key in (
        "meaningful_candidate_found",
        "meaningful_family_falsified",
        "meaningful_failure_confirmed",
        "uninformative_technical_failure",
        "duplicate_low_value_run",
        "too_early_to_classify",
    ):
        counts.setdefault(key, 0)
    return dict(counts)


def _top_failure_reasons(
    events_today: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    codes: Counter[str] = Counter()
    failure_types = {
        "campaign_failed",
        "paper_blocked",
        "reject_no_survivor",
    }
    for ev in events_today:
        if ev.get("event_type") not in failure_types:
            continue
        codes[str(ev.get("reason_code") or "none")] += 1
    return [
        {"reason_code": code, "count": int(count)}
        for code, count in codes.most_common(limit)
    ]


def _compute_by_lineage_root(
    records_today: list[dict[str, Any]],
) -> dict[str, Any]:
    by_root: dict[str, dict[str, Any]] = {}
    for r in records_today:
        root = str(r.get("lineage_root_campaign_id") or r.get("campaign_id") or "")
        if not root:
            continue
        bucket = by_root.setdefault(
            root,
            {
                "children_count": 0,
                "actual_compute_seconds": 0,
                "meaningful_classifications": [],
            },
        )
        bucket["children_count"] = int(bucket["children_count"]) + 1
        bucket["actual_compute_seconds"] = int(bucket["actual_compute_seconds"]) + int(
            r.get("actual_runtime_seconds") or 0
        )
        meaningful = r.get("meaningful_classification")
        if meaningful:
            bucket["meaningful_classifications"].append(str(meaningful))
    # Deterministic ordering of keys.
    return {root: by_root[root] for root in sorted(by_root)}


def _compute_by_candidate_family(
    records_today: list[dict[str, Any]],
) -> dict[str, Any]:
    by_family: dict[str, dict[str, Any]] = {}
    for r in records_today:
        family = r.get("strategy_family")
        asset = r.get("asset_class")
        if not family or not asset:
            continue
        key = f"{family}|{asset}"
        bucket = by_family.setdefault(
            key,
            {
                "campaigns_today": 0,
                "actual_compute_seconds": 0,
                "candidates_produced": 0,
                "paper_worthy_candidates": 0,
            },
        )
        bucket["campaigns_today"] = int(bucket["campaigns_today"]) + 1
        bucket["actual_compute_seconds"] = int(bucket["actual_compute_seconds"]) + int(
            r.get("actual_runtime_seconds") or 0
        )
        candidates = int(
            r.get("extra", {}).get("candidates_produced", 0)
            if isinstance(r.get("extra"), dict)
            else 0
        )
        paper_worthy = int(
            r.get("extra", {}).get("paper_worthy_candidates", 0)
            if isinstance(r.get("extra"), dict)
            else 0
        )
        bucket["candidates_produced"] = int(bucket["candidates_produced"]) + candidates
        bucket["paper_worthy_candidates"] = int(bucket["paper_worthy_candidates"]) + paper_worthy
    for bucket in by_family.values():
        pwc = max(1, int(bucket["paper_worthy_candidates"]))
        bucket["compute_per_paper_worthy_candidate"] = float(
            bucket["actual_compute_seconds"]
        ) / pwc
    return {key: by_family[key] for key in sorted(by_family)}


def build_digest_payload(
    inputs: DigestInputs,
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
) -> dict[str, Any]:
    today = generated_at_utc.astimezone(UTC).date().isoformat()
    campaigns = list((inputs.registry.get("campaigns") or {}).values())
    records_today = [
        r
        for r in campaigns
        if _is_today(_parse_utc(r.get("spawned_at_utc")), today)
    ]
    events_today = [
        ev
        for ev in inputs.events
        if _is_today(_parse_utc(ev.get("at_utc")), today)
    ]
    campaigns_scheduled = len(records_today)
    campaigns_completed = sum(
        1 for r in records_today if r.get("state") == "completed"
    )
    campaigns_failed = sum(
        1 for r in records_today if r.get("state") == "failed"
    )
    campaigns_canceled = sum(
        1 for r in records_today if r.get("state") == "canceled"
    )
    meaningful_by = _build_meaningful_by_classification(records_today)
    meaningful_total = sum(
        meaningful_by[k]
        for k in (
            "meaningful_candidate_found",
            "meaningful_family_falsified",
            "meaningful_failure_confirmed",
        )
    )
    candidates_produced = sum(
        int(
            (r.get("extra") or {}).get("candidates_produced", 0)
            if isinstance(r.get("extra"), dict)
            else 0
        )
        for r in records_today
    )
    paper_worthy = sum(
        int(
            (r.get("extra") or {}).get("paper_worthy_candidates", 0)
            if isinstance(r.get("extra"), dict)
            else 0
        )
        for r in records_today
    )
    estimated = sum(
        int(r.get("estimated_runtime_seconds") or 0) for r in records_today
    )
    actual = sum(
        int(r.get("actual_runtime_seconds") or 0) for r in records_today
    )
    worker_capacity_seconds = 86_400 * max(1, int(inputs.max_concurrent_campaigns))
    utilisation_pct = round(100.0 * actual / worker_capacity_seconds, 2) if worker_capacity_seconds else 0.0

    frozen_now = {
        name: state.policy_state
        for name, state in inputs.preset_states.items()
    }
    prev = inputs.previous_digest or {}
    prev_states = dict(prev.get("preset_states") or {})
    newly_frozen = sorted(
        name
        for name, s in frozen_now.items()
        if s == "frozen" and prev_states.get(name) != "frozen"
    )
    thawed = sorted(
        name
        for name in prev_states
        if prev_states[name] == "frozen" and frozen_now.get(name) != "frozen"
    )

    pins = build_pin_block(
        schema_version=DIGEST_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )

    queue_efficiency_pct = (
        round(100.0 * meaningful_total / max(1, campaigns_completed), 2)
        if campaigns_completed
        else 0.0
    )

    return {
        **pins,
        "date": today,
        "campaigns_scheduled": campaigns_scheduled,
        "campaigns_completed": campaigns_completed,
        "campaigns_failed": campaigns_failed,
        "campaigns_canceled": campaigns_canceled,
        "campaigns_frozen": sum(1 for s in frozen_now.values() if s == "frozen"),
        "campaigns_by_type": _build_campaigns_by_type(records_today),
        "meaningful_by_classification": meaningful_by,
        "meaningful_campaigns_total": int(meaningful_total),
        "candidates_produced_today": int(candidates_produced),
        "paper_worthy_candidates_today": int(paper_worthy),
        "estimated_compute_seconds_used": int(estimated),
        "actual_compute_seconds_used": int(actual),
        "compute_seconds_per_meaningful_campaign": (
            round(actual / max(1, meaningful_total), 2)
            if meaningful_total
            else 0.0
        ),
        "compute_seconds_per_candidate": (
            round(actual / max(1, candidates_produced), 2)
            if candidates_produced
            else 0.0
        ),
        "compute_seconds_per_paper_worthy_candidate": (
            round(actual / max(1, paper_worthy), 2) if paper_worthy else 0.0
        ),
        "queue_depth": sum(
            1 for r in campaigns if r.get("state") in ("pending", "leased", "running")
        ),
        "queue_efficiency_pct": queue_efficiency_pct,
        "worker_utilization_pct": utilisation_pct,
        "top_failure_reasons": _top_failure_reasons(events_today),
        "preset_states": {name: frozen_now[name] for name in sorted(frozen_now)},
        "newly_frozen_presets": newly_frozen,
        "thawed_presets": thawed,
        "compute_by_lineage_root": _compute_by_lineage_root(records_today),
        "compute_by_candidate_family": _compute_by_candidate_family(records_today),
        "policy_decisions_count": sum(
            1
            for ev in events_today
            if ev.get("event_type")
            in (
                "campaign_spawned",
                "canceled_duplicate",
                "canceled_upstream_stale",
                "lease_expired",
            )
        ),
        "idle_noop_count": 0,  # maintained by the launcher in ``extra``
        "skip_budget_count": 0,
        # v3.15.10 (additive; schema 1.0 -> 1.1) — funnel decisions
        # roll-up for the day. Empty {} when no funnel events
        # present, so v1.0 readers (launcher.load_previous_digest
        # uses .get(...); dashboard/api_campaigns serves the dict
        # as-is) continue to work.
        "funnel_decisions": _aggregate_funnel_decisions(events_today),
    }


def load_previous_digest(
    path: Path = DIGEST_ARTIFACT_PATH,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_digest(
    payload: dict[str, Any],
    *,
    path: Path = DIGEST_ARTIFACT_PATH,
) -> None:
    write_sidecar_atomic(path, payload)


__all__ = [
    "DIGEST_ARTIFACT_PATH",
    "DIGEST_SCHEMA_VERSION",
    "DigestInputs",
    "build_digest_payload",
    "load_previous_digest",
    "write_digest",
]
