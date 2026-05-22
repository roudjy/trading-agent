"""Research decision state and attribution sidecar.

This module is read-only with respect to campaign artifacts. It
summarizes current controlled-evaluation and Campaign OS evidence into
deterministic research-state sidecars; it does not run research, start
campaigns, or mutate campaign ledgers.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

RESEARCH_STATE_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path("research/research_state_latest.v1.json")
DEFAULT_REPORT_MD_PATH: Final[Path] = Path("research/research_state_latest.md")

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "controlled_eval": Path("research/controlled_eval_latest.v1.json"),
    "policy_decision": Path("research/campaign_policy_decision_latest.v1.json"),
    "campaign_registry": Path("research/campaign_registry_latest.v1.json"),
    "campaign_evidence_ledger": Path("research/campaign_evidence_ledger_latest.v1.jsonl"),
    "discovery_sprint_progress": Path(
        "research/discovery_sprints/discovery_sprint_progress_latest.v1.json"
    ),
    "information_gain": Path(
        "research/campaigns/evidence/information_gain_latest.v1.json"
    ),
    "viability": Path("research/campaigns/evidence/viability_latest.v1.json"),
    "stop_conditions": Path(
        "research/campaigns/evidence/stop_conditions_latest.v1.json"
    ),
    "spawn_proposals": Path(
        "research/campaigns/evidence/spawn_proposals_latest.v1.json"
    ),
}

ACTIVE_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset({"pending", "leased", "running"})
TERMINAL_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"campaign_completed", "campaign_failed"}
)
DISALLOWED_ACTIONS: Final[list[str]] = [
    "strategy_synthesis_without_attribution",
    "strategy_synthesis_outside_research_sandbox",
    "modify_presets_without_operator_approval",
    "modify_templates_without_operator_approval",
    "change_screening_budgets_without_operator_approval",
    "paper_trading",
    "shadow_trading",
    "live_trading",
    "broker_changes",
    "risk_changes",
    "execution_changes",
    "direct_strategy_deployment",
]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    if not isinstance(payload, dict):
        return None, "malformed"
    return payload, "present"


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "missing"
    events: list[dict[str, Any]] = []
    malformed = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    malformed = True
                    continue
                if isinstance(item, dict):
                    events.append(item)
                else:
                    malformed = True
    except OSError:
        return [], "malformed"
    return events, "malformed" if malformed and not events else "present"


def load_current_artifacts(
    *,
    root: Path = Path("."),
    artifact_paths: dict[str, Path] = ARTIFACT_PATHS,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    payloads: dict[str, Any] = {}
    statuses: dict[str, dict[str, str]] = {}
    for name, relative_path in artifact_paths.items():
        path = root / relative_path
        if name == "campaign_evidence_ledger":
            payload, status = _read_jsonl(path)
        else:
            payload, status = _read_json(path)
        payloads[name] = payload
        statuses[name] = {"path": relative_path.as_posix(), "status": status}
    return payloads, statuses


def _policy_summary(
    policy: dict[str, Any] | None,
    controlled_eval: dict[str, Any] | None,
) -> dict[str, Any]:
    policy = policy or {}
    controlled_eval = controlled_eval or {}
    decision = policy.get("decision") if isinstance(policy.get("decision"), dict) else {}
    rules = policy.get("rules_evaluated") if isinstance(policy.get("rules_evaluated"), list) else []
    rules_by_id: dict[str, dict[str, Any]] = {}
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("rule_id"):
            continue
        rules_by_id[str(rule["rule_id"])] = {k: v for k, v in rule.items() if k != "rule_id"}

    candidates = policy.get("candidates_considered")
    candidate_count = len(candidates) if isinstance(candidates, list) else None
    if candidate_count is None:
        candidate_count = controlled_eval.get("latest_policy_candidates_considered_count")

    return {
        "action": decision.get("action") or controlled_eval.get("latest_policy_action"),
        "reason": decision.get("reason") or controlled_eval.get("latest_policy_reason"),
        "candidates_considered": int(candidate_count or 0),
        "rules": rules_by_id or controlled_eval.get("latest_policy_rules_summary") or {},
    }


def _campaign_records(registry: dict[str, Any] | None) -> list[dict[str, Any]]:
    campaigns = (registry or {}).get("campaigns")
    if not isinstance(campaigns, dict):
        return []
    records = [record for record in campaigns.values() if isinstance(record, dict)]
    records.sort(key=lambda r: str(r.get("finished_at_utc") or r.get("spawned_at_utc") or ""))
    return records


def _ledger_terminal_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terminals = [
        event
        for event in events
        if isinstance(event, dict) and event.get("event_type") in TERMINAL_EVENT_TYPES
    ]
    terminals.sort(key=lambda event: str(event.get("at_utc") or ""))
    return terminals


def _campaign_outcomes(
    registry: dict[str, Any] | None,
    ledger_events: list[dict[str, Any]],
    controlled_eval: dict[str, Any] | None,
) -> dict[str, Any]:
    records = _campaign_records(registry)
    terminal_records = [
        record
        for record in records
        if record.get("state") in {"completed", "failed"} or record.get("outcome")
    ]
    terminal_events = _ledger_terminal_events(ledger_events)
    outcomes: list[str] = []
    reason_codes: list[str] = []
    preset_names: set[str] = set()
    active_campaign_ids: list[str] = []

    for record in records:
        if str(record.get("state") or "") in ACTIVE_CAMPAIGN_STATES:
            active_campaign_ids.append(str(record.get("campaign_id") or "unknown"))
        outcome = record.get("outcome")
        if outcome:
            outcomes.append(str(outcome))
        reason = record.get("reason_code")
        if reason:
            reason_codes.append(str(reason))
        preset = record.get("preset_name")
        if preset:
            preset_names.add(str(preset))

    for event in terminal_events:
        outcome = event.get("outcome")
        if outcome:
            outcomes.append(str(outcome))
        reason = event.get("reason_code")
        if reason and reason != "none":
            reason_codes.append(str(reason))
        preset = event.get("preset_name")
        if preset:
            preset_names.add(str(preset))

    controlled_counts = (controlled_eval or {}).get("campaigns_by_outcome")
    if isinstance(controlled_counts, dict):
        for outcome, count in controlled_counts.items():
            try:
                repeat = int(count)
            except (TypeError, ValueError):
                repeat = 0
            outcomes.extend([str(outcome)] * max(0, repeat))

    return {
        "records": terminal_records,
        "terminal_events": terminal_events,
        "outcome_counts": dict(sorted(Counter(outcomes).items())),
        "reason_codes": sorted(set(reason_codes)),
        "preset_names": sorted(preset_names),
        "active_campaign_count": len(active_campaign_ids),
        "active_campaign_ids": sorted(active_campaign_ids),
    }


def _has_outcome(outcomes: dict[str, int], value: str) -> bool:
    return int(outcomes.get(value) or 0) > 0


def _drop_reasons_known(campaign_summary: dict[str, Any]) -> bool:
    known_tokens = {
        "insufficient_trades",
        "no_oos_returns",
        "timeout",
        "cost_sensitivity",
        "parameter_instability",
        "data_coverage_gap",
        "strict_gate_rejection",
    }
    if any(reason in known_tokens for reason in campaign_summary["reason_codes"]):
        return True
    for record in campaign_summary["records"]:
        for key in ("drop_reasons", "screening_drop_reasons", "failure_attribution"):
            value = record.get(key)
            if value:
                return True
        extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
        if extra.get("drop_reasons") or extra.get("screening_drop_reasons"):
            return True
    return False


def _gate_diagnostics_known(campaign_summary: dict[str, Any]) -> bool:
    for record in campaign_summary["records"]:
        if record.get("gate_diagnostics") or record.get("failure_attribution"):
            return True
        extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
        if extra.get("gate_diagnostics") or extra.get("failure_attribution"):
            return True
    return False


def _observed_total(sprint_progress: dict[str, Any] | None) -> int:
    try:
        return int((sprint_progress or {}).get("observed_total") or 0)
    except (TypeError, ValueError):
        return 0


def _campaign_count(viability: dict[str, Any] | None) -> int | None:
    if not isinstance(viability, dict):
        return None
    candidates = [
        viability.get("campaign_count"),
        (viability.get("summary") or {}).get("campaign_count")
        if isinstance(viability.get("summary"), dict)
        else None,
        (viability.get("viability") or {}).get("campaign_count")
        if isinstance(viability.get("viability"), dict)
        else None,
    ]
    for value in candidates:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _has_linked_market_insight(payloads: dict[str, Any]) -> bool:
    keys = {
        "market_context_insight",
        "market_context_insights",
        "supporting_market_insight",
        "linked_market_insight",
    }
    stack: list[Any] = list(payloads.values())
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if any(key in item and item[key] for key in keys):
                return True
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def build_research_state_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    controlled_eval = artifacts.get("controlled_eval")
    policy = _policy_summary(artifacts.get("policy_decision"), controlled_eval)
    campaign_summary = _campaign_outcomes(
        artifacts.get("campaign_registry"),
        artifacts.get("campaign_evidence_ledger") or [],
        controlled_eval,
    )
    outcomes = campaign_summary["outcome_counts"]
    missing_artifacts = [
        name
        for name, status in artifact_status.items()
        if status.get("status") != "present"
    ]
    malformed_artifacts = [
        name
        for name, status in artifact_status.items()
        if status.get("status") == "malformed"
    ]

    no_candidates_policy = (
        policy["action"] == "idle_noop"
        and policy["reason"] == "no_candidates"
        and policy["candidates_considered"] == 0
    )
    no_campaign_completed = (
        (controlled_eval or {}).get("verdict", {}).get("status") == "no_campaign_completed"
        or not outcomes
    )
    has_degenerate = _has_outcome(outcomes, "degenerate_no_survivors")
    has_completed_no_survivor = _has_outcome(outcomes, "completed_no_survivor")
    drop_reasons_known = _drop_reasons_known(campaign_summary)
    gate_diagnostics_known = _gate_diagnostics_known(campaign_summary)

    active_campaign_count = int(
        (controlled_eval or {}).get("active_campaign_count")
        or campaign_summary["active_campaign_count"]
        or 0
    )

    policy_state = "unknown"
    if no_candidates_policy:
        policy_state = "blocked_no_candidates"
    elif policy["action"] in {"spawn", "spawn_campaign", "enqueue_campaign"}:
        policy_state = "can_spawn"
    elif policy["reason"] in {"single_worker_active", "single_worker_block"}:
        policy_state = "blocked_single_worker"
    elif policy["action"] and policy["action"] != "idle_noop":
        policy_state = "can_spawn"
    elif policy["action"] == "idle_noop":
        policy_state = "blocked_by_unknown_policy"

    preset_state = "unknown"
    if has_completed_no_survivor:
        preset_state = "completed_no_survivor"
    elif has_degenerate:
        preset_state = "degenerate_screening_failure"
    elif outcomes.get("canceled_duplicate") or outcomes.get("duplicate_low_value_run"):
        preset_state = "low_value_duplicate"
    elif outcomes:
        preset_state = "insufficient_evidence"

    hypothesis_state = "unknown"
    if no_candidates_policy and no_campaign_completed:
        hypothesis_state = "blocked_by_policy"
    elif has_degenerate and not drop_reasons_known:
        hypothesis_state = "active_but_blocked_by_evaluability"
    elif has_completed_no_survivor:
        hypothesis_state = "needs_more_diagnostic_evidence"
    elif outcomes:
        hypothesis_state = "insufficient_evidence"
    elif missing_artifacts:
        hypothesis_state = "unknown"

    evidence_quality = {
        "state": "insufficient_data",
        "rank": 0,
        "summary": "No campaign-level evidence was available.",
    }
    if no_candidates_policy and no_campaign_completed:
        evidence_quality = {
            "state": "policy_only",
            "rank": 1,
            "summary": "No-candidate policy evidence is not hypothesis evidence.",
        }
    if has_degenerate:
        evidence_quality = {
            "state": "screening_or_evaluability_failure",
            "rank": 2,
            "summary": "Degenerate no-survivor evidence needs drop-reason attribution.",
        }
    if has_completed_no_survivor:
        evidence_quality = {
            "state": "completed_no_survivor",
            "rank": 3,
            "summary": (
                "Completed no-survivor evidence is stronger than degenerate "
                "screening failure but does not falsify the hypothesis."
            ),
        }

    failure_attribution = {
        "state": "unknown",
        "attributed": False,
        "primary_blocker": None,
        "missing": [],
    }
    if no_candidates_policy and no_campaign_completed:
        failure_attribution = {
            "state": "policy_only_failure",
            "attributed": True,
            "primary_blocker": "policy_no_candidates",
            "missing": ["policy_filter_diagnostics"],
        }
    if has_degenerate:
        failure_attribution = {
            "state": (
                "screening_failure_attributed"
                if drop_reasons_known
                else "screening_evaluability_unattributed"
            ),
            "attributed": drop_reasons_known,
            "primary_blocker": "screening_or_evaluability",
            "missing": [] if drop_reasons_known else ["screening_drop_reasons"],
        }
    if has_completed_no_survivor and not has_degenerate:
        failure_attribution = {
            "state": (
                "gate_rejection_attributed"
                if gate_diagnostics_known
                else "gate_rejection_unattributed"
            ),
            "attributed": gate_diagnostics_known,
            "primary_blocker": "validation_or_promotion_gate",
            "missing": [] if gate_diagnostics_known else ["gate_diagnostics"],
        }

    instrumentation_states: list[str] = []
    instrumentation_gaps: list[str] = []
    observed_total = _observed_total(artifacts.get("discovery_sprint_progress"))
    viability_campaign_count = _campaign_count(artifacts.get("viability"))
    if observed_total > 0 and viability_campaign_count == 0:
        instrumentation_states.append("viability_window_misaligned")
        instrumentation_gaps.append("viability_window_misaligned")
    if malformed_artifacts:
        instrumentation_states.append("missing_artifacts")
        instrumentation_gaps.extend(f"malformed:{name}" for name in malformed_artifacts)
    if missing_artifacts:
        instrumentation_states.append("missing_artifacts")
        instrumentation_gaps.extend(f"missing:{name}" for name in missing_artifacts)
    if not outcomes and not no_candidates_policy:
        instrumentation_states.append("insufficient_data")
    if not instrumentation_states:
        instrumentation_states.append("healthy")

    next_allowed_actions: list[str] = []
    if no_candidates_policy:
        _append_unique(next_allowed_actions, "inspect_campaign_policy_filters")
    if has_degenerate and not drop_reasons_known:
        _append_unique(next_allowed_actions, "explain_screening_drop_reasons")
    if has_completed_no_survivor:
        _append_unique(next_allowed_actions, "inspect_gate_diagnostics")
    if "viability_window_misaligned" in instrumentation_states:
        _append_unique(next_allowed_actions, "check_evidence_window_alignment")
    if not next_allowed_actions:
        _append_unique(next_allowed_actions, "collect_campaign_level_evidence")

    if no_candidates_policy:
        synthesis_gate = "blocked_policy_only_failure"
        next_best_test = "inspect_campaign_policy_filters"
    elif has_degenerate and not drop_reasons_known:
        synthesis_gate = "blocked_insufficient_attribution"
        next_best_test = "explain_screening_drop_reasons"
    elif has_degenerate:
        synthesis_gate = "blocked_evaluability_primary"
        next_best_test = "run_bounded_controlled_eval_after_drop_reason_review"
    elif has_completed_no_survivor:
        synthesis_gate = "blocked_insufficient_attribution"
        next_best_test = "inspect_gate_diagnostics"
    else:
        synthesis_gate = "not_allowed_yet"
        next_best_test = next_allowed_actions[0]

    attributed = bool(failure_attribution["attributed"])
    failed_presets = len(campaign_summary["preset_names"])
    if (
        _has_linked_market_insight(artifacts)
        and attributed
        and failed_presets >= 2
        and policy_state not in {"blocked_no_candidates", "blocked_single_worker"}
        and failure_attribution["primary_blocker"] != "screening_or_evaluability"
    ):
        synthesis_gate = "allowed_for_sandbox_review"
        _append_unique(next_allowed_actions, "review_sandbox_synthesis_inputs")

    payload = {
        "schema_version": RESEARCH_STATE_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "artifact_inputs": artifact_status,
        "hypothesis_state": hypothesis_state,
        "preset_state": preset_state,
        "policy_state": policy_state,
        "evidence_quality": evidence_quality,
        "failure_attribution": failure_attribution,
        "instrumentation_state": instrumentation_states[0],
        "instrumentation_states": instrumentation_states,
        "instrumentation_gaps": sorted(set(instrumentation_gaps)),
        "next_allowed_actions": next_allowed_actions,
        "disallowed_actions": DISALLOWED_ACTIONS,
        "synthesis_gate": synthesis_gate,
        "next_best_test": next_best_test,
        "policy_summary": policy,
        "campaign_summary": campaign_summary,
        "safety_invariants": {
            "runs_research": False,
            "starts_campaign_launcher": False,
            "mutates_campaign_artifacts": False,
            "writes_only_research_state_sidecars": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "frozen_contracts_unchanged": True,
        },
    }
    payload["states"] = {
        "hypothesis_state": hypothesis_state,
        "preset_state": preset_state,
        "policy_state": policy_state,
        "instrumentation_states": instrumentation_states,
        "synthesis_gate": synthesis_gate,
    }
    return payload


def render_markdown_report(payload: dict[str, Any]) -> str:
    evidence = payload.get("evidence_quality") or {}
    attribution = payload.get("failure_attribution") or {}
    policy = payload.get("policy_summary") or {}
    campaign = payload.get("campaign_summary") or {}
    lines = [
        "# Research Decision State",
        "",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Hypothesis state: `{payload.get('hypothesis_state')}`",
        f"- Preset state: `{payload.get('preset_state')}`",
        f"- Policy state: `{payload.get('policy_state')}`",
        f"- Instrumentation states: {', '.join(payload.get('instrumentation_states') or [])}",
        f"- Synthesis gate: `{payload.get('synthesis_gate')}`",
        f"- Next-best test: `{payload.get('next_best_test')}`",
        "",
        "## Evidence",
        f"- Evidence quality: `{evidence.get('state')}` (rank {evidence.get('rank')})",
        f"- Summary: {evidence.get('summary')}",
        f"- Campaign outcomes: {json.dumps(campaign.get('outcome_counts') or {}, sort_keys=True)}",
        f"- Active campaigns: {campaign.get('active_campaign_count')}",
        "",
        "## Attribution",
        f"- Failure attribution: `{attribution.get('state')}`",
        f"- Attributed: {attribution.get('attributed')}",
        f"- Primary blocker: `{attribution.get('primary_blocker')}`",
        f"- Missing attribution: {', '.join(attribution.get('missing') or []) or 'none'}",
        "",
        "## Policy",
        f"- Latest action: `{policy.get('action')}`",
        f"- Latest reason: `{policy.get('reason')}`",
        f"- Candidates considered: {policy.get('candidates_considered')}",
        "",
        "## Next Allowed Actions",
        *[f"- `{action}`" for action in payload.get("next_allowed_actions") or []],
        "",
        "## Disallowed Actions",
        *[f"- `{action}`" for action in payload.get("disallowed_actions") or []],
        "",
        "## Instrumentation Gaps",
        *[f"- `{gap}`" for gap in payload.get("instrumentation_gaps") or ["none"]],
        "",
    ]
    return "\n".join(lines)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def build_from_current_artifacts(
    *,
    root: Path = Path("."),
    report_json: Path = DEFAULT_REPORT_JSON_PATH,
    report_md: Path = DEFAULT_REPORT_MD_PATH,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    artifacts, statuses = load_current_artifacts(root=root)
    payload = build_research_state_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.research_state",
        description="Build read-only research decision state sidecars from current artifacts.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read known current QRE artifacts and write research_state sidecars.",
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON_PATH)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.from_current_artifacts:
        parser.error("--from-current-artifacts is required")
    payload = build_from_current_artifacts(
        report_json=args.report_json,
        report_md=args.report_md,
    )
    print(
        "research_state: "
        f"hypothesis={payload['hypothesis_state']} "
        f"policy={payload['policy_state']} "
        f"synthesis={payload['synthesis_gate']} "
        f"next={payload['next_best_test']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ARTIFACT_PATHS",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "RESEARCH_STATE_SCHEMA_VERSION",
    "build_from_current_artifacts",
    "build_research_state_payload",
    "load_current_artifacts",
    "main",
    "render_markdown_report",
]
