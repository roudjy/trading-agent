"""Strategy synthesis eligibility gate sidecar.

This module decides whether sandbox strategy synthesis is eligible for
review from existing research artifacts only. It never generates strategy
code, runs research, or changes trading lanes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

SYNTHESIS_GATE_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path(
    "research/synthesis_gate_latest.v1.json"
)
DEFAULT_REPORT_MD_PATH: Final[Path] = Path("research/synthesis_gate_latest.md")

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "research_state": Path("research/research_state_latest.v1.json"),
    "research_action_plan": Path("research/research_action_plan_latest.v1.json"),
    "policy_filter_diagnostics": Path(
        "research/policy_filter_diagnostics_latest.v1.json"
    ),
    "screening_failure_attribution": Path(
        "research/screening_failure_attribution_latest.v1.json"
    ),
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
}

GATE_STATES: Final[tuple[str, ...]] = (
    "blocked_insufficient_attribution",
    "blocked_policy_only_failure",
    "blocked_evaluability_primary",
    "blocked_missing_market_context",
    "blocked_no_preset_space_exhaustion",
    "operator_review_required",
    "allowed_for_sandbox_review",
)

DISALLOWED_PATHS: Final[tuple[str, ...]] = (
    "paper/**",
    "shadow/**",
    "live/**",
    "risk/**",
    "broker/**",
    "execution/**",
    "agent/backtesting/strategies.py",
    "registry.py",
)
ALLOWED_SANDBOX_PATHS: Final[tuple[str, ...]] = ("research/sandbox/**",)

MARKET_CONTEXT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "market_context",
        "market_context_insight",
        "market_context_insights",
        "market_regime_insight",
        "supporting_market_insight",
        "linked_market_insight",
    }
)
HYPOTHESIS_KEYS: Final[frozenset[str]] = frozenset(
    {"hypothesis", "hypothesis_id", "hypothesis_state", "hypothesis_summary"}
)
EVALUABILITY_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {
        "data_coverage_gap",
        "no_oos_returns",
        "insufficient_trades",
        "missing_diagnostics",
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "no", "none", "unknown"}
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def _find_key_evidence(
    value: Any,
    keys: frozenset[str],
    *,
    source: str,
    prefix: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    stack: list[tuple[Any, str]] = [(value, prefix)]
    while stack and len(evidence) < limit:
        item, path = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                key_l = str(key).lower()
                if key_l in keys and _truthy(child):
                    evidence.append(
                        {
                            "source": source,
                            "path": child_path,
                            "value": (
                                child
                                if isinstance(child, (str, int, float, bool))
                                else True
                            ),
                        }
                    )
                stack.append((child, child_path))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                stack.append((child, f"{path}[{index}]"))
    return evidence


def _all_key_evidence(
    artifacts: dict[str, Any],
    keys: frozenset[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for source, payload in artifacts.items():
        evidence.extend(_find_key_evidence(payload, keys, source=source))
    return evidence


def _policy_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    policy = _dict_value(artifacts.get("policy_decision"))
    controlled = _dict_value(artifacts.get("controlled_eval"))
    research_state = _dict_value(artifacts.get("research_state"))
    state_policy = _dict_value(research_state.get("policy_summary"))
    decision = _dict_value(policy.get("decision"))
    candidates = policy.get("candidates_considered")
    candidate_count = len(candidates) if isinstance(candidates, list) else None
    if candidate_count is None:
        candidate_count = state_policy.get(
            "candidates_considered",
            controlled.get("latest_policy_candidates_considered_count"),
        )
    return {
        "action": decision.get("action")
        or state_policy.get("action")
        or controlled.get("latest_policy_action"),
        "reason": decision.get("reason")
        or state_policy.get("reason")
        or controlled.get("latest_policy_reason"),
        "candidates_considered": _safe_int(candidate_count),
        "policy_state": research_state.get("policy_state"),
        "evidence_quality": _dict_value(research_state.get("evidence_quality")).get(
            "state"
        ),
    }


def _latest_evidence_is_no_candidates(policy: dict[str, Any]) -> bool:
    return (
        policy.get("action") == "idle_noop"
        and policy.get("reason") == "no_candidates"
        and _safe_int(policy.get("candidates_considered")) == 0
    ) or policy.get("policy_state") == "blocked_no_candidates" or policy.get(
        "evidence_quality"
    ) == "policy_only"


def _campaign_records(registry: dict[str, Any]) -> list[dict[str, Any]]:
    campaigns = registry.get("campaigns")
    if not isinstance(campaigns, dict):
        return []
    return [record for record in campaigns.values() if isinstance(record, dict)]


def _prior_campaign_evidence(artifacts: dict[str, Any]) -> dict[str, Any]:
    registry_records = _campaign_records(_dict_value(artifacts.get("campaign_registry")))
    terminal_records = [
        record
        for record in registry_records
        if record.get("state") in {"completed", "failed", "archived"}
        or record.get("outcome")
    ]
    ledger_events = [
        event
        for event in _list_value(artifacts.get("campaign_evidence_ledger"))
        if isinstance(event, dict)
        and (
            event.get("event_type") in {"campaign_completed", "campaign_failed"}
            or event.get("outcome")
        )
    ]
    controlled = _dict_value(artifacts.get("controlled_eval"))
    controlled_outcomes = _dict_value(controlled.get("campaigns_by_outcome"))
    research_state = _dict_value(artifacts.get("research_state"))
    campaign_summary = _dict_value(research_state.get("campaign_summary"))
    state_outcomes = _dict_value(campaign_summary.get("outcome_counts"))
    evidence_count = (
        len(terminal_records)
        + len(ledger_events)
        + sum(_safe_int(v) for v in controlled_outcomes.values())
        + sum(_safe_int(v) for v in state_outcomes.values())
    )
    return {
        "present": evidence_count > 0,
        "evidence_count": evidence_count,
        "registry_terminal_records": len(terminal_records),
        "ledger_terminal_events": len(ledger_events),
        "controlled_outcomes": controlled_outcomes,
        "research_state_outcomes": state_outcomes,
    }


def _failure_attribution(artifacts: dict[str, Any]) -> dict[str, Any]:
    research_state = _dict_value(artifacts.get("research_state"))
    state_attr = _dict_value(research_state.get("failure_attribution"))
    screening = _dict_value(artifacts.get("screening_failure_attribution"))
    screening_summary = _dict_value(screening.get("summary"))
    primary = (
        state_attr.get("primary_blocker")
        or screening_summary.get("primary_classification")
    )
    attributed = state_attr.get("attributed")
    if attributed is None:
        attributed = screening_summary.get("attributed")
    return {
        "present": bool(state_attr) or bool(screening_summary),
        "state": state_attr.get("state"),
        "primary": primary,
        "attributed": bool(attributed) if attributed is not None else False,
        "screening_primary_classification": screening_summary.get(
            "primary_classification"
        ),
        "screening_attributed": screening_summary.get("attributed"),
    }


def _screening_failure_unattributed(attribution: dict[str, Any]) -> bool:
    state = str(attribution.get("state") or "")
    primary = str(attribution.get("primary") or "")
    screening_primary = str(attribution.get("screening_primary_classification") or "")
    if attribution.get("attributed") is True:
        return False
    return (
        "unattributed" in state
        or primary in {"screening_or_evaluability", "validation_or_promotion_gate"}
        or screening_primary in {"missing_diagnostics", "unknown_screening_failure"}
        or attribution.get("screening_attributed") is False
    )


def _evaluability_primary(artifacts: dict[str, Any], attribution: dict[str, Any]) -> bool:
    research_state = _dict_value(artifacts.get("research_state"))
    evidence_state = _dict_value(research_state.get("evidence_quality")).get("state")
    screening_primary = str(attribution.get("screening_primary_classification") or "")
    return (
        research_state.get("synthesis_gate") == "blocked_evaluability_primary"
        or attribution.get("primary") == "screening_or_evaluability"
        or evidence_state == "screening_or_evaluability_failure"
        or screening_primary in EVALUABILITY_CLASSIFICATIONS
    )


def _preset_space_exhaustion(artifacts: dict[str, Any]) -> dict[str, Any]:
    explicit = _explicit_preset_space_exhaustion(artifacts)
    if explicit:
        return {"demonstrated": True, "mode": "explicit", "evidence": explicit}

    research_state = _dict_value(artifacts.get("research_state"))
    campaign_summary = _dict_value(research_state.get("campaign_summary"))
    preset_names = {
        str(name)
        for name in _list_value(campaign_summary.get("preset_names"))
        if str(name)
    }
    registry_records = _campaign_records(_dict_value(artifacts.get("campaign_registry")))
    for record in registry_records:
        preset = record.get("preset_name")
        if preset:
            preset_names.add(str(preset))
    outcome_counts = _dict_value(campaign_summary.get("outcome_counts"))
    completed_no_survivor_count = _safe_int(outcome_counts.get("completed_no_survivor"))
    for record in registry_records:
        if record.get("outcome") == "completed_no_survivor":
            completed_no_survivor_count += 1
    inferred = (
        research_state.get("preset_state")
        in {"completed_no_survivor", "preset_space_exhausted", "exhausted"}
        and len(preset_names) >= 2
        and completed_no_survivor_count >= 1
    )
    return {
        "demonstrated": inferred,
        "mode": "inferred_from_completed_no_survivor_presets" if inferred else "missing",
        "preset_count": len(preset_names),
        "completed_no_survivor_count": completed_no_survivor_count,
        "evidence": explicit,
    }


def _explicit_preset_space_exhaustion(
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    keys = {
        "preset_space_exhausted",
        "preset_space_exhaustion_demonstrated",
        "preset_space_exhaustion",
    }
    evidence: list[dict[str, Any]] = []
    for source, payload in artifacts.items():
        stack: list[tuple[Any, str]] = [(payload, "")]
        while stack and len(evidence) < 10:
            item, path = stack.pop()
            if isinstance(item, dict):
                for key, child in item.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    key_l = str(key).lower()
                    if key_l in keys and _preset_exhaustion_value_is_true(child):
                        evidence.append(
                            {
                                "source": source,
                                "path": child_path,
                                "value": _summarize_evidence_value(child),
                            }
                        )
                    stack.append((child, child_path))
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    stack.append((child, f"{path}[{index}]"))
    return evidence


def _preset_exhaustion_value_is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "exhausted", "demonstrated"}
    if isinstance(value, dict):
        for key in ("demonstrated", "exhausted"):
            if value.get(key) is True:
                return True
        status = str(value.get("status") or value.get("state") or "").lower()
        return status in {"exhausted", "demonstrated"}
    return False


def _summarize_evidence_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            key: child
            for key, child in value.items()
            if key in {"demonstrated", "exhausted", "status", "state"}
        } or True
    return True


def _operator_review_requested(artifacts: dict[str, Any]) -> bool:
    review = _all_key_evidence(
        artifacts,
        frozenset({"operator_review_required", "requires_operator_review"}),
    )
    return any(item.get("value") is True for item in review)


def _reasoned_state(
    *,
    policy_only: bool,
    unattributed: bool,
    evaluability_primary: bool,
    has_market_context: bool,
    preset_exhausted: bool,
    residual_missing: list[str],
    operator_review_requested: bool,
) -> tuple[str, bool, bool, list[str], list[str], list[str]]:
    reason_codes: list[str] = []
    missing: list[str] = []
    next_actions: list[str] = []

    if policy_only:
        return (
            "blocked_policy_only_failure",
            False,
            False,
            ["policy_only_idle_noop_no_candidates"],
            ["campaign_or_policy_filter_evidence_beyond_no_candidates"],
            ["run_policy_filter_diagnostics"],
        )
    if unattributed:
        return (
            "blocked_insufficient_attribution",
            False,
            False,
            ["screening_or_gate_failure_unattributed"],
            ["screening_failure_attribution"],
            ["run_screening_failure_attribution"],
        )
    if evaluability_primary:
        return (
            "blocked_evaluability_primary",
            False,
            False,
            ["evaluability_or_data_coverage_primary_blocker"],
            ["evaluable_candidate_evidence"],
            ["repair_or_diagnose_evaluability_before_synthesis"],
        )
    if not has_market_context:
        return (
            "blocked_missing_market_context",
            False,
            False,
            ["missing_linked_market_context_insight"],
            ["linked_market_context_insight"],
            ["link_market_context_insight_to_hypothesis"],
        )
    if not preset_exhausted:
        return (
            "blocked_no_preset_space_exhaustion",
            False,
            False,
            ["preset_space_exhaustion_not_demonstrated"],
            ["preset_space_exhaustion_evidence"],
            ["run_preset_space_exhaustion_diagnostic"],
        )
    if residual_missing:
        reason_codes.extend(f"missing_{item}" for item in residual_missing)
        missing.extend(residual_missing)
        next_actions.append("operator_review_synthesis_evidence")
        return (
            "operator_review_required",
            False,
            True,
            reason_codes,
            missing,
            next_actions,
        )
    if operator_review_requested:
        return (
            "operator_review_required",
            False,
            True,
            ["operator_review_requested_by_artifact"],
            [],
            ["operator_review_synthesis_evidence"],
        )
    return (
        "allowed_for_sandbox_review",
        True,
        False,
        ["all_required_synthesis_evidence_present", "sandbox_scope_only"],
        [],
        ["review_sandbox_synthesis_inputs"],
    )


def build_synthesis_gate_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    policy = _policy_summary(artifacts)
    policy_only = _latest_evidence_is_no_candidates(policy)
    attribution = _failure_attribution(artifacts)
    unattributed = _screening_failure_unattributed(attribution)
    evaluability = _evaluability_primary(artifacts, attribution)
    market_context = _all_key_evidence(artifacts, MARKET_CONTEXT_KEYS)
    hypothesis = _all_key_evidence(artifacts, HYPOTHESIS_KEYS)
    prior_campaign = _prior_campaign_evidence(artifacts)
    preset_exhaustion = _preset_space_exhaustion(artifacts)

    residual_missing: list[str] = []
    if not hypothesis:
        residual_missing.append("hypothesis_state")
    if not prior_campaign["present"]:
        residual_missing.append("prior_campaign_evidence")
    if not attribution["present"] or not attribution["attributed"]:
        residual_missing.append("failure_attribution")
    if any(status["status"] == "malformed" for status in artifact_status.values()):
        residual_missing.append("well_formed_artifacts")

    (
        gate_state,
        allowed,
        operator_review_required,
        reason_codes,
        required_missing_evidence,
        next_actions,
    ) = _reasoned_state(
        policy_only=policy_only,
        unattributed=unattributed,
        evaluability_primary=evaluability,
        has_market_context=bool(market_context),
        preset_exhausted=bool(preset_exhaustion["demonstrated"]),
        residual_missing=residual_missing,
        operator_review_requested=_operator_review_requested(artifacts),
    )
    for missing_item in residual_missing:
        if missing_item not in required_missing_evidence:
            required_missing_evidence.append(missing_item)

    allowed_paths = list(ALLOWED_SANDBOX_PATHS) if allowed else []
    return {
        "schema_version": SYNTHESIS_GATE_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "synthesis_gate_state": gate_state,
        "allowed": allowed,
        "operator_review_required": operator_review_required,
        "reason_codes": reason_codes,
        "required_missing_evidence": required_missing_evidence,
        "supporting_evidence": {
            "policy": policy,
            "latest_evidence_is_no_candidates": policy_only,
            "failure_attribution": attribution,
            "evaluability_primary": evaluability,
            "market_context": market_context,
            "hypothesis": hypothesis,
            "prior_campaign_evidence": prior_campaign,
            "preset_space_exhaustion": preset_exhaustion,
            "artifact_inputs": artifact_status,
        },
        "disallowed_paths": list(DISALLOWED_PATHS),
        "allowed_paths": allowed_paths,
        "next_required_actions": next_actions,
        "safety_invariants": {
            "runs_research": False,
            "generates_strategy_code": False,
            "mutates_campaign_artifacts": False,
            "writes_only_synthesis_gate_sidecars": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "sandbox_paths_only_when_allowed": allowed_paths == list(ALLOWED_SANDBOX_PATHS)
            if allowed
            else True,
            "frozen_contracts_unchanged": True,
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    missing = payload.get("required_missing_evidence") or []
    reason_codes = payload.get("reason_codes") or []
    next_actions = payload.get("next_required_actions") or []
    allowed = bool(payload.get("allowed"))
    missing_lines = [f"- `{item}`" for item in missing] if missing else ["- none"]
    allowed_path_lines = [
        f"- `{path}`" for path in payload.get("allowed_paths") or ["none"]
    ]
    lines = [
        "# Strategy Synthesis Eligibility Gate",
        "",
        "## Summary",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Gate state: `{payload.get('synthesis_gate_state')}`",
        f"- Synthesis allowed: {allowed}",
        f"- Operator review required: {payload.get('operator_review_required')}",
        f"- Reason codes: {', '.join(reason_codes) or 'none'}",
        "",
        "## Missing Evidence",
        *missing_lines,
        "",
        "## Next Diagnostic",
        f"- {', '.join(f'`{item}`' for item in next_actions) or '`none`'}",
        "",
        "## Safety Scope",
        "- Paper, shadow, live, risk, broker, and execution paths remain forbidden.",
        (
            "- Generated strategy code, when eventually allowed, must stay inside "
            "`research/sandbox/**` paths only."
        ),
        "- This gate does not generate strategy code or enable trading lanes.",
        "",
        "## Allowed Paths",
        *allowed_path_lines,
        "",
        "## Disallowed Paths",
        *[f"- `{path}`" for path in payload.get("disallowed_paths") or []],
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
    payload = build_synthesis_gate_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.synthesis_gate",
        description="Evaluate sandbox strategy synthesis eligibility.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read current QRE sidecars and write synthesis gate reports.",
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
        "synthesis_gate: "
        f"state={payload['synthesis_gate_state']} "
        f"allowed={payload['allowed']} "
        f"operator_review={payload['operator_review_required']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ALLOWED_SANDBOX_PATHS",
    "ARTIFACT_PATHS",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "DISALLOWED_PATHS",
    "GATE_STATES",
    "SYNTHESIS_GATE_SCHEMA_VERSION",
    "build_from_current_artifacts",
    "build_synthesis_gate_payload",
    "load_current_artifacts",
    "main",
    "render_markdown_report",
]
