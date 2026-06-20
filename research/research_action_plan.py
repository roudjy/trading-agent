"""Research action planner sidecar.

This module turns the current research decision state into a bounded
operator-facing action plan. It reads existing sidecar artifacts only,
does not run research, and writes only the action-plan sidecars.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

RESEARCH_ACTION_PLAN_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path(
    "research/research_action_plan_latest.v1.json"
)
DEFAULT_REPORT_MD_PATH: Final[Path] = Path("research/research_action_plan_latest.md")

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "research_state": Path("research/research_state_latest.v1.json"),
    "research_state_markdown": Path("research/research_state_latest.md"),
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

AUTOMATIC_ACTION_IDS: Final[tuple[str, ...]] = (
    "inspect_campaign_policy_filters",
    "explain_screening_drop_reasons",
    "inspect_gate_diagnostics",
    "collect_campaign_level_evidence",
    "controlled_eval_bounded",
    "disposable_workspace_eval",
    "evidence_window_alignment_check",
    "generate_daily_research_report",
    "generate_candidate_alert_if_candidate_exists",
)
OPERATOR_GATED_ACTION_IDS: Final[tuple[str, ...]] = (
    "modify_presets",
    "modify_templates",
    "change_screening_budgets",
    "change_promotion_criteria",
    "enable_synthesis_lane",
    "approve_sandbox_synthesis",
)
FORBIDDEN_ACTION_IDS: Final[tuple[str, ...]] = (
    "paper_trading",
    "shadow_trading",
    "live_trading",
    "broker_changes",
    "risk_changes",
    "execution_changes",
    "direct_strategy_deployment",
    "production_strategy_overwrite",
    "strategy_synthesis_outside_research_sandbox",
)
SYNTHESIS_BLOCKED_STATES: Final[frozenset[str]] = frozenset(
    {
        "blocked_policy_only_failure",
        "blocked_insufficient_attribution",
        "blocked_evaluability_primary",
        "not_allowed_yet",
    }
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


def _read_text(path: Path) -> tuple[str | None, str]:
    if not path.exists():
        return None, "missing"
    try:
        return path.read_text(encoding="utf-8"), "present"
    except OSError:
        return None, "malformed"


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
        elif name == "research_state_markdown":
            payload, status = _read_text(path)
        else:
            payload, status = _read_json(path)
        payloads[name] = payload
        statuses[name] = {"path": relative_path.as_posix(), "status": status}
    return payloads, statuses


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _append_unique(items: list[dict[str, Any]], action: dict[str, Any]) -> None:
    if not any(item["action_id"] == action["action_id"] for item in items):
        items.append(action)


def _action(
    *,
    action_id: str,
    action_type: str,
    priority: int,
    allowed_mode: str,
    reason_codes: list[str],
    expected_outputs: list[str],
    max_scope: str,
    stop_conditions: list[str],
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "action_type": action_type,
        "priority": int(priority),
        "allowed_mode": allowed_mode,
        "reason_codes": reason_codes,
        "expected_outputs": expected_outputs,
        "max_scope": max_scope,
        "stop_conditions": stop_conditions,
    }


def _active_campaign_count(state: dict[str, Any]) -> int:
    campaign_summary = _dict_value(state.get("campaign_summary"))
    controlled = _dict_value(state.get("controlled_eval_summary"))
    return _safe_int(
        state.get("active_campaign_count"),
        _safe_int(
            controlled.get("active_campaign_count"),
            _safe_int(campaign_summary.get("active_campaign_count")),
        ),
    )


def _has_candidate_signal(artifacts: dict[str, Any], state: dict[str, Any]) -> bool:
    controlled = _dict_value(artifacts.get("controlled_eval"))
    campaign_summary = _dict_value(state.get("campaign_summary"))
    candidate_tokens = {
        "candidate_found",
        "meaningful_candidate_found",
        "candidate_ready",
        "candidate_exists",
    }
    stack: list[Any] = [controlled, campaign_summary, state]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                key_l = str(key).lower()
                if (
                    key_l in {"candidate_count", "validation_candidate_count"}
                    and _safe_int(value) > 0
                ):
                    return True
                if isinstance(value, str) and value in candidate_tokens:
                    return True
                stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _state_summary(
    *,
    state: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> dict[str, Any]:
    evidence_quality = _dict_value(state.get("evidence_quality"))
    failure_attribution = _dict_value(state.get("failure_attribution"))
    policy_summary = _dict_value(state.get("policy_summary"))
    return {
        "hypothesis_state": state.get("hypothesis_state"),
        "preset_state": state.get("preset_state"),
        "policy_state": state.get("policy_state"),
        "evidence_quality": evidence_quality.get("state"),
        "failure_attribution": failure_attribution.get("state"),
        "instrumentation_states": _list_value(state.get("instrumentation_states")),
        "synthesis_gate": state.get("synthesis_gate"),
        "next_best_test": state.get("next_best_test"),
        "active_campaign_count": _active_campaign_count(state),
        "policy_action": policy_summary.get("action"),
        "policy_reason": policy_summary.get("reason"),
        "source_research_state_status": artifact_status["research_state"]["status"],
    }


def _automatic_actions(
    *,
    state: dict[str, Any],
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    policy_state = state.get("policy_state")
    failure_attribution = _dict_value(state.get("failure_attribution"))
    failure_state = failure_attribution.get("state")
    evidence_quality = _dict_value(state.get("evidence_quality"))
    evidence_state = evidence_quality.get("state")
    synthesis_gate = state.get("synthesis_gate")
    instrumentation_states = set(map(str, _list_value(state.get("instrumentation_states"))))
    active_campaign_count = _active_campaign_count(state)
    missing_state = artifact_status["research_state"]["status"] != "present"

    if policy_state == "blocked_no_candidates":
        _append_unique(
            actions,
            _action(
                action_id="inspect_campaign_policy_filters",
                action_type="diagnostic",
                priority=1,
                allowed_mode="automatic_bounded",
                reason_codes=["policy_state_blocked_no_candidates"],
                expected_outputs=[
                    "research/policy_filter_diagnostics_latest.v1.json",
                    "research/policy_filter_diagnostics_latest.md",
                ],
                max_scope="Explain why the launcher produced idle_noop/no_candidates.",
                stop_conditions=[
                    "policy decision artifact is missing or malformed",
                    "diagnostics require changing campaign policy",
                ],
            ),
        )

    if failure_state == "screening_evaluability_unattributed":
        _append_unique(
            actions,
            _action(
                action_id="explain_screening_drop_reasons",
                action_type="diagnostic",
                priority=2 if policy_state == "blocked_no_candidates" else 1,
                allowed_mode="automatic_bounded",
                reason_codes=["screening_evaluability_unattributed"],
                expected_outputs=[
                    "research/screening_failure_attribution_latest.v1.json",
                    "research/screening_failure_attribution_latest.md",
                ],
                max_scope="Attribute screening drop reasons from existing campaign artifacts.",
                stop_conditions=[
                    "drop-reason evidence is unavailable",
                    "classification would require changing screening budgets",
                ],
            ),
        )

    next_allowed_actions = state.get("next_allowed_actions")
    if not isinstance(next_allowed_actions, list):
        next_allowed_actions = []

    if "inspect_gate_diagnostics" in next_allowed_actions:
        _append_unique(
            actions,
            _action(
                action_id="inspect_gate_diagnostics",
                action_type="diagnostic",
                priority=3 if policy_state == "blocked_no_candidates" else 2,
                allowed_mode="automatic_bounded",
                reason_codes=["gate_diagnostics_requested_by_research_state"],
                expected_outputs=["gate diagnostic summary from existing campaign evidence"],
                max_scope="Inspect validation and promotion gate evidence without changing gates.",
                stop_conditions=[
                    "gate diagnostics are absent",
                    "next step would require changing promotion criteria",
                ],
            ),
        )

    if "collect_campaign_level_evidence" in next_allowed_actions:
        _append_unique(
            actions,
            _action(
                action_id="collect_campaign_level_evidence",
                action_type="evidence_collection",
                priority=2,
                allowed_mode="automatic_bounded",
                reason_codes=["campaign_level_evidence_requested_by_research_state"],
                expected_outputs=[
                    "campaign-level evidence summary from existing research artifacts"
                ],
                max_scope=(
                    "Collect and summarize existing campaign-level evidence "
                    "without changing presets, gates, budgets, or strategies."
                ),
                stop_conditions=[
                    "required campaign evidence is unavailable",
                    "collection would require launching a new campaign",
                    "next step would require changing research criteria",
                ],
            ),
        )

    if "viability_window_misaligned" in instrumentation_states:
        _append_unique(
            actions,
            _action(
                action_id="evidence_window_alignment_check",
                action_type="diagnostic",
                priority=4,
                allowed_mode="automatic_bounded",
                reason_codes=["viability_window_misaligned"],
                expected_outputs=["evidence window alignment diagnosis"],
                max_scope="Compare discovery sprint and viability evidence windows.",
                stop_conditions=["alignment fix would require mutating source campaign evidence"],
            ),
        )

    if missing_state:
        _append_unique(
            actions,
            _action(
                action_id="inspect_gate_diagnostics",
                action_type="diagnostic",
                priority=1,
                allowed_mode="automatic_bounded",
                reason_codes=["research_state_missing"],
                expected_outputs=["missing artifact inventory"],
                max_scope="Report missing research_state and avoid launching research.",
                stop_conditions=["research_state must be regenerated before action execution"],
            ),
        )

    controlled_eval_allowed = (
        not missing_state
        and active_campaign_count == 0
        and policy_state not in {"blocked_no_candidates", "blocked_single_worker"}
        and synthesis_gate not in {"blocked_policy_only_failure"}
    )
    diagnostic_first = bool(actions)
    if controlled_eval_allowed:
        _append_unique(
            actions,
            _action(
                action_id="controlled_eval_bounded",
                action_type="evaluation",
                priority=20 if diagnostic_first else 1,
                allowed_mode="automatic_bounded",
                reason_codes=["bounded_campaign_level_evaluation_allowed"],
                expected_outputs=[
                    "research/controlled_eval_latest.v1.json",
                    "research/controlled_eval_latest.md",
                ],
                max_scope="Run a bounded controlled_eval within configured campaign caps.",
                stop_conditions=[
                    "campaign launcher returns a technical failure",
                    "operator-gated policy or preset change is required",
                    "active campaign appears during preflight",
                ],
            ),
        )
        if evidence_state in {"insufficient_data", "policy_only", None}:
            _append_unique(
                actions,
                _action(
                    action_id="disposable_workspace_eval",
                    action_type="evaluation",
                    priority=21 if diagnostic_first else 2,
                    allowed_mode="automatic_bounded",
                    reason_codes=["prefer_isolated_reproducibility_check"],
                    expected_outputs=["disposable workspace evaluation notes"],
                    max_scope="Evaluate in a disposable workspace without promoting artifacts.",
                    stop_conditions=[
                        "workspace setup requires protected path changes",
                        "evaluation would touch paper/shadow/live paths",
                    ],
                ),
            )

    _append_unique(
        actions,
        _action(
            action_id="generate_daily_research_report",
            action_type="reporting",
            priority=80,
            allowed_mode="automatic_bounded",
            reason_codes=["operator_visibility"],
            expected_outputs=["research/daily_research_report_latest.v1.json"],
            max_scope="Summarize current research state and diagnostics.",
            stop_conditions=["reporting would require running trading lanes"],
        ),
    )

    if _has_candidate_signal(artifacts, state):
        _append_unique(
            actions,
            _action(
                action_id="generate_candidate_alert_if_candidate_exists",
                action_type="reporting",
                priority=70,
                allowed_mode="automatic_bounded",
                reason_codes=["candidate_signal_present"],
                expected_outputs=["research/candidate_alert_latest.v1.json"],
                max_scope="Emit an alert for existing research candidates only.",
                stop_conditions=["candidate evidence is ambiguous or missing"],
            ),
        )

    return sorted(actions, key=lambda item: (item["priority"], item["action_id"]))


def _operator_gated_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    synthesis_gate = state.get("synthesis_gate")
    synthesis_blocked = synthesis_gate in SYNTHESIS_BLOCKED_STATES or not synthesis_gate
    actions = [
        _action(
            action_id="modify_presets",
            action_type="research_change",
            priority=100,
            allowed_mode="operator_gated",
            reason_codes=["changes_research_search_space"],
            expected_outputs=["reviewed preset change"],
            max_scope="Operator-approved preset edits only.",
            stop_conditions=["approval is absent", "change expands beyond preset scope"],
        ),
        _action(
            action_id="modify_templates",
            action_type="research_change",
            priority=101,
            allowed_mode="operator_gated",
            reason_codes=["changes_research_generation_templates"],
            expected_outputs=["reviewed template change"],
            max_scope="Operator-approved template edits only.",
            stop_conditions=["approval is absent", "change touches strategy implementation"],
        ),
        _action(
            action_id="change_screening_budgets",
            action_type="research_change",
            priority=102,
            allowed_mode="operator_gated",
            reason_codes=["changes_evaluation_budget"],
            expected_outputs=["reviewed budget change"],
            max_scope="Operator-approved screening budget adjustment.",
            stop_conditions=["approval is absent", "change weakens quality gates"],
        ),
        _action(
            action_id="change_promotion_criteria",
            action_type="research_change",
            priority=103,
            allowed_mode="operator_gated",
            reason_codes=["changes_candidate_promotion_gate"],
            expected_outputs=["reviewed promotion criteria change"],
            max_scope="Operator-approved promotion criteria adjustment.",
            stop_conditions=["approval is absent", "change enables paper/shadow/live"],
        ),
        _action(
            action_id="enable_synthesis_lane",
            action_type="synthesis_governance",
            priority=104,
            allowed_mode="operator_gated",
            reason_codes=(
                ["synthesis_gate_blocked", str(synthesis_gate or "missing")]
                if synthesis_blocked
                else ["synthesis_gate_allows_sandbox_review"]
            ),
            expected_outputs=["operator synthesis-lane approval"],
            max_scope="Enable only the isolated research sandbox lane.",
            stop_conditions=[
                "synthesis gate is blocked",
                "approval is absent",
                "scope leaves research/sandbox paths",
            ],
        ),
        _action(
            action_id="approve_sandbox_synthesis",
            action_type="synthesis_governance",
            priority=105,
            allowed_mode="operator_gated",
            reason_codes=(
                ["synthesis_gate_blocked", str(synthesis_gate or "missing")]
                if synthesis_blocked
                else ["synthesis_gate_allows_sandbox_review"]
            ),
            expected_outputs=["operator approval for sandbox synthesis"],
            max_scope="Approve sandbox-only generated strategy research.",
            stop_conditions=[
                "synthesis gate is blocked",
                "approval is absent",
                "generated strategy would overwrite production strategy code",
            ],
        ),
    ]
    return actions


def _forbidden_actions() -> list[dict[str, Any]]:
    expected = {
        "paper_trading": "no paper trading activation",
        "shadow_trading": "no shadow trading activation",
        "live_trading": "no live trading activation",
        "broker_changes": "no broker behavior changes",
        "risk_changes": "no risk behavior changes",
        "execution_changes": "no execution behavior changes",
        "direct_strategy_deployment": "no direct deployment of research strategies",
        "production_strategy_overwrite": "no overwrite of production strategies",
        "strategy_synthesis_outside_research_sandbox": (
            "no synthesis outside research/sandbox"
        ),
    }
    return [
        _action(
            action_id=action_id,
            action_type="forbidden_scope",
            priority=200 + index,
            allowed_mode="forbidden",
            reason_codes=["hard_governance_denial"],
            expected_outputs=[expected[action_id]],
            max_scope="Not allowed in this queue.",
            stop_conditions=["requested by any automated action"],
        )
        for index, action_id in enumerate(FORBIDDEN_ACTION_IDS)
    ]


def _synthesis_status(state: dict[str, Any]) -> dict[str, Any]:
    gate = state.get("synthesis_gate")
    blocked = gate in SYNTHESIS_BLOCKED_STATES or not gate
    return {
        "gate": gate,
        "eligible": not blocked,
        "automatic_allowed": False,
        "operator_approval_required": True,
        "status": "blocked" if blocked else "operator_gated_sandbox_review",
        "reason_codes": (
            ["synthesis_gate_blocked", str(gate or "missing")]
            if blocked
            else ["synthesis_gate_allows_sandbox_review"]
        ),
    }


def _blind_rerun_rationale(state: dict[str, Any]) -> str:
    if (
        state.get("policy_state") == "blocked_no_candidates"
        and _active_campaign_count(state) == 0
    ):
        return (
            "Blind rerun is not appropriate as the top action because the latest "
            "state is policy blocked with zero active campaigns; policy filter "
            "diagnostics must explain why no candidates are eligible first."
        )
    return (
        "Blind rerun is not preferred until diagnostics and bounded evaluation "
        "preflight confirm the next campaign can produce campaign-level evidence."
    )


def build_action_plan_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    state = artifacts.get("research_state")
    if not isinstance(state, dict):
        state = {
            "hypothesis_state": "unknown",
            "preset_state": "unknown",
            "policy_state": "unknown",
            "evidence_quality": {"state": "unknown"},
            "failure_attribution": {"state": "unknown", "attributed": False},
            "instrumentation_states": ["missing_research_state"],
            "synthesis_gate": "not_allowed_yet",
            "next_best_test": "inspect_gate_diagnostics",
            "campaign_summary": {"active_campaign_count": 0},
        }

    automatic = _automatic_actions(
        state=state,
        artifacts=artifacts,
        artifact_status=artifact_status,
    )
    operator_gated = _operator_gated_actions(state)
    forbidden = _forbidden_actions()
    ordered = sorted(
        [*automatic, *operator_gated, *forbidden],
        key=lambda item: (item["priority"], item["action_id"]),
    )
    next_best = automatic[0] if automatic else operator_gated[0]
    summary = _state_summary(state=state, artifact_status=artifact_status)
    policy_first = next_best["action_id"] == "inspect_campaign_policy_filters"
    screening_first = next_best["action_id"] == "explain_screening_drop_reasons"
    controlled_actions = [
        action for action in automatic if action["action_id"] == "controlled_eval_bounded"
    ]
    disposable_actions = [
        action for action in automatic if action["action_id"] == "disposable_workspace_eval"
    ]
    candidate_exists = _has_candidate_signal(artifacts, state)

    rationale = [
        f"Top action is {next_best['action_id']} because "
        f"{', '.join(next_best['reason_codes'])}.",
        _blind_rerun_rationale(state),
    ]
    if summary.get("evidence_quality") in {"insufficient_data", "policy_only", "unknown"}:
        rationale.append("Evidence quality is insufficient, so diagnostics precede synthesis.")
    if state.get("synthesis_gate") in SYNTHESIS_BLOCKED_STATES:
        rationale.append(
            f"Synthesis is blocked by gate {state.get('synthesis_gate')} and is not automatic."
        )

    return {
        "schema_version": RESEARCH_ACTION_PLAN_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "source_state_path": artifact_status["research_state"]["path"],
        "artifact_inputs": artifact_status,
        "state_summary": {
            **summary,
            "policy_filter_diagnostics_first": policy_first,
            "screening_drop_reason_diagnostics_first": screening_first,
            "next_best_controlled_eval": (
                {
                    "allowed": True,
                    "action_id": "controlled_eval_bounded",
                    "priority": controlled_actions[0]["priority"],
                }
                if controlled_actions
                else {"allowed": False, "reason": "diagnostic_or_policy_block_first"}
            ),
            "disposable_workspace_evaluation_preferred": bool(disposable_actions),
        },
        "ordered_actions": ordered,
        "automatic_actions": automatic,
        "operator_gated_actions": operator_gated,
        "forbidden_actions": forbidden,
        "next_best_action": next_best,
        "rationale": rationale,
        "synthesis_status": _synthesis_status(state),
        "candidate_alert_status": {
            "candidate_exists": candidate_exists,
            "recommended": candidate_exists,
            "automatic_allowed": candidate_exists,
        },
        "daily_report_recommendation": {
            "recommended": True,
            "action_id": "generate_daily_research_report",
            "reason_codes": ["operator_visibility"],
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload.get("state_summary") or {}
    next_action = payload.get("next_best_action") or {}
    synthesis = payload.get("synthesis_status") or {}
    lines = [
        "# Research Action Plan",
        "",
        "## Current State",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Source state path: `{payload.get('source_state_path')}`",
        f"- Hypothesis state: `{summary.get('hypothesis_state')}`",
        f"- Preset state: `{summary.get('preset_state')}`",
        f"- Policy state: `{summary.get('policy_state')}`",
        f"- Evidence quality: `{summary.get('evidence_quality')}`",
        f"- Failure attribution: `{summary.get('failure_attribution')}`",
        f"- Active campaigns: {summary.get('active_campaign_count')}",
        "",
        "## Top Recommended Action",
        f"- Action: `{next_action.get('action_id')}`",
        f"- Mode: `{next_action.get('allowed_mode')}`",
        f"- Reason codes: {', '.join(next_action.get('reason_codes') or []) or 'none'}",
        "",
        "## Blind Rerun",
        f"- {payload.get('rationale', [''])[1]}",
        "",
        "## Synthesis Status",
        f"- Gate: `{synthesis.get('gate')}`",
        f"- Status: `{synthesis.get('status')}`",
        f"- Automatic allowed: {synthesis.get('automatic_allowed')}",
        f"- Operator approval required: {synthesis.get('operator_approval_required')}",
        "",
        "## Automatic Actions",
        *[
            f"- `{action['action_id']}` (priority {action['priority']}): "
            f"{', '.join(action['reason_codes'])}"
            for action in payload.get("automatic_actions") or []
        ],
        "",
        "## Operator-Gated Actions",
        *[
            f"- `{action['action_id']}`: {', '.join(action['reason_codes'])}"
            for action in payload.get("operator_gated_actions") or []
        ],
        "",
        "## Forbidden Actions",
        *[
            f"- `{action['action_id']}`"
            for action in payload.get("forbidden_actions") or []
        ],
        "",
        "## What To Expect Next",
        (
            "- The next run should execute only the top bounded diagnostic unless "
            "it reaches an operator gate or exposes a governance blocker."
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
    payload = build_action_plan_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.research_action_plan",
        description="Build a bounded research action plan from current state sidecars.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read known current QRE artifacts and write research action-plan sidecars.",
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
        "research_action_plan: "
        f"next={payload['next_best_action']['action_id']} "
        f"synthesis={payload['synthesis_status']['status']} "
        f"automatic={len(payload['automatic_actions'])}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ARTIFACT_PATHS",
    "AUTOMATIC_ACTION_IDS",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "FORBIDDEN_ACTION_IDS",
    "OPERATOR_GATED_ACTION_IDS",
    "RESEARCH_ACTION_PLAN_SCHEMA_VERSION",
    "build_action_plan_payload",
    "build_from_current_artifacts",
    "load_current_artifacts",
    "main",
    "render_markdown_report",
]
