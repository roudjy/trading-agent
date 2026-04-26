"""Campaign launcher — single-tick CLI for the v3.15.2 Campaign OS.

This module is the only code path that performs side effects. It:

1. Loads all artifacts under the queue lock (registry / queue / ledger /
   budget / templates / preset+family policy states).
2. Asserts invariants; if violated, rebuilds the queue from the registry
   and re-asserts (recovery attempt).
3. Builds follow-up and weekly-control candidate specs.
4. Calls ``campaign_policy.decide(...)``.
5. Applies the decision as a single critical-section mutation and
   appends ledger events.
6. On ``spawn`` action: invokes ``python -m research.run_research
   --preset NAME --campaign-id CID`` as a subprocess, observes the run
   artifacts, and records the outcome.
7. Writes the daily digest.

Entrypoint: ``python -m research.campaign_launcher``. Usually fired
hourly by the systemd timer that previously invoked ``run_research.py``
directly.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - required to invoke research.run_research as a subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.campaign_lease import (
    Lease,
    acquire_queue_lock,
    build_lease,
    build_worker_id,
)
from research._sidecar_io import write_sidecar_atomic
from research.campaign_budget import (
    add_reservation,
    estimate_runtime_seconds,
    load_budget,
    settle_reservation,
    write_budget,
)
from research.campaign_digest import (
    DigestInputs,
    build_digest_payload,
    load_previous_digest,
    write_digest,
)
from research.campaign_evidence_ledger import (
    REASON_CODE_NONE,
    append_events,
    load_events,
    make_event,
    write_meta,
)
from research.campaign_family_policy import (
    derive_family_states,
    write_family_policy,
)
from research.campaign_invariants import (
    CampaignInvariantViolation,
    assert_invariants,
)
from research.campaign_os_artifacts import iso_utc
from research.campaign_policy import (
    CandidateSpec,
    decide,
    write_decision,
)
from research.campaign_preset_policy import (
    derive_preset_states,
    write_preset_policy,
)
from research.campaign_queue import (
    clear_lease,
    load_queue,
    rebuild_queue_from_registry,
    set_lease,
    upsert_entry,
    write_queue,
)
from research.campaign_registry import (
    LAUNCHER_EMITTABLE_OUTCOMES,
    REGISTRY_ARTIFACT_PATH,
    CampaignRecord,
    build_campaign_id,
    fingerprint_inputs,
    get_record,
    load_registry,
    record_outcome,
    transition_state,
    upsert_record,
    write_registry,
)
from research.empty_run_reporting import EXIT_CODE_DEGENERATE_NO_SURVIVORS
from research.rejection_taxonomy import SCREENING_REASON_CODES
from research.campaign_followup import (
    derive_followups,
    derive_weekly_controls,
)
from research.campaign_templates import (
    CAMPAIGN_TEMPLATES,
    DEFAULT_CONFIG,
    build_templates_payload,
    get_template,
)
from research.campaign_queue import queue_entry_from_record

EVIDENCE_LEDGER_PATH: Path = Path(
    "research/campaign_evidence_ledger_latest.v1.jsonl"
)
EVIDENCE_META_PATH: Path = Path(
    "research/campaign_evidence_ledger_latest.v1.meta.json"
)
TEMPLATES_ARTIFACT_PATH: Path = Path(
    "research/campaign_templates_latest.v1.json"
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _short_git_revision() -> str | None:
    try:
        # Fixed argv, no user input; git is a trusted dev tool.
        result = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            shell=False,
        )
        rev = result.stdout.strip()
        return rev or None
    except Exception:  # pragma: no cover - defensive, git may be absent
        return None


def _load_upstream_states() -> dict[str, str]:
    """Read upstream ``public_artifact_status`` for the stale check."""
    path = Path("research/public_artifact_status_latest.v1.json")
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    state = "stale" if raw.get("public_artifacts_stale") else "healthy"
    return {"public_artifact_status": state}


def _ensure_templates_artifact(now_utc: datetime, git_rev: str | None) -> None:
    if TEMPLATES_ARTIFACT_PATH.exists():
        return
    payload = build_templates_payload(
        generated_at_utc=now_utc,
        git_revision=git_rev,
    )
    write_sidecar_atomic(TEMPLATES_ARTIFACT_PATH, payload)


def _cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="research.campaign_launcher",
        description="Single-tick autonomous campaign launcher (v3.15.2 COL).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute a decision but do not mutate state or spawn subprocess.",
    )
    parser.add_argument(
        "--no-subprocess",
        action="store_true",
        help="Emit the decision and mutate state, but skip the subprocess call.",
    )
    return parser.parse_args()


def _build_record(
    *,
    campaign_id: str,
    template_id: str,
    preset_name: str,
    campaign_type: str,
    priority_tier: int,
    spawned_at_utc: str,
    spawn_reason: str,
    parent_campaign_id: str | None,
    lineage_root_campaign_id: str,
    input_artifact_fingerprint: str,
    estimate_seconds: int,
    subtype: str | None,
) -> CampaignRecord:
    return CampaignRecord(
        campaign_id=campaign_id,
        template_id=template_id,
        preset_name=preset_name,
        campaign_type=campaign_type,  # type: ignore[arg-type]
        state="pending",
        priority_tier=int(priority_tier),
        spawned_at_utc=spawned_at_utc,
        spawn_reason=spawn_reason,
        parent_campaign_id=parent_campaign_id,
        lineage_root_campaign_id=lineage_root_campaign_id or campaign_id,
        input_artifact_fingerprint=input_artifact_fingerprint,
        estimated_runtime_seconds=int(estimate_seconds),
        subtype=subtype,
    )


def _build_followup_specs(
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    preset_states: dict[str, Any],
    now_utc: datetime,
) -> tuple[CandidateSpec, ...]:
    specs: list[CandidateSpec] = []
    idx_counter = 0
    campaigns = list((registry.get("campaigns") or {}).values())
    campaigns.sort(key=lambda r: str(r.get("spawned_at_utc") or ""))
    for parent in campaigns:
        if parent.get("state") != "completed":
            continue
        preset_name = str(parent.get("preset_name") or "")
        preset_state = preset_states.get(preset_name)
        weekly_cap = (
            int(preset_state.paper_followup_weekly_cap)
            if preset_state is not None
            else 2
        )
        paper_reason = (
            parent.get("reason_code")
            if parent.get("outcome") == "paper_blocked"
            else None
        )
        requests = derive_followups(
            parent_record=parent,
            registry=registry,
            events=events,
            paper_blocked_reason=paper_reason,
            paper_followup_weekly_cap=weekly_cap,
            now_utc=now_utc,
        )
        for req in requests:
            try:
                template = get_template(req.template_id)
            except KeyError:
                continue
            estimate = estimate_runtime_seconds(
                events,
                preset_name=template.preset_name,
                campaign_type=template.campaign_type,
                fallback_seconds=template.estimated_runtime_seconds_default,
            )
            specs.append(
                CandidateSpec(
                    template=template,
                    appended_in_phase="A",
                    appended_index=idx_counter,
                    preset_name=req.preset_name,
                    campaign_type=req.campaign_type,
                    parent_campaign_id=req.parent_campaign_id,
                    lineage_root_campaign_id=req.lineage_root_campaign_id,
                    spawn_reason=req.spawn_reason,
                    subtype=req.subtype,
                    input_artifact_fingerprint="",
                    estimate_seconds=estimate,
                    effective_priority_tier=int(req.priority_tier),
                )
            )
            idx_counter += 1
    return tuple(specs)


def _build_weekly_control_specs(
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    now_utc: datetime,
    templates: tuple,
) -> tuple[CandidateSpec, ...]:
    preset_names = sorted({t.preset_name for t in templates if t.campaign_type == "daily_control"})
    requests = derive_weekly_controls(
        preset_names=preset_names,
        registry=registry,
        events=events,
        now_utc=now_utc,
    )
    specs: list[CandidateSpec] = []
    for idx, req in enumerate(requests):
        try:
            template = get_template(req.template_id)
        except KeyError:
            continue
        estimate = estimate_runtime_seconds(
            events,
            preset_name=template.preset_name,
            campaign_type=template.campaign_type,
            fallback_seconds=template.estimated_runtime_seconds_default,
        )
        specs.append(
            CandidateSpec(
                template=template,
                appended_in_phase="C",
                appended_index=idx,
                preset_name=req.preset_name,
                campaign_type=req.campaign_type,
                parent_campaign_id=None,
                lineage_root_campaign_id="",
                spawn_reason=req.spawn_reason,
                subtype=req.subtype,
                input_artifact_fingerprint="",
                estimate_seconds=estimate,
                effective_priority_tier=3,
            )
        )
    return tuple(specs)


def _write_ledger(
    events: list,
    *,
    now_utc: datetime,
    git_rev: str | None,
) -> None:
    append_events(EVIDENCE_LEDGER_PATH, events)
    write_meta(
        EVIDENCE_META_PATH,
        generated_at_utc=now_utc,
        git_revision=git_rev,
        event_count=len(load_events(EVIDENCE_LEDGER_PATH)),
        ledger_path=str(EVIDENCE_LEDGER_PATH.as_posix()),
    )


def _record_digest(
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    budget,
    preset_states,
    now_utc: datetime,
    git_rev: str | None,
) -> None:
    previous = load_previous_digest()
    payload = build_digest_payload(
        DigestInputs(
            registry=registry,
            events=events,
            budget=budget,
            preset_states=preset_states,
            previous_digest=previous,
            max_concurrent_campaigns=int(DEFAULT_CONFIG.max_concurrent_campaigns),
        ),
        generated_at_utc=now_utc,
        git_revision=git_rev,
    )
    write_digest(payload)


def _classify_outcome_from_paper(
    paper_readiness_path: Path,
    *,
    expected_campaign_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Return (outcome, blocking_reason) based on paper readiness artifact.

    v3.15.4 ownership check: when ``expected_campaign_id`` is given the
    sidecar's ``col_campaign_id`` field MUST equal it. A missing or
    mismatched stamp means the file is either pre-v3.15.4 or belongs
    to a previous campaign whose subprocess crashed before overwriting
    it; the function returns ``(None, None)`` in that case so the
    caller falls back to the conservative ``completed_no_survivor``
    classification rather than crediting / blaming the current run for
    another campaign's verdict.
    """
    if not paper_readiness_path.exists():
        return None, None
    try:
        raw = json.loads(paper_readiness_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if expected_campaign_id is not None:
        owner = raw.get("col_campaign_id")
        if owner is None or str(owner) != str(expected_campaign_id):
            return None, None
    status = raw.get("status")
    if status == "ready_for_paper_promotion":
        return "completed_with_candidates", None
    if status == "blocked":
        reasons = raw.get("blocking_reasons") or []
        first = str(reasons[0]) if reasons else "unknown"
        return "paper_blocked", first
    return None, None


# v3.15.5 — outcome dispatch helpers ------------------------------------------

EMPTY_RUN_DIAGNOSTICS_PATH: Path = Path(
    "research/empty_run_diagnostics_latest.v1.json"
)
CANDIDATE_REGISTRY_V1_PATH: Path = Path(
    "research/candidate_registry_latest.v1.json"
)


def _classify_research_rejection(
    paper_readiness_path: Path,
    candidate_registry_path: Path,
    *,
    expected_campaign_id: str,
) -> tuple[str | None, str | None]:
    """Return ``("research_rejection", reason_code)`` or ``(None, None)``.

    Hard-ownership rule (v3.15.5): we only credit / blame this run for
    the candidate registry if ``paper_readiness_latest.v1.json``'s
    ``col_campaign_id`` matches ``expected_campaign_id``. Paper readiness
    is written by ``run_research`` in the same subprocess that writes
    ``candidate_registry_latest.v1.json``; an ownership match on paper
    readiness anchors the registry's identity by producer atomicity.
    Mtime is **not** used as ownership.

    Returns ``(None, None)`` whenever any of the strict conditions
    fails. The caller falls back to ``completed_no_survivor``.
    """
    # Hard ownership via paper_readiness col_campaign_id stamp.
    if not paper_readiness_path.exists():
        return None, None
    try:
        paper_raw = json.loads(paper_readiness_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    owner = paper_raw.get("col_campaign_id")
    if owner is None or str(owner) != str(expected_campaign_id):
        return None, None
    status = paper_raw.get("status")
    # Stages A and B already classify these — research_rejection only
    # fires when paper readiness did NOT classify the run.
    if status in ("ready_for_paper_promotion", "blocked"):
        return None, None
    # Now inspect the v1 candidate registry. The frozen v1 schema has no
    # run_id field, but ownership is anchored above via paper_readiness.
    if not candidate_registry_path.exists():
        return None, None
    try:
        registry_raw = json.loads(
            candidate_registry_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None, None
    candidates = registry_raw.get("candidates")
    if not isinstance(candidates, list) or len(candidates) == 0:
        return None, None
    if not all(
        isinstance(c, dict) and c.get("status") == "rejected" for c in candidates
    ):
        return None, None
    # Aggregate failed reason codes across candidates.
    failed_union: list[str] = []
    for entry in candidates:
        reasoning = entry.get("reasoning") or {}
        failed = reasoning.get("failed") or []
        for code in failed:
            failed_union.append(str(code))
    if not failed_union:
        return None, None
    failed_set = set(failed_union)
    if not failed_set.issubset(SCREENING_REASON_CODES):
        return None, None
    # Pick the dominant code; tiebreak alphabetically for determinism.
    counts: dict[str, int] = {}
    for code in failed_union:
        counts[code] = counts.get(code, 0) + 1
    dominant = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return "research_rejection", dominant


def _technical_failure_reason_code(rc: int) -> str:
    """Map a non-zero, non-degenerate ``rc`` to a closed reason code.

    Only reuses codes already accepted by ``_TECHNICAL_REASON_CODES``
    in ``campaign_preset_policy``. ``timeout`` is in that set already
    (v3.15.2), so rc=124 is allowed to use it. Other non-zero codes
    fall back to the conservative ``worker_crash`` so policy
    semantics stay byte-identical to pre-v3.15.5 for this branch.
    """
    if rc == 124:
        return "timeout"
    return "worker_crash"


def _check_rc2_origin(
    diagnostics_path: Path,
    *,
    expected_campaign_id: str,
) -> str:
    """Diagnostic-only origin check for ``rc == 2``.

    Returns one of ``"rc2_origin_confirmed_degenerate"``,
    ``"rc2_unexpected_origin"``, ``"rc2_payload_malformed"``. Outcome
    classification is **not** affected by this check; rc=2 is itself
    a producer-restricted signal (only ``run_research.py``'s ``__main__``
    wrapper emits it). The status string is logged to stderr by the
    caller for forensic visibility.
    """
    if not diagnostics_path.exists():
        return "rc2_unexpected_origin"
    try:
        raw = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "rc2_payload_malformed"
    if not isinstance(raw, dict):
        return "rc2_payload_malformed"
    if "failure_stage" not in raw or "summary" not in raw:
        return "rc2_payload_malformed"
    # Optional ownership cross-check (does not gate outcome).
    owner = raw.get("col_campaign_id")
    if owner is not None and str(owner) != str(expected_campaign_id):
        return "rc2_unexpected_origin"
    return "rc2_origin_confirmed_degenerate"


def _invoke_subprocess(
    *,
    preset_name: str,
    campaign_id: str,
    lease_ttl_seconds: int,
) -> tuple[int, int]:
    """Call ``run_research.py --preset --campaign-id``. Returns (exit, elapsed)."""
    args = [
        sys.executable,
        "-m",
        "research.run_research",
        "--preset",
        preset_name,
        "--campaign-id",
        campaign_id,
    ]
    start = datetime.now(UTC)
    try:
        # sys.executable + hardcoded -m invocation; preset_name and
        # campaign_id are validated upstream via the closed preset catalog
        # and policy engine. shell=False forbids shell interpolation.
        completed = subprocess.run(  # nosec B603
            args,
            timeout=max(60, lease_ttl_seconds - 300),
            check=False,
            shell=False,
        )
        elapsed = int((datetime.now(UTC) - start).total_seconds())
        return int(completed.returncode), elapsed
    except subprocess.TimeoutExpired:
        elapsed = int((datetime.now(UTC) - start).total_seconds())
        return 124, elapsed


def main() -> int:
    args = _cli_args()
    now_utc = _now_utc()
    git_rev = _short_git_revision()
    _ensure_templates_artifact(now_utc, git_rev)
    templates = CAMPAIGN_TEMPLATES
    config = DEFAULT_CONFIG

    try:
        with acquire_queue_lock():
            return _tick(
                now_utc=now_utc,
                git_rev=git_rev,
                templates=templates,
                config=config,
                dry_run=args.dry_run,
                skip_subprocess=args.no_subprocess,
            )
    except CampaignInvariantViolation as exc:
        sys.stderr.write(f"campaign invariant violation: {exc}\n")
        return 2


def _tick(
    *,
    now_utc: datetime,
    git_rev: str | None,
    templates: tuple,
    config,
    dry_run: bool,
    skip_subprocess: bool,
) -> int:
    registry = load_registry()
    queue = load_queue()
    events = load_events(EVIDENCE_LEDGER_PATH)
    budget = load_budget(
        now_utc=now_utc,
        daily_compute_budget_seconds=config.daily_compute_budget_seconds,
        reserved_for_followups_seconds=config.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=config.max_low_value_reruns_per_day,
        tier1_fairness_cap=config.tier1_fairness_cap,
    )
    upstream = _load_upstream_states()

    # Rebuild queue view from registry if invariants disagree.
    try:
        assert_invariants(
            registry=registry,
            queue=queue,
            events=events,
            max_concurrent_campaigns=config.max_concurrent_campaigns,
        )
    except CampaignInvariantViolation:
        queue = rebuild_queue_from_registry(registry)
        assert_invariants(
            registry=registry,
            queue=queue,
            events=events,
            max_concurrent_campaigns=config.max_concurrent_campaigns,
        )

    # Derive preset + family policy state from the ledger.
    template_cooldown_by_preset = {
        t.preset_name: t.cooldown_seconds
        for t in templates
        if t.campaign_type == "daily_primary"
    }
    preset_names = sorted({t.preset_name for t in templates})
    preset_states = derive_preset_states(
        events,
        preset_names=preset_names,
        template_cooldown_seconds_by_preset=template_cooldown_by_preset,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    # Family state: enumerate known families from registry records.
    families: list[tuple[str, str]] = []
    for record in (registry.get("campaigns") or {}).values():
        family = record.get("strategy_family")
        asset = record.get("asset_class")
        if family and asset:
            families.append((str(family), str(asset)))
    family_states = derive_family_states(
        events, families=families, now_utc=now_utc
    )

    if not dry_run:
        write_preset_policy(
            preset_states, generated_at_utc=now_utc, git_revision=git_rev
        )
        write_family_policy(
            family_states, generated_at_utc=now_utc, git_revision=git_rev
        )

    followup_specs = _build_followup_specs(
        registry=registry,
        events=events,
        preset_states=preset_states,
        now_utc=now_utc,
    )
    control_specs = _build_weekly_control_specs(
        registry=registry,
        events=events,
        now_utc=now_utc,
        templates=templates,
    )

    decision = decide(
        registry=registry,
        queue=queue,
        events=events,
        budget=budget,
        templates=templates,
        config=config,
        preset_state_by_name=preset_states,
        family_state_by_key=family_states,
        upstream_artifact_states=upstream,
        follow_up_candidate_specs=followup_specs,
        weekly_control_candidate_specs=control_specs,
        now_utc=now_utc,
    )
    if not dry_run:
        write_decision(decision, generated_at_utc=now_utc, git_revision=git_rev)

    if dry_run:
        return 0

    registry, queue, new_events = _apply_decision(
        decision=decision,
        registry=registry,
        queue=queue,
        budget=budget,
        events=events,
        now_utc=now_utc,
        config=config,
        skip_subprocess=skip_subprocess,
    )
    _write_ledger(new_events, now_utc=now_utc, git_rev=git_rev)

    write_registry(registry, generated_at_utc=now_utc, git_revision=git_rev)
    write_queue(queue, generated_at_utc=now_utc, git_revision=git_rev)

    refreshed_events = load_events(EVIDENCE_LEDGER_PATH)
    write_budget(budget, generated_at_utc=now_utc, git_revision=git_rev)
    _record_digest(
        registry=registry,
        events=refreshed_events,
        budget=budget,
        preset_states=preset_states,
        now_utc=now_utc,
        git_rev=git_rev,
    )
    assert_invariants(
        registry=registry,
        queue=queue,
        events=refreshed_events,
        max_concurrent_campaigns=config.max_concurrent_campaigns,
    )
    return 0


def _apply_decision(
    *,
    decision,
    registry: dict[str, Any],
    queue: dict[str, Any],
    budget,
    events: list[dict[str, Any]],
    now_utc: datetime,
    config,
    skip_subprocess: bool,
) -> tuple[dict[str, Any], dict[str, Any], list]:
    action = decision.decision.action
    new_events: list = []

    if action == "idle_noop":
        return registry, queue, new_events

    if action == "reclaim_stale_lease":
        cid = decision.decision.campaign_id
        registry = transition_state(
            registry,
            campaign_id=str(cid),
            to_state="pending",
            at_utc=now_utc,
            attempt_delta=1,
        )
        queue = clear_lease(queue, campaign_id=str(cid), to_state="pending")
        record = get_record(registry, str(cid)) or {}
        new_events.append(
            make_event(
                campaign_id=str(cid),
                parent_campaign_id=record.get("parent_campaign_id"),
                lineage_root_campaign_id=str(
                    record.get("lineage_root_campaign_id") or cid
                ),
                preset_name=str(record.get("preset_name") or ""),
                campaign_type=str(record.get("campaign_type") or ""),  # type: ignore[arg-type]
                event_type="lease_expired",
                at_utc=now_utc,
                reason_code="timeout",
            )
        )
        return registry, queue, new_events

    if action in ("cancel_duplicate", "cancel_upstream_stale"):
        cid = decision.decision.campaign_id
        registry = transition_state(
            registry,
            campaign_id=str(cid),
            to_state="canceled",
            at_utc=now_utc,
        )
        record = get_record(registry, str(cid)) or {}
        new_events.append(
            make_event(
                campaign_id=str(cid),
                parent_campaign_id=record.get("parent_campaign_id"),
                lineage_root_campaign_id=str(
                    record.get("lineage_root_campaign_id") or cid
                ),
                preset_name=str(record.get("preset_name") or ""),
                campaign_type=str(record.get("campaign_type") or ""),  # type: ignore[arg-type]
                event_type=(
                    "canceled_duplicate"
                    if action == "cancel_duplicate"
                    else "canceled_upstream_stale"
                ),
                at_utc=now_utc,
                reason_code=(
                    "user_cancel"
                    if action == "cancel_duplicate"
                    else "upstream_stale"
                ),
            )
        )
        queue = clear_lease(queue, campaign_id=str(cid), to_state="canceled")
        return registry, queue, new_events

    if action != "spawn":
        return registry, queue, new_events

    # --- spawn path --------------------------------------------------------
    preset_name = str(decision.decision.preset_name or "")
    campaign_type = str(decision.decision.campaign_type or "")
    template_id = str(decision.decision.template_id or "")
    parent = decision.decision.parent_campaign_id
    lineage_root = decision.decision.lineage_root_campaign_id or ""
    extra = decision.decision.extra or {}
    fingerprint = str(extra.get("input_artifact_fingerprint") or "")
    if not fingerprint:
        fingerprint = fingerprint_inputs(
            {"now": now_utc.isoformat(), "template": template_id}
        )
    cid = build_campaign_id(
        preset_name=preset_name,
        now_utc=now_utc,
        parent_or_lineage_root=parent or lineage_root,
        input_artifact_fingerprint=fingerprint,
    )
    spawned_iso = iso_utc(now_utc)
    new_record = _build_record(
        campaign_id=cid,
        template_id=template_id,
        preset_name=preset_name,
        campaign_type=campaign_type,
        priority_tier=int(decision.decision.priority_tier or 2),
        spawned_at_utc=spawned_iso,
        spawn_reason=str(decision.decision.spawn_reason or "cron_tick"),
        parent_campaign_id=parent,
        lineage_root_campaign_id=lineage_root or cid,
        input_artifact_fingerprint=fingerprint,
        estimate_seconds=int(decision.decision.estimate_seconds or 0),
        subtype=decision.decision.subtype,
    )
    registry = upsert_record(registry, new_record)
    queue = upsert_entry(queue, queue_entry_from_record(new_record.to_payload()))
    new_events.append(
        make_event(
            campaign_id=cid,
            parent_campaign_id=parent,
            lineage_root_campaign_id=new_record.lineage_root_campaign_id,
            preset_name=preset_name,
            campaign_type=campaign_type,  # type: ignore[arg-type]
            event_type="campaign_spawned",
            at_utc=now_utc,
            reason_code=REASON_CODE_NONE,
            source_artifact=str(REGISTRY_ARTIFACT_PATH.as_posix()),
        )
    )

    # Acquire lease immediately — single-worker MVP.
    worker_id = build_worker_id()
    lease: Lease = build_lease(
        campaign_id=cid,
        worker_id=worker_id,
        leased_at=now_utc,
        ttl_seconds=int(config.lease_ttl_seconds),
        attempt=int(new_record.attempt_count),
    )
    registry = transition_state(
        registry,
        campaign_id=cid,
        to_state="leased",
        at_utc=now_utc,
        extra_updates={"lease": lease.to_payload()},
    )
    queue = set_lease(queue, campaign_id=cid, lease_payload=lease.to_payload())
    new_events.append(
        make_event(
            campaign_id=cid,
            parent_campaign_id=parent,
            lineage_root_campaign_id=new_record.lineage_root_campaign_id,
            preset_name=preset_name,
            campaign_type=campaign_type,  # type: ignore[arg-type]
            event_type="campaign_leased",
            at_utc=now_utc,
            reason_code=REASON_CODE_NONE,
            extra={"lease_id": lease.lease_id, "worker_id": worker_id},
        )
    )

    budget = add_reservation(
        budget,
        campaign_id=cid,
        estimate_seconds=int(decision.decision.estimate_seconds or 0),
        priority_tier=int(decision.decision.priority_tier or 2),
        is_followup=(campaign_type in ("survivor_confirmation", "paper_followup")),
        reserved_at_utc=now_utc,
    )

    if skip_subprocess:
        # Admin mode (e.g. tests): leave in ``leased`` state.
        return registry, queue, new_events

    # Subprocess step -------------------------------------------------------
    registry = transition_state(
        registry,
        campaign_id=cid,
        to_state="running",
        at_utc=now_utc,
    )
    new_events.append(
        make_event(
            campaign_id=cid,
            parent_campaign_id=parent,
            lineage_root_campaign_id=new_record.lineage_root_campaign_id,
            preset_name=preset_name,
            campaign_type=campaign_type,  # type: ignore[arg-type]
            event_type="campaign_started",
            at_utc=now_utc,
            reason_code=REASON_CODE_NONE,
        )
    )
    rc, elapsed = _invoke_subprocess(
        preset_name=preset_name,
        campaign_id=cid,
        lease_ttl_seconds=int(config.lease_ttl_seconds),
    )
    finished_at = datetime.now(UTC)
    # v3.15.5 — hierarchical outcome dispatch. Post-v3.15.5 launcher
    # emissions are confined to ``LAUNCHER_EMITTABLE_OUTCOMES``; the
    # deprecated ``worker_crashed`` alias must never appear here. The
    # invariant assert below pins this contract at runtime.
    outcome: str
    meaningful: str
    reason_code: str
    if rc == EXIT_CODE_DEGENERATE_NO_SURVIVORS:
        outcome = "degenerate_no_survivors"
        meaningful = "meaningful_failure_confirmed"
        reason_code = "degenerate_no_evaluable_pairs"
        # Diagnostic origin check; outcome stays degenerate either way.
        rc2_status = _check_rc2_origin(
            EMPTY_RUN_DIAGNOSTICS_PATH,
            expected_campaign_id=cid,
        )
        if rc2_status != "rc2_origin_confirmed_degenerate":
            sys.stderr.write(
                f"campaign_launcher: rc=2 diagnostic event "
                f"{rc2_status} for campaign={cid}\n"
            )
    elif rc != 0:
        outcome = "technical_failure"
        meaningful = "uninformative_technical_failure"
        reason_code = _technical_failure_reason_code(rc)
    else:
        # v3.15.4: pass the spawned campaign_id so a stale sidecar from
        # a prior campaign cannot misclassify this run.
        paper_outcome, paper_reason = _classify_outcome_from_paper(
            Path("research/paper_readiness_latest.v1.json"),
            expected_campaign_id=cid,
        )
        if paper_outcome == "completed_with_candidates":
            outcome = "completed_with_candidates"
            meaningful = "meaningful_candidate_found"
            reason_code = REASON_CODE_NONE
        elif paper_outcome == "paper_blocked":
            outcome = "paper_blocked"
            meaningful = (
                "uninformative_technical_failure"
                if paper_reason in ("malformed_return_stream", "insufficient_oos_days")
                else "meaningful_failure_confirmed"
            )
            reason_code = str(paper_reason or "none")
        else:
            # v3.15.5 — try research_rejection before falling back to
            # the residual completed_no_survivor classification.
            rr_outcome, rr_reason = _classify_research_rejection(
                Path("research/paper_readiness_latest.v1.json"),
                CANDIDATE_REGISTRY_V1_PATH,
                expected_campaign_id=cid,
            )
            if rr_outcome == "research_rejection":
                outcome = "research_rejection"
                meaningful = "meaningful_family_falsified"
                reason_code = str(rr_reason or "none")
            else:
                outcome = "completed_no_survivor"
                meaningful = "duplicate_low_value_run"
                reason_code = "none"
    # v3.15.5 — post-dispatch invariant. Ensures the launcher never
    # leaks the deprecated ``worker_crashed`` alias and never emits an
    # outcome outside the post-v3.15.5 vocabulary. This is the runtime
    # backstop for the static AST test pinning the same contract.
    # Bandit B101: intentional defensive assert — the static AST test
    # in ``tests/unit/test_v3_15_5_outcome_invariant.py`` is the
    # primary contract; this assert exists as a runtime documentation
    # / fail-fast signal in non-optimised builds.
    assert outcome in LAUNCHER_EMITTABLE_OUTCOMES, (  # nosec B101
        f"v3.15.5 outcome invariant violated: {outcome!r} "
        f"not in LAUNCHER_EMITTABLE_OUTCOMES"
    )
    assert outcome != "worker_crashed", (  # nosec B101
        "v3.15.5: launcher must never emit deprecated 'worker_crashed'"
    )
    # v3.15.5 — degenerate / research_rejection are *structured*
    # completions; they belong in state="completed" so the policy
    # streak counter (which inspects ``campaign_completed`` events)
    # observes them. Only true technical failures stay in "failed".
    is_completed_state = (
        rc == 0 or rc == EXIT_CODE_DEGENERATE_NO_SURVIVORS
    )
    terminal_state = "completed" if is_completed_state else "failed"
    terminal_event = (
        "campaign_completed" if is_completed_state else "campaign_failed"
    )
    registry = record_outcome(
        registry,
        campaign_id=cid,
        outcome=outcome,  # type: ignore[arg-type]
        meaningful=meaningful,  # type: ignore[arg-type]
        actual_runtime_seconds=int(elapsed),
        reason_code=reason_code,
    )
    registry = transition_state(
        registry,
        campaign_id=cid,
        to_state=terminal_state,  # type: ignore[arg-type]
        at_utc=finished_at,
    )
    new_events.append(
        make_event(
            campaign_id=cid,
            parent_campaign_id=parent,
            lineage_root_campaign_id=new_record.lineage_root_campaign_id,
            preset_name=preset_name,
            campaign_type=campaign_type,  # type: ignore[arg-type]
            event_type=terminal_event,  # type: ignore[arg-type]
            at_utc=finished_at,
            reason_code=reason_code,
            outcome=outcome,
            meaningful_classification=meaningful,
        )
    )
    queue = clear_lease(queue, campaign_id=cid, to_state=terminal_state)  # type: ignore[arg-type]

    # Settle budget reservation.
    budget = settle_reservation(
        budget,
        campaign_id=cid,
        actual_runtime_seconds=int(elapsed),
        priority_tier=int(decision.decision.priority_tier or 2),
        template_id=template_id,
    )

    return registry, queue, new_events


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = ["main"]
