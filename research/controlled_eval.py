"""Controlled Research Evaluation Harness (v3.16.x-eval).

Operator-facing wrapper around the existing discovery sprint plus
Campaign Operating Layer route. This module does not call
``research.run_research`` directly; campaign execution remains owned by
``research.campaign_launcher``.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess  # nosec B404 - fixed argv subprocess wrapper
import sys
import time
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research import discovery_sprint as ds
from research._sidecar_io import write_sidecar_atomic
from research.campaign_evidence_ledger import load_events
from research.campaign_policy import POLICY_DECISION_PATH
from research.campaign_queue import (
    ACTIVE_QUEUE_STATES,
    QUEUE_ARTIFACT_PATH,
    load_queue,
)
from research.campaign_registry import REGISTRY_ARTIFACT_PATH, load_registry

CONTROLLED_EVAL_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path("research/controlled_eval_latest.v1.json")
DEFAULT_REPORT_MD_PATH: Final[Path] = Path("research/controlled_eval_latest.md")
DEFAULT_TIMEOUT_SECONDS_PER_CAMPAIGN: Final[int] = 3600
DEFAULT_POLL_SECONDS: Final[int] = 5
DEFAULT_MAX_CAMPAIGNS: Final[int] = 3
MAX_CAMPAIGNS_HARD_LIMIT: Final[int] = 10
MIN_TIMEOUT_SECONDS_PER_CAMPAIGN: Final[int] = 60
MAX_TIMEOUT_SECONDS_PER_CAMPAIGN: Final[int] = 21_600
MAX_POLL_SECONDS: Final[int] = 300

LEDGER_PATH: Final[Path] = Path("research/campaign_evidence_ledger_latest.v1.jsonl")
RUN_CAMPAIGN_PATH: Final[Path] = Path("research/run_campaign_latest.v1.json")
SCREENING_EVIDENCE_PATH: Final[Path] = Path("research/screening_evidence_latest.v1.json")
INFORMATION_GAIN_PATH: Final[Path] = Path(
    "research/campaigns/evidence/information_gain_latest.v1.json"
)
VIABILITY_PATH: Final[Path] = Path("research/campaigns/evidence/viability_latest.v1.json")
STOP_CONDITIONS_PATH: Final[Path] = Path(
    "research/campaigns/evidence/stop_conditions_latest.v1.json"
)
SPAWN_PROPOSALS_PATH: Final[Path] = Path(
    "research/campaigns/evidence/spawn_proposals_latest.v1.json"
)

ACTIVE_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset({"pending", "leased", "running"})
TERMINAL_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset(
    {"completed", "failed", "canceled", "archived"}
)
MAX_ACTIVE_CAMPAIGN_IDS: Final[int] = 10

MEANINGFUL_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {
        "meaningful_candidate_found",
        "meaningful_family_falsified",
        "meaningful_failure_confirmed",
    }
)
MEANINGFUL_FAILURE_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "degenerate_no_survivors",
        "research_rejection",
    }
)


@dataclass(frozen=True)
class LauncherTick:
    tick_index: int
    returncode: int | None
    timed_out: bool
    elapsed_seconds: int
    stdout_tail: str
    stderr_tail: str
    completed_campaign_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "tick_index": self.tick_index,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "elapsed_seconds": self.elapsed_seconds,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "completed_campaign_ids": list(self.completed_campaign_ids),
        }


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _tail_text(value: str | None, *, max_chars: int = 2000) -> str:
    text = value or ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _profile_name_from_sprint(registry_payload: dict[str, Any] | None) -> str | None:
    profile = (registry_payload or {}).get("profile")
    if not isinstance(profile, dict):
        return None
    name = profile.get("name")
    return str(name) if name else None


def _plan_presets(registry_payload: dict[str, Any] | None) -> frozenset[str]:
    entries = ((registry_payload or {}).get("plan") or {}).get("entries") or []
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("preset_name")
        if name:
            names.add(str(name))
    return frozenset(names)


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _record_matches_sprint(
    record: dict[str, Any],
    *,
    sprint_registry: dict[str, Any] | None,
) -> bool:
    sprint_id = (sprint_registry or {}).get("sprint_id")
    extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
    if sprint_id and extra.get("sprint_id") == sprint_id:
        return True

    plan_presets = _plan_presets(sprint_registry)
    if record.get("preset_name") not in plan_presets:
        return False
    started = _parse_dt((sprint_registry or {}).get("started_at_utc"))
    if started is None:
        return True
    finished = _parse_dt(record.get("finished_at_utc"))
    if finished is None:
        return False
    return finished >= started


def _completed_campaign_ids(
    registry: dict[str, Any],
    *,
    sprint_registry: dict[str, Any] | None,
) -> set[str]:
    out: set[str] = set()
    for cid, record in (registry.get("campaigns") or {}).items():
        if not isinstance(record, dict):
            continue
        if record.get("state") != "completed":
            continue
        if _record_matches_sprint(record, sprint_registry=sprint_registry):
            out.add(str(cid))
    return out


def _ledger_meaningful_by_campaign(
    ledger_events: list[dict[str, Any]],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for event in ledger_events:
        cid = event.get("campaign_id")
        meaningful = event.get("meaningful_classification")
        if cid and meaningful:
            out[str(cid)] = str(meaningful)
    return out


def summarize_campaign_records(
    *,
    registry: dict[str, Any],
    sprint_registry: dict[str, Any] | None,
    ledger_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    meaningful_by_campaign = _ledger_meaningful_by_campaign(ledger_events)
    records: list[dict[str, Any]] = []
    campaigns = registry.get("campaigns") or {}
    for cid in sorted(campaigns):
        record = campaigns[cid]
        if not isinstance(record, dict):
            continue
        if not _record_matches_sprint(record, sprint_registry=sprint_registry):
            continue
        meaningful = meaningful_by_campaign.get(str(cid)) or record.get("meaningful_classification")
        records.append(
            {
                "campaign_id": str(record.get("campaign_id") or cid),
                "preset_name": record.get("preset_name"),
                "state": record.get("state"),
                "outcome": record.get("outcome"),
                "reason_code": record.get("reason_code"),
                "meaningful_classification": meaningful,
                "spawned_at_utc": record.get("spawned_at_utc"),
                "finished_at_utc": record.get("finished_at_utc"),
            }
        )
    return records


def summarize_registry_ledger_invariants(
    *,
    campaign_records: list[dict[str, Any]],
    ledger_events: list[dict[str, Any]],
) -> dict[str, Any]:
    completed_campaign_ids = {
        str(record.get("campaign_id"))
        for record in campaign_records
        if record.get("state") == "completed" and record.get("campaign_id")
    }
    ledger_completed_campaign_ids = {
        str(event.get("campaign_id"))
        for event in ledger_events
        if isinstance(event, dict)
        and event.get("event_type") == "campaign_completed"
        and event.get("campaign_id")
    }
    missing_completed_ledger_event_ids = sorted(
        completed_campaign_ids - ledger_completed_campaign_ids
    )
    status = "failed" if missing_completed_ledger_event_ids else "passed"
    reason_codes = (
        ["completed_campaign_missing_campaign_completed_ledger_event"]
        if missing_completed_ledger_event_ids
        else []
    )
    return {
        "status": status,
        "reason_codes": reason_codes,
        "operator_review_required": bool(missing_completed_ledger_event_ids),
        "completed_campaign_count": len(completed_campaign_ids),
        "campaign_completed_ledger_event_count": len(ledger_completed_campaign_ids),
        "missing_completed_ledger_event_ids": missing_completed_ledger_event_ids,
    }


def summarize_screening_evidence(
    screening_evidence_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    summary = (
        screening_evidence_payload.get("summary")
        if isinstance(screening_evidence_payload, dict)
        else None
    )
    if not isinstance(summary, dict):
        return {
            "present": False,
            "total_candidates": 0,
            "passed_screening": 0,
            "rejected_screening": 0,
            "promotion_grade_candidates": 0,
            "sufficient_oos_evidence_candidates": 0,
            "qre_linkage_blocked_candidates": 0,
            "sufficient_oos_but_unlinked_candidates": 0,
        }

    return {
        "present": True,
        "total_candidates": int(summary.get("total_candidates") or 0),
        "passed_screening": int(summary.get("passed_screening") or 0),
        "rejected_screening": int(summary.get("rejected_screening") or 0),
        "promotion_grade_candidates": int(summary.get("promotion_grade_candidates") or 0),
        "sufficient_oos_evidence_candidates": int(
            summary.get("sufficient_oos_evidence_candidates") or 0
        ),
        "qre_linkage_blocked_candidates": int(
            summary.get("qre_linkage_blocked_candidates") or 0
        ),
        "sufficient_oos_but_unlinked_candidates": int(
            summary.get("sufficient_oos_but_unlinked_candidates") or 0
        ),
    }


def summarize_latest_run(run_campaign_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not run_campaign_payload:
        return {
            "run_id": None,
            "status": None,
            "screening_rejected_count": 0,
            "validation_candidate_count": 0,
            "error_type": None,
            "error_message": None,
        }
    summary = run_campaign_payload.get("summary") or {}
    batches = run_campaign_payload.get("batches") or []
    failed_batch = next(
        (batch for batch in batches if isinstance(batch, dict) and batch.get("error_type")),
        {},
    )
    screening_rejected = summary.get("screening_rejected_count")
    if screening_rejected is None:
        screening_rejected = summary.get("rejected_candidate_count", 0)
    validation_count = summary.get("validation_candidate_count")
    if validation_count is None:
        validation_count = summary.get("promoted_candidate_count", 0)
    return {
        "run_id": run_campaign_payload.get("run_id"),
        "status": run_campaign_payload.get("status"),
        "screening_rejected_count": int(screening_rejected or 0),
        "validation_candidate_count": int(validation_count or 0),
        "error_type": run_campaign_payload.get("error_type") or failed_batch.get("error_type"),
        "error_message": run_campaign_payload.get("error_message")
        or failed_batch.get("reason_detail"),
    }


def summarize_latest_policy_decision(
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not payload:
        return {
            "latest_policy_decision_present": False,
            "latest_policy_action": None,
            "latest_policy_reason": None,
            "latest_policy_candidates_considered_count": 0,
            "latest_policy_rules_summary": {},
        }

    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    candidates = payload.get("candidates_considered")
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    rules_summary: dict[str, dict[str, Any]] = {}
    rules = payload.get("rules_evaluated")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule_id = rule.get("rule_id")
            if not rule_id:
                continue
            rules_summary[str(rule_id)] = {str(k): v for k, v in rule.items() if k != "rule_id"}

    return {
        "latest_policy_decision_present": True,
        "latest_policy_action": decision.get("action"),
        "latest_policy_reason": decision.get("reason"),
        "latest_policy_candidates_considered_count": candidate_count,
        "latest_policy_rules_summary": rules_summary,
    }


def summarize_active_campaigns(registry: dict[str, Any]) -> dict[str, Any]:
    active_ids: list[str] = []
    for cid, record in (registry.get("campaigns") or {}).items():
        if not isinstance(record, dict):
            continue
        state = str(record.get("state") or "")
        if state not in ACTIVE_CAMPAIGN_STATES:
            continue
        active_ids.append(str(record.get("campaign_id") or cid))
    active_ids.sort()
    return {
        "active_campaign_count": len(active_ids),
        "active_campaign_ids": active_ids[:MAX_ACTIVE_CAMPAIGN_IDS],
    }


def summarize_queue_state(queue_payload: dict[str, Any] | None) -> dict[str, Any]:
    entries = (queue_payload or {}).get("queue")
    if not isinstance(entries, list):
        entries = []
    active_count = 0
    terminal_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        state = str(entry.get("state") or "")
        if state in ACTIVE_QUEUE_STATES:
            active_count += 1
        elif state in TERMINAL_CAMPAIGN_STATES:
            terminal_count += 1
    return {
        "queue_item_count": len(entries),
        "queue_active_count": active_count,
        "queue_terminal_count": terminal_count,
    }


def build_intelligence_artifact_status(
    *,
    information_gain_path: Path = INFORMATION_GAIN_PATH,
    viability_path: Path = VIABILITY_PATH,
    stop_conditions_path: Path = STOP_CONDITIONS_PATH,
    spawn_proposals_path: Path = SPAWN_PROPOSALS_PATH,
) -> dict[str, str]:
    paths = {
        "information_gain": information_gain_path,
        "viability": viability_path,
        "stop_conditions": stop_conditions_path,
        "spawn_proposals": spawn_proposals_path,
    }
    return {
        name: "present" if _read_json(path) is not None else "missing"
        for name, path in paths.items()
    }


def _classify_verdict(
    *,
    campaign_records: list[dict[str, Any]],
    ticks: list[LauncherTick],
    intelligence_artifact_status: dict[str, str],
    latest_policy_summary: dict[str, Any],
    registry_ledger_invariant_summary: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    reason_codes: list[str] = []
    timed_out = any(tick.timed_out for tick in ticks)
    if timed_out:
        reason_codes.append("launcher_timeout")
        return (
            {
                "status": "timeout",
                "reason_codes": reason_codes,
                "human_summary": "Campaign launcher timed out before the bounded evaluation completed.",
            },
            "operator_review_required",
        )

    if registry_ledger_invariant_summary.get("status") == "failed":
        reason_codes.append("registry_ledger_invariant_violation")
        reason_codes.extend(
            str(code)
            for code in registry_ledger_invariant_summary.get("reason_codes", [])
            if code
        )
        return (
            {
                "status": "technical_failure",
                "reason_codes": reason_codes,
                "human_summary": (
                    "Campaign registry and evidence ledger disagree about completed "
                    "campaign evidence; operator review is required before results "
                    "can be trusted."
                ),
            },
            "operator_review_required",
        )

    completed = [r for r in campaign_records if r.get("state") == "completed"]
    failed = [r for r in campaign_records if r.get("state") == "failed"]
    if not completed and failed:
        reason_codes.append("campaign_failed")
        return (
            {
                "status": "technical_failure",
                "reason_codes": reason_codes,
                "human_summary": "Campaigns failed without campaign-level completion evidence.",
            },
            "operator_review_required",
        )
    launcher_invariant_violations = [
        tick
        for tick in ticks
        if tick.returncode not in (None, 0)
        and "campaign invariant violation" in tick.stderr_tail.lower()
    ]
    if launcher_invariant_violations:
        reason_codes.append("launcher_invariant_violation")
        return (
            {
                "status": "technical_failure",
                "reason_codes": reason_codes,
                "human_summary": (
                    "Campaign launcher reported a campaign invariant violation "
                    "before campaign-level completion evidence could be trusted."
                ),
            },
            "operator_review_required",
        )

    if not completed:
        reason_codes.append("no_campaign_completed")
        if (
            latest_policy_summary.get("latest_policy_action") == "idle_noop"
            and latest_policy_summary.get("latest_policy_reason") == "no_candidates"
        ):
            reason_codes.append("no_candidates_policy_block")
            return (
                {
                    "status": "no_campaign_completed",
                    "reason_codes": reason_codes,
                    "human_summary": (
                        "No campaign completed because the latest launcher "
                        "policy decision idled with no candidates."
                    ),
                },
                "inspect_campaign_policy_filters",
            )
        return (
            {
                "status": "no_campaign_completed",
                "reason_codes": reason_codes,
                "human_summary": "No compatible campaign completed during the controlled evaluation window.",
            },
            "rerun_with_more_campaigns",
        )

    outcomes = {str(r.get("outcome") or "") for r in completed}
    meaningful = {str(r.get("meaningful_classification") or "") for r in completed}
    missing_intelligence = [
        name for name, status in intelligence_artifact_status.items() if status != "present"
    ]
    has_meaningful_failure = bool(outcomes & MEANINGFUL_FAILURE_OUTCOMES) or bool(
        meaningful & MEANINGFUL_CLASSIFICATIONS
    )
    if has_meaningful_failure:
        for outcome in sorted(outcomes):
            if outcome:
                reason_codes.append(outcome)
        if "degenerate_no_survivors" in outcomes and missing_intelligence:
            reason_codes.append("missing_intelligence_artifacts")
            return (
                {
                    "status": "useful_observation",
                    "reason_codes": reason_codes,
                    "human_summary": (
                        "Campaign-level evidence contains a meaningful research "
                        "failure, but intelligence artifacts are missing."
                    ),
                },
                "inspect_failure_observability",
            )
        return (
            {
                "status": "useful_observation",
                "reason_codes": reason_codes,
                "human_summary": "Campaign-level evidence contains a meaningful research observation.",
            },
            (
                "stop_due_to_no_survivors"
                if "degenerate_no_survivors" in outcomes
                else "continue_sprint"
            ),
        )

    if "technical_failure" in outcomes:
        reason_codes.append("technical_failure")
        return (
            {
                "status": "technical_failure",
                "reason_codes": reason_codes,
                "human_summary": "Campaign completed with a technical failure outcome.",
            },
            "inspect_failure_observability",
        )

    reason_codes.append("campaign_completed_without_decisive_evidence")
    return (
        {
            "status": "insufficient_data",
            "reason_codes": reason_codes,
            "human_summary": "Campaigns completed, but the bounded sample is not yet decisive.",
        },
        "continue_sprint",
    )


def build_report_payload(
    *,
    profile: str,
    max_campaigns: int,
    sprint_started_by_harness: bool,
    sprint_reused: bool,
    observed_total_before: int,
    observed_total_after: int,
    campaigns_attempted: int,
    sprint_registry: dict[str, Any] | None,
    sprint_progress: dict[str, Any] | None,
    registry: dict[str, Any],
    ledger_events: list[dict[str, Any]],
    run_campaign_payload: dict[str, Any] | None,
    latest_policy_decision_payload: dict[str, Any] | None,
    queue_payload: dict[str, Any] | None,
    intelligence_artifact_status: dict[str, str],
    ticks: list[LauncherTick],
    screening_evidence_payload: dict[str, Any] | None = None,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    campaign_records = summarize_campaign_records(
        registry=registry,
        sprint_registry=sprint_registry,
        ledger_events=ledger_events,
    )
    completed_records = [r for r in campaign_records if r.get("state") == "completed"]
    by_preset = Counter(str(r.get("preset_name") or "unknown") for r in completed_records)
    by_outcome = Counter(str(r.get("outcome") or "unknown") for r in completed_records)
    latest_policy_summary = summarize_latest_policy_decision(latest_policy_decision_payload)
    active_campaign_summary = summarize_active_campaigns(registry)
    queue_summary = summarize_queue_state(queue_payload)
    registry_ledger_invariant_summary = summarize_registry_ledger_invariants(
        campaign_records=campaign_records,
        ledger_events=ledger_events,
    )
    verdict, next_action = _classify_verdict(
        campaign_records=campaign_records,
        ticks=ticks,
        intelligence_artifact_status=intelligence_artifact_status,
        latest_policy_summary=latest_policy_summary,
        registry_ledger_invariant_summary=registry_ledger_invariant_summary,
    )
    return {
        "schema_version": CONTROLLED_EVAL_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "profile": profile,
        "max_campaigns": int(max_campaigns),
        "sprint_id": (sprint_registry or {}).get("sprint_id"),
        "sprint_state": (sprint_registry or {}).get("state")
        or (sprint_progress or {}).get("state"),
        "sprint_started_by_harness": bool(sprint_started_by_harness),
        "sprint_reused": bool(sprint_reused),
        "observed_total_before": int(observed_total_before),
        "observed_total_after": int(observed_total_after),
        "campaigns_attempted": int(campaigns_attempted),
        "campaigns_completed": len(completed_records),
        "campaigns_by_preset": dict(sorted(by_preset.items())),
        "campaigns_by_outcome": dict(sorted(by_outcome.items())),
        "campaign_records": campaign_records,
        "registry_ledger_invariant_summary": registry_ledger_invariant_summary,
        "latest_run_summary": summarize_latest_run(run_campaign_payload),
        "screening_evidence_summary": summarize_screening_evidence(
            screening_evidence_payload
        ),
        **latest_policy_summary,
        **active_campaign_summary,
        **queue_summary,
        "intelligence_artifact_status": intelligence_artifact_status,
        "launcher_ticks": [tick.to_payload() for tick in ticks],
        "verdict": verdict,
        "recommended_next_action": next_action,
        "campaign_level_evidence_valid": bool(completed_records)
        and registry_ledger_invariant_summary.get("status") == "passed",
        "strategy_synthesis_sandbox_needed": "not_enough_evidence_not_yet",
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    verdict = report.get("verdict") or {}
    artifacts = report.get("intelligence_artifact_status") or {}
    by_outcome = report.get("campaigns_by_outcome") or {}
    missing_artifacts = [name for name, status in artifacts.items() if status != "present"]
    rules_summary = report.get("latest_policy_rules_summary") or {}
    filtering = rules_summary.get("R4_R7_filtering") or {}
    idle = rules_summary.get("R8_idle") or {}
    lines = [
        "# Controlled Evaluation Report",
        "",
        "## What Ran",
        f"- Profile: `{report.get('profile')}`",
        f"- Sprint: `{report.get('sprint_id')}` ({report.get('sprint_state')})",
        f"- Launcher ticks attempted: {report.get('campaigns_attempted')}",
        f"- Max campaigns cap: {report.get('max_campaigns')}",
        "",
        "## What Completed",
        f"- Campaigns completed: {report.get('campaigns_completed')}",
        f"- Outcomes: {json.dumps(by_outcome, sort_keys=True)}",
        f"- Campaign-level evidence valid: {report.get('campaign_level_evidence_valid')}",
        "",
        "## What Failed",
        f"- Verdict: `{verdict.get('status')}`",
        f"- Reason codes: {', '.join(verdict.get('reason_codes') or []) or 'none'}",
        f"- Summary: {verdict.get('human_summary')}",
        "",
        "## Bottleneck",
        (
            "- Latest launcher decision: "
            f"{report.get('latest_policy_action') or 'missing'} / "
            f"{report.get('latest_policy_reason') or 'missing'}"
        ),
        ("- Candidates considered: " f"{report.get('latest_policy_candidates_considered_count')}"),
        f"- R4_R7 surviving: {filtering.get('surviving', 'unknown')}",
        f"- R4_R7 rejected: {filtering.get('rejected', 'unknown')}",
        f"- R8 idle: {idle.get('result', 'unknown')}",
        f"- Active campaigns: {report.get('active_campaign_count')}",
        (
            "- Policy/no-candidate condition, not a running campaign: "
            f"{_is_policy_no_candidate_condition(report)}"
        ),
        (
            "- Missing intelligence artifacts: "
            + (", ".join(missing_artifacts) if missing_artifacts else "none")
        ),
        f"- Recommended next action: `{report.get('recommended_next_action')}`",
        "",
        "## Strategy Synthesis Sandbox",
        "- Not enough evidence / not yet. This harness only validates campaign-level COL evidence and does not add synthesis.",
        "",
    ]
    return "\n".join(lines)


def _is_policy_no_candidate_condition(report: dict[str, Any]) -> bool:
    return (
        report.get("campaigns_completed") == 0
        and report.get("latest_policy_action") == "idle_noop"
        and report.get("latest_policy_reason") == "no_candidates"
        and int(report.get("active_campaign_count") or 0) == 0
    )


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _run_launcher_tick(
    *,
    tick_index: int,
    timeout_seconds: int,
    before_completed_ids: set[str],
    sprint_registry: dict[str, Any] | None,
) -> LauncherTick:
    args = [sys.executable, "-m", "research.campaign_launcher"]
    started = _now_utc()
    try:
        completed = subprocess.run(  # nosec B603
            args,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=timeout_seconds,
        )
        timed_out = False
        returncode: int | None = int(completed.returncode)
        stdout_tail = _tail_text(completed.stdout)
        stderr_tail = _tail_text(completed.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout_tail = _tail_text(
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else exc.stdout
        )
        stderr_tail = _tail_text(
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else exc.stderr
        )
    elapsed = int((_now_utc() - started).total_seconds())
    with suppress(Exception):
        ds.update_sprint_progress()
    after_registry = load_registry(REGISTRY_ARTIFACT_PATH)
    after_completed_ids = _completed_campaign_ids(after_registry, sprint_registry=sprint_registry)
    new_completed = tuple(sorted(after_completed_ids - before_completed_ids))
    return LauncherTick(
        tick_index=tick_index,
        returncode=returncode,
        timed_out=timed_out,
        elapsed_seconds=elapsed,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        completed_campaign_ids=new_completed,
    )


def _ensure_active_sprint(profile: str) -> tuple[bool, bool]:
    now = _now_utc()
    existing = ds.load_sprint_registry()
    if ds.is_active_sprint(registry_payload=existing, now_utc=now):
        existing_profile = _profile_name_from_sprint(existing)
        if existing_profile != profile:
            raise RuntimeError(
                "active sprint profile mismatch: "
                f"requested={profile!r}, active={existing_profile!r}"
            )
        return False, True
    rc = ds.cmd_run(profile, out=io.StringIO())
    if rc != 0:
        raise RuntimeError(f"failed to start discovery sprint for {profile!r}")
    return True, False


def run_controlled_eval(
    *,
    profile: str,
    max_campaigns: int,
    timeout_seconds_per_campaign: int,
    poll_seconds: int,
    report_json: Path,
    report_md: Path,
    out=sys.stdout,
) -> int:
    if max_campaigns < 1 or max_campaigns > MAX_CAMPAIGNS_HARD_LIMIT:
        raise ValueError(f"max_campaigns must be between 1 and {MAX_CAMPAIGNS_HARD_LIMIT}")
    sprint_started, sprint_reused = _ensure_active_sprint(profile)
    ds.update_sprint_progress()
    initial_progress = ds.load_sprint_progress() or {}
    observed_before = int(initial_progress.get("observed_total") or 0)
    sprint_registry = ds.load_sprint_registry()
    registry_before = load_registry(REGISTRY_ARTIFACT_PATH)
    completed_ids = _completed_campaign_ids(registry_before, sprint_registry=sprint_registry)

    ticks: list[LauncherTick] = []
    for tick_index in range(1, max_campaigns + 1):
        tick = _run_launcher_tick(
            tick_index=tick_index,
            timeout_seconds=timeout_seconds_per_campaign,
            before_completed_ids=completed_ids,
            sprint_registry=sprint_registry,
        )
        ticks.append(tick)
        registry_now = load_registry(REGISTRY_ARTIFACT_PATH)
        completed_ids = _completed_campaign_ids(registry_now, sprint_registry=sprint_registry)
        out.write(
            f"tick {tick_index}/{max_campaigns}: "
            f"rc={tick.returncode if tick.returncode is not None else 'timeout'} "
            f"new_completed={len(tick.completed_campaign_ids)}\n"
        )
        if tick.timed_out:
            break
        if tick_index < max_campaigns and poll_seconds > 0:
            time.sleep(poll_seconds)

    ds.update_sprint_progress()
    final_progress = ds.load_sprint_progress() or {}
    final_registry = ds.load_sprint_registry()
    campaign_registry = load_registry(REGISTRY_ARTIFACT_PATH)
    ledger_events = load_events(LEDGER_PATH)
    report = build_report_payload(
        profile=profile,
        max_campaigns=max_campaigns,
        sprint_started_by_harness=sprint_started,
        sprint_reused=sprint_reused,
        observed_total_before=observed_before,
        observed_total_after=int(final_progress.get("observed_total") or 0),
        campaigns_attempted=len(ticks),
        sprint_registry=final_registry,
        sprint_progress=final_progress,
        registry=campaign_registry,
        ledger_events=ledger_events,
        run_campaign_payload=_read_json(RUN_CAMPAIGN_PATH),
        screening_evidence_payload=_read_json(SCREENING_EVIDENCE_PATH),
        latest_policy_decision_payload=_read_json(POLICY_DECISION_PATH),
        queue_payload=load_queue(QUEUE_ARTIFACT_PATH),
        intelligence_artifact_status=build_intelligence_artifact_status(),
        ticks=ticks,
    )
    write_sidecar_atomic(report_json, report)
    _write_text_atomic(report_md, render_markdown_report(report))
    out.write(
        "controlled_eval: "
        f"completed={report['campaigns_completed']} "
        f"verdict={report['verdict']['status']} "
        f"next={report['recommended_next_action']}\n"
    )
    return 0 if report["verdict"]["status"] != "technical_failure" else 1


def _bounded_int(
    value: str,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.controlled_eval",
        description=(
            "Controlled campaign-level evaluation harness over discovery_sprint "
            "and campaign_launcher."
        ),
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--max-campaigns",
        type=lambda v: _bounded_int(
            v,
            name="max_campaigns",
            minimum=1,
            maximum=MAX_CAMPAIGNS_HARD_LIMIT,
        ),
        default=DEFAULT_MAX_CAMPAIGNS,
    )
    parser.add_argument(
        "--timeout-seconds-per-campaign",
        type=lambda v: _bounded_int(
            v,
            name="timeout_seconds_per_campaign",
            minimum=MIN_TIMEOUT_SECONDS_PER_CAMPAIGN,
            maximum=MAX_TIMEOUT_SECONDS_PER_CAMPAIGN,
        ),
        default=DEFAULT_TIMEOUT_SECONDS_PER_CAMPAIGN,
    )
    parser.add_argument(
        "--poll-seconds",
        type=lambda v: _bounded_int(
            v,
            name="poll_seconds",
            minimum=0,
            maximum=MAX_POLL_SECONDS,
        ),
        default=DEFAULT_POLL_SECONDS,
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON_PATH)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return run_controlled_eval(
            profile=args.profile,
            max_campaigns=args.max_campaigns,
            timeout_seconds_per_campaign=args.timeout_seconds_per_campaign,
            poll_seconds=args.poll_seconds,
            report_json=args.report_json,
            report_md=args.report_md,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "CONTROLLED_EVAL_SCHEMA_VERSION",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "LauncherTick",
    "build_intelligence_artifact_status",
    "build_report_payload",
    "main",
    "render_markdown_report",
    "run_controlled_eval",
    "summarize_active_campaigns",
    "summarize_campaign_records",
    "summarize_latest_run",
    "summarize_screening_evidence",
    "summarize_latest_policy_decision",
    "summarize_queue_state",
    "summarize_registry_ledger_invariants",
]
