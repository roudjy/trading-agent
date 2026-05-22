"""No-candidate policy filter diagnostics sidecar.

This module explains why the campaign launcher most recently idled
with no candidates, using existing policy, routing, registry, queue,
and controlled-evaluation artifacts. It does not run the launcher or
change policy state.
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

POLICY_FILTER_DIAGNOSTICS_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path(
    "research/policy_filter_diagnostics_latest.v1.json"
)
DEFAULT_REPORT_MD_PATH: Final[Path] = Path(
    "research/policy_filter_diagnostics_latest.md"
)

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "policy_decision": Path("research/campaign_policy_decision_latest.v1.json"),
    "controlled_eval": Path("research/controlled_eval_latest.v1.json"),
    "campaign_registry": Path("research/campaign_registry_latest.v1.json"),
    "campaign_queue": Path("research/campaign_queue_latest.v1.json"),
    "campaign_evidence_ledger": Path("research/campaign_evidence_ledger_latest.v1.jsonl"),
    "sprint_routing_decision": Path(
        "research/discovery_sprints/sprint_routing_decision_latest.v1.json"
    ),
    "discovery_sprint_progress": Path(
        "research/discovery_sprints/discovery_sprint_progress_latest.v1.json"
    ),
    "research_state": Path("research/research_state_latest.v1.json"),
    "research_action_plan": Path("research/research_action_plan_latest.v1.json"),
}

TERMINAL_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset(
    {"completed", "failed", "canceled", "archived"}
)
ACTIVE_CAMPAIGN_STATES: Final[frozenset[str]] = frozenset(
    {"pending", "leased", "running"}
)


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


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rule_by_id(policy: dict[str, Any], rule_id: str) -> dict[str, Any]:
    for rule in _list_value(policy.get("rules_evaluated")):
        if isinstance(rule, dict) and rule.get("rule_id") == rule_id:
            return rule
    return {}


def _effective_policy(artifacts: dict[str, Any]) -> dict[str, Any]:
    policy = artifacts.get("policy_decision")
    if isinstance(policy, dict):
        return policy
    controlled = _dict_value(artifacts.get("controlled_eval"))
    return {
        "decision": {
            "action": controlled.get("latest_policy_action"),
            "reason": controlled.get("latest_policy_reason"),
        },
        "rules_evaluated": [
            {"rule_id": rule_id, **_dict_value(rule)}
            for rule_id, rule in _dict_value(
                controlled.get("latest_policy_rules_summary")
            ).items()
        ],
        "candidates_considered": [
            {}
            for _ in range(
                _safe_int(controlled.get("latest_policy_candidates_considered_count"))
            )
        ],
    }


def _candidate_rejections(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _list_value(policy.get("candidates_considered"))
        if isinstance(item, dict) and item.get("result") == "rejected"
    ]


def _candidate_count(policy: dict[str, Any]) -> int:
    candidates = policy.get("candidates_considered")
    if isinstance(candidates, list):
        return len(candidates)
    return 0


def _filter_counts(policy: dict[str, Any]) -> dict[str, Any]:
    filtering = _rule_by_id(policy, "R4_R7_filtering")
    idle = _rule_by_id(policy, "R8_idle")
    return {
        "candidates_considered_count": _candidate_count(policy),
        "r4_r7": {
            "present": bool(filtering),
            "result": filtering.get("result"),
            "surviving": _safe_int(filtering.get("surviving")),
            "rejected": _safe_int(filtering.get("rejected")),
        },
        "r8_idle": {
            "present": bool(idle),
            "result": idle.get("result"),
            "selected": idle.get("selected"),
        },
    }


def _classify_reject_reason(reason: str) -> str:
    if reason in {"budget", "daily_cap_reached"}:
        return "budget_cap"
    if reason in {"duplicate_forbidden", "followup_already_exists"}:
        return "duplicate_fingerprint"
    if reason.startswith("family_"):
        return "family_preset_policy_block"
    if reason.startswith("preset_") or reason.startswith("hypothesis_"):
        return "family_preset_policy_block"
    if "cooldown" in reason:
        return "cooldown"
    if "repeat" in reason or "retest" in reason:
        return "repeat_rejection"
    if reason == "template_not_eligible":
        return "no_eligible_template"
    return "unknown_filter"


def _rejection_summary(policy: dict[str, Any]) -> dict[str, Any]:
    rejections = _candidate_rejections(policy)
    by_reason = Counter(str(item.get("reject_reason") or "unknown") for item in rejections)
    by_category = Counter(_classify_reject_reason(reason) for reason in by_reason.elements())
    examples: dict[str, list[dict[str, Any]]] = {}
    for item in rejections:
        reason = str(item.get("reject_reason") or "unknown")
        examples.setdefault(reason, [])
        if len(examples[reason]) < 3:
            examples[reason].append(
                {
                    "template_id": item.get("template_id"),
                    "preset_name": item.get("preset_name"),
                    "campaign_type": item.get("campaign_type"),
                    "details": _dict_value(item.get("details")),
                }
            )
    return {
        "total_rejections": len(rejections),
        "by_reason": dict(sorted(by_reason.items())),
        "by_category": dict(sorted(by_category.items())),
        "examples_by_reason": dict(sorted(examples.items())),
    }


def _registry_queue_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    registry = _dict_value(artifacts.get("campaign_registry"))
    queue = _dict_value(artifacts.get("campaign_queue"))
    records = [
        record
        for record in _dict_value(registry.get("campaigns")).values()
        if isinstance(record, dict)
    ]
    queue_entries = [
        entry for entry in _list_value(queue.get("queue")) if isinstance(entry, dict)
    ]
    registry_states = Counter(str(record.get("state") or "unknown") for record in records)
    queue_states = Counter(str(entry.get("state") or "unknown") for entry in queue_entries)
    active_registry = sum(
        count for state, count in registry_states.items() if state in ACTIVE_CAMPAIGN_STATES
    )
    active_queue = sum(
        count for state, count in queue_states.items() if state in ACTIVE_CAMPAIGN_STATES
    )
    terminal_registry = sum(
        count
        for state, count in registry_states.items()
        if state in TERMINAL_CAMPAIGN_STATES
    )
    terminal_queue = sum(
        count for state, count in queue_states.items() if state in TERMINAL_CAMPAIGN_STATES
    )
    return {
        "registry_campaign_count": len(records),
        "registry_states": dict(sorted(registry_states.items())),
        "queue_item_count": len(queue_entries),
        "queue_states": dict(sorted(queue_states.items())),
        "active_registry_count": active_registry,
        "active_queue_count": active_queue,
        "terminal_registry_count": terminal_registry,
        "terminal_queue_count": terminal_queue,
        "terminal_state_effect": (
            "terminal_only_no_active_work"
            if (terminal_registry or terminal_queue) and not (active_registry or active_queue)
            else "not_terminal_only"
        ),
    }


def _routing_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    routing = _dict_value(artifacts.get("sprint_routing_decision"))
    counts = _dict_value(routing.get("counts"))
    filtered = sum(
        _safe_int(counts.get(key))
        for key in (
            "templates_filtered",
            "followups_filtered",
            "weekly_controls_filtered",
        )
    )
    return {
        "present": bool(routing),
        "routing_active": bool(routing.get("routing_active")),
        "counts": counts,
        "filtered_count": filtered,
        "sprint": _dict_value(routing.get("sprint")),
    }


def _status(
    *,
    condition: bool,
    evidence_present: bool,
) -> str:
    if condition:
        return "explained"
    return "not_observed" if evidence_present else "unknown"


def _diagnostic_rows(
    *,
    policy: dict[str, Any],
    rejection_summary: dict[str, Any],
    filter_counts: dict[str, Any],
    routing: dict[str, Any],
    registry_queue: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    decision = _dict_value(policy.get("decision"))
    by_category = _dict_value(rejection_summary.get("by_category"))
    by_reason = _dict_value(rejection_summary.get("by_reason"))
    policy_present = artifact_status["policy_decision"]["status"] == "present"
    candidates_count = int(filter_counts["candidates_considered_count"])
    no_candidates_idle = (
        decision.get("action") == "idle_noop"
        and decision.get("reason") == "no_candidates"
    )
    r4_r7 = _dict_value(filter_counts.get("r4_r7"))
    r8 = _dict_value(filter_counts.get("r8_idle"))
    worker = _rule_by_id(policy, "R3_single_worker")
    duplicate_cancel = _rule_by_id(policy, "R2_cancel_duplicate")

    rows = [
        {
            "diagnostic_id": "no_eligible_template",
            "status": _status(
                condition=(
                    no_candidates_idle
                    and candidates_count == 0
                    and _safe_int(r4_r7.get("surviving")) == 0
                ),
                evidence_present=policy_present,
            ),
            "count": 1
            if no_candidates_idle and candidates_count == 0
            else _safe_int(by_category.get("no_eligible_template")),
            "evidence": {
                "decision": decision,
                "candidates_considered_count": candidates_count,
                "r4_r7": r4_r7,
            },
            "explanation": (
                "No eligible template survived into a spawnable candidate."
            ),
        },
        {
            "diagnostic_id": "sprint_routing_exclusion",
            "status": _status(
                condition=bool(routing.get("routing_active"))
                and _safe_int(routing.get("filtered_count")) > 0,
                evidence_present=bool(routing.get("present")),
            ),
            "count": _safe_int(routing.get("filtered_count")),
            "evidence": routing,
            "explanation": "Active discovery sprint routing filtered launcher inputs.",
        },
        {
            "diagnostic_id": "cooldown",
            "status": _status(
                condition=_safe_int(by_category.get("cooldown")) > 0,
                evidence_present=policy_present,
            ),
            "count": _safe_int(by_category.get("cooldown")),
            "evidence": {"reject_reasons": by_reason},
            "explanation": "Recent campaign spawn timing blocked a candidate.",
        },
        {
            "diagnostic_id": "duplicate_fingerprint",
            "status": _status(
                condition=_safe_int(by_category.get("duplicate_fingerprint")) > 0
                or duplicate_cancel.get("result") == "trigger",
                evidence_present=policy_present,
            ),
            "count": _safe_int(by_category.get("duplicate_fingerprint"))
            + (1 if duplicate_cancel.get("result") == "trigger" else 0),
            "evidence": {
                "reject_reasons": by_reason,
                "r2_cancel_duplicate": duplicate_cancel,
            },
            "explanation": "A duplicate campaign fingerprint or child follow-up exists.",
        },
        {
            "diagnostic_id": "repeat_rejection",
            "status": _status(
                condition=_safe_int(by_category.get("repeat_rejection")) > 0,
                evidence_present=policy_present,
            ),
            "count": _safe_int(by_category.get("repeat_rejection")),
            "evidence": {"reject_reasons": by_reason},
            "explanation": "Repeat rejection or retest policy blocked the candidate.",
        },
        {
            "diagnostic_id": "budget_cap",
            "status": _status(
                condition=_safe_int(by_category.get("budget_cap")) > 0,
                evidence_present=policy_present,
            ),
            "count": _safe_int(by_category.get("budget_cap")),
            "evidence": {"reject_reasons": by_reason},
            "explanation": "Budget or per-template daily cap blocked candidates.",
        },
        {
            "diagnostic_id": "single_worker_block",
            "status": _status(
                condition=worker.get("result") == "block"
                or decision.get("reason") == "worker_busy",
                evidence_present=policy_present,
            ),
            "count": 1
            if worker.get("result") == "block" or decision.get("reason") == "worker_busy"
            else 0,
            "evidence": {"r3_single_worker": worker, "decision": decision},
            "explanation": "Single-worker policy found active work and idled.",
        },
        {
            "diagnostic_id": "family_preset_policy_block",
            "status": _status(
                condition=_safe_int(by_category.get("family_preset_policy_block")) > 0,
                evidence_present=policy_present,
            ),
            "count": _safe_int(by_category.get("family_preset_policy_block")),
            "evidence": {"reject_reasons": by_reason},
            "explanation": "Preset, hypothesis, or family policy blocked candidates.",
        },
        {
            "diagnostic_id": "queue_registry_terminal_state_effect",
            "status": _status(
                condition=registry_queue["terminal_state_effect"]
                == "terminal_only_no_active_work",
                evidence_present=artifact_status["campaign_registry"]["status"] == "present"
                or artifact_status["campaign_queue"]["status"] == "present",
            ),
            "count": registry_queue["terminal_registry_count"]
            + registry_queue["terminal_queue_count"],
            "evidence": registry_queue,
            "explanation": "Registry or queue contains terminal work but no active campaign.",
        },
        {
            "diagnostic_id": "r4_r7_filtering_counts",
            "status": "explained" if r4_r7.get("present") else "unknown",
            "count": _safe_int(r4_r7.get("rejected")),
            "evidence": r4_r7,
            "explanation": "R4_R7 records surviving and rejected policy candidates.",
        },
        {
            "diagnostic_id": "r8_idle_status",
            "status": "explained" if r8.get("present") else "unknown",
            "count": 1 if r8.get("result") == "fire" else 0,
            "evidence": r8,
            "explanation": "R8 fire means the policy idled after filtering.",
        },
    ]
    return rows


def _primary_explanations(rows: list[dict[str, Any]]) -> list[str]:
    priority = [
        "single_worker_block",
        "sprint_routing_exclusion",
        "family_preset_policy_block",
        "budget_cap",
        "duplicate_fingerprint",
        "cooldown",
        "repeat_rejection",
        "no_eligible_template",
        "queue_registry_terminal_state_effect",
    ]
    explained = {
        row["diagnostic_id"]: row
        for row in rows
        if row["status"] == "explained" and _safe_int(row.get("count")) > 0
    }
    out = [diagnostic_id for diagnostic_id in priority if diagnostic_id in explained]
    return out or ["unknown_policy_filter"]


def build_policy_filter_diagnostics_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    policy = _effective_policy(artifacts)
    filter_counts = _filter_counts(policy)
    rejection_summary = _rejection_summary(policy)
    routing = _routing_summary(artifacts)
    registry_queue = _registry_queue_summary(artifacts)
    rows = _diagnostic_rows(
        policy=policy,
        rejection_summary=rejection_summary,
        filter_counts=filter_counts,
        routing=routing,
        registry_queue=registry_queue,
        artifact_status=artifact_status,
    )
    decision = _dict_value(policy.get("decision"))
    primary = _primary_explanations(rows)
    return {
        "schema_version": POLICY_FILTER_DIAGNOSTICS_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "source_policy_path": artifact_status["policy_decision"]["path"],
        "artifact_inputs": artifact_status,
        "policy_summary": {
            "action": decision.get("action"),
            "reason": decision.get("reason"),
            **filter_counts,
        },
        "candidate_rejection_summary": rejection_summary,
        "routing_summary": routing,
        "registry_queue_summary": registry_queue,
        "diagnostics": rows,
        "primary_explanations": primary,
        "recommended_next_action": (
            "explain_screening_drop_reasons"
            if decision.get("action") == "spawn"
            else "inspect_campaign_policy_filters"
        ),
        "safety_invariants": {
            "runs_campaign_launcher": False,
            "mutates_policy": False,
            "mutates_campaign_artifacts": False,
            "writes_only_policy_filter_diagnostics_sidecars": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "frozen_contracts_unchanged": True,
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    policy = payload.get("policy_summary") or {}
    rejections = payload.get("candidate_rejection_summary") or {}
    routing = payload.get("routing_summary") or {}
    registry_queue = payload.get("registry_queue_summary") or {}
    lines = [
        "# Policy Filter Diagnostics",
        "",
        "## Current Policy Decision",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Latest action: `{policy.get('action')}`",
        f"- Latest reason: `{policy.get('reason')}`",
        f"- Candidates considered: {policy.get('candidates_considered_count')}",
        f"- R4_R7 surviving: {(policy.get('r4_r7') or {}).get('surviving')}",
        f"- R4_R7 rejected: {(policy.get('r4_r7') or {}).get('rejected')}",
        f"- R8 idle: `{(policy.get('r8_idle') or {}).get('result')}`",
        "",
        "## Primary Explanations",
        *[f"- `{item}`" for item in payload.get("primary_explanations") or []],
        "",
        "## Candidate Rejections",
        f"- Total rejected candidates: {rejections.get('total_rejections')}",
        f"- By reason: {json.dumps(rejections.get('by_reason') or {}, sort_keys=True)}",
        f"- By category: {json.dumps(rejections.get('by_category') or {}, sort_keys=True)}",
        "",
        "## Sprint Routing",
        f"- Present: {routing.get('present')}",
        f"- Active: {routing.get('routing_active')}",
        f"- Filtered count: {routing.get('filtered_count')}",
        "",
        "## Queue And Registry",
        f"- Registry campaigns: {registry_queue.get('registry_campaign_count')}",
        f"- Queue items: {registry_queue.get('queue_item_count')}",
        f"- Terminal-state effect: `{registry_queue.get('terminal_state_effect')}`",
        "",
        "## Diagnostic Rows",
        *[
            f"- `{row['diagnostic_id']}`: {row['status']} "
            f"(count {row['count']})"
            for row in payload.get("diagnostics") or []
        ],
        "",
        "## What To Expect Next",
        (
            "- Use these explanations to decide whether the next safe step is "
            "screening attribution, gate diagnostics, or an operator-gated policy change."
        ),
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
    payload = build_policy_filter_diagnostics_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.policy_filter_diagnostics",
        description="Explain no-candidate campaign policy filter outcomes.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read current QRE sidecars and write policy filter diagnostics.",
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
        "policy_filter_diagnostics: "
        f"primary={','.join(payload['primary_explanations'])} "
        f"action={payload['policy_summary']['action']} "
        f"reason={payload['policy_summary']['reason']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ARTIFACT_PATHS",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "POLICY_FILTER_DIAGNOSTICS_SCHEMA_VERSION",
    "build_from_current_artifacts",
    "build_policy_filter_diagnostics_payload",
    "load_current_artifacts",
    "main",
    "render_markdown_report",
]
