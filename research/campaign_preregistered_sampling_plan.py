from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_sampling_plan as sampling

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "campaign_preregistered_sampling_plan"
DECISION_PATH: Final[Path] = Path(
    "research/campaign_evidence_decision_latest.v1.json"
)
DEFAULT_JSON_OUTPUT_PATH: Final[Path] = Path(
    "research/campaign_preregistered_sampling_plan_latest.v1.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH: Final[Path] = Path(
    "research/campaign_preregistered_sampling_plan_latest.md"
)
REQUIRED_RECOMMENDATION: Final[str] = "create_preregistered_sampling_plan"
REQUIRED_ACTION_AUTHORITY: Final[str] = "report_only"
SAFETY_KEYS: Final[tuple[str, ...]] = (
    "can_execute",
    "can_spawn_campaigns",
    "can_mutate_queue",
    "can_change_policy",
    "can_change_presets",
    "can_change_strategy",
    "can_access_paper_shadow_live",
)
REQUIRED_SCOPE_FIELDS: Final[tuple[str, ...]] = (
    "campaign_id",
    "hypothesis_id",
    "preset_name",
    "timeframe",
    "template_id",
    "strategy_family",
    "asset_class",
)
FAILURE_POLICIES: Final[dict[str, dict[str, Any]]] = {
    "insufficient_window_length": {
        "window_count": 2,
        "minimum_window_length": 20,
        "minimum_warmup_period": 10,
        "minimum_trade_requirement": 1,
        "required_oos_evidence_types": [
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "null_control_definitions": [
            {
                "control_id": "null_preregistered_holdout",
                "control_kind": "holdout",
                "required_for_evidence_complete": True,
                "required_for_fail_closed_rejection": False,
            }
        ],
    }
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _read_json(path: Path) -> tuple[str, dict[str, Any] | None]:
    if not path.exists():
        return "missing", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "malformed", None
    if not isinstance(payload, dict):
        return "malformed", None
    return "present", payload


def _report_hash(report: Mapping[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in report.items()
        if key not in {"hash", "proposal_id", "_artifact_paths"}
    }
    blob = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    digest = _report_hash(report)
    report["proposal_id"] = f"cpsp_{digest[:16]}"
    report["hash"] = _report_hash(report)
    return report


def _base_report(
    *,
    decision: Mapping[str, Any] | None,
    preregistration_timestamp: str,
    decision_input_status: str,
) -> dict[str, Any]:
    payload = decision if isinstance(decision, Mapping) else {}
    scope = payload.get("campaign_scope")
    scope = dict(scope) if isinstance(scope, Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "proposal_status": "blocked_malformed_decision",
        "blocked_reasons": [],
        "campaign_scope": scope,
        "decision_trigger": {
            "decision_status": _text(payload.get("decision_status")),
            "recommended_action": _text(payload.get("recommended_action")),
            "action_authority": _text(payload.get("action_authority")),
            "failure_class": _text(payload.get("failure_class")),
            "reason_codes": _unique_in_order(payload.get("reason_codes") or []),
            "prerequisites": _unique_in_order(payload.get("prerequisites") or []),
        },
        "preregistration_timestamp": _text(preregistration_timestamp),
        "coverage_requirements": {},
        "sampling_plan": {},
        "sampling_plan_validation": {},
        "provenance": {
            "decision_ref": DECISION_PATH.as_posix(),
            "selected_source": _text(payload.get("selected_source")),
            "evidence_refs": _unique_in_order(payload.get("evidence_refs") or []),
        },
        "artifact_inputs": {
            "campaign_evidence_decision": {
                "path": DECISION_PATH.as_posix(),
                "status": decision_input_status,
            }
        },
        "authority": {
            "action_authority": REQUIRED_ACTION_AUTHORITY,
            "approval_required_before_execution": True,
            "evidence_authority": "context_only",
        },
        "safety_invariants": {key: False for key in SAFETY_KEYS},
    }


def build_campaign_preregistered_sampling_plan(
    *,
    decision: Mapping[str, Any] | None,
    preregistration_timestamp: str,
    decision_input_status: str = "present",
) -> dict[str, Any]:
    report = _base_report(
        decision=decision,
        preregistration_timestamp=preregistration_timestamp,
        decision_input_status=decision_input_status,
    )
    if decision_input_status != "present":
        report["proposal_status"] = f"blocked_{decision_input_status}_decision"
        report["blocked_reasons"] = [
            f"campaign_evidence_decision_{decision_input_status}"
        ]
        return _finalize(report)
    if not isinstance(decision, Mapping):
        report["proposal_status"] = "blocked_malformed_decision"
        report["blocked_reasons"] = ["campaign_evidence_decision_malformed"]
        return _finalize(report)

    trigger = report["decision_trigger"]
    if (
        trigger["decision_status"] != "decision_ready"
        or trigger["recommended_action"] != REQUIRED_RECOMMENDATION
        or trigger["action_authority"] != REQUIRED_ACTION_AUTHORITY
    ):
        report["proposal_status"] = "blocked_unsupported_decision"
        report["blocked_reasons"] = ["decision_not_sampling_plan_eligible"]
        return _finalize(report)

    input_safety = decision.get("safety_invariants")
    input_safety = input_safety if isinstance(input_safety, Mapping) else {}
    unsafe_keys = [key for key in SAFETY_KEYS if input_safety.get(key) is not False]
    if unsafe_keys:
        report["proposal_status"] = "blocked_unsafe_decision_authority"
        report["blocked_reasons"] = [
            f"decision_safety_invariant_not_false:{key}" for key in unsafe_keys
        ]
        return _finalize(report)

    scope = report["campaign_scope"]
    missing_scope = [field for field in REQUIRED_SCOPE_FIELDS if not _text(scope.get(field))]
    if scope.get("registry_record_present") is not True:
        missing_scope.append("registry_record_present")
    universe = scope.get("universe")
    if not isinstance(universe, list) or not _unique_in_order(universe):
        missing_scope.append("universe")
    if missing_scope:
        report["proposal_status"] = "blocked_incomplete_campaign_scope"
        report["blocked_reasons"] = [
            f"missing_campaign_scope:{field}" for field in _unique_in_order(missing_scope)
        ]
        return _finalize(report)

    if not _text(preregistration_timestamp):
        report["proposal_status"] = "blocked_missing_preregistration_timestamp"
        report["blocked_reasons"] = ["missing_preregistration_timestamp"]
        return _finalize(report)

    failure_class = trigger["failure_class"]
    policy = FAILURE_POLICIES.get(failure_class)
    if policy is None:
        report["proposal_status"] = "blocked_unsupported_failure_class"
        report["blocked_reasons"] = [f"unsupported_failure_class:{failure_class}"]
        return _finalize(report)

    window_count = int(policy["window_count"])
    minimum_window_length = int(policy["minimum_window_length"])
    minimum_warmup_period = int(policy["minimum_warmup_period"])
    universe = _unique_in_order(universe)
    report["campaign_scope"]["universe"] = sorted(universe)
    report["coverage_requirements"] = {
        "local_only": True,
        "window_count": window_count,
        "minimum_window_length": minimum_window_length,
        "minimum_warmup_period": minimum_warmup_period,
        "minimum_common_trading_dates": window_count * minimum_window_length,
        "window_derivation_policy": "deterministic_non_overlapping_partition",
        "regime_assignment_policy": "unclassified_unless_explicitly_preregistered",
        "required_oos_evidence_types": list(policy["required_oos_evidence_types"]),
    }
    plan = sampling.build_preregistered_sampling_plan(
        hypothesis_ref=_text(scope.get("hypothesis_id")),
        behavior_id=_text(scope.get("strategy_family")),
        preset_id=_text(scope.get("preset_name")),
        timeframe=_text(scope.get("timeframe")),
        bounded_source_data_availability={
            "status": "not_materialized",
            "local_only": True,
            "symbols": sorted(universe),
            "timeframe": _text(scope.get("timeframe")),
        },
        proposed_total_validation_range={
            "status": "coverage_required",
            "minimum_common_trading_dates": window_count * minimum_window_length,
            "window_count": window_count,
        },
        minimum_window_length=minimum_window_length,
        minimum_warmup_period=minimum_warmup_period,
        required_oos_evidence_types=policy["required_oos_evidence_types"],
        null_control_definitions=policy["null_control_definitions"],
        window_count=window_count,
        preregistration_timestamp=_text(preregistration_timestamp),
        minimum_trade_requirement=int(policy["minimum_trade_requirement"]),
    )
    validation = sampling.validate_sampling_plan(plan)
    report["sampling_plan"] = plan
    report["sampling_plan_validation"] = validation
    if validation.get("valid") is not True:
        report["proposal_status"] = "blocked_invalid_sampling_plan_contract"
        report["blocked_reasons"] = list(validation.get("rejection_reasons") or [])
        return _finalize(report)

    report["proposal_status"] = "proposal_ready_coverage_required"
    report["blocked_reasons"] = []
    return _finalize(report)


def build_from_current_decision(
    *,
    preregistration_timestamp: str,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    status, decision = _read_json(repo_root / DECISION_PATH)
    return build_campaign_preregistered_sampling_plan(
        decision=decision,
        preregistration_timestamp=preregistration_timestamp,
        decision_input_status=status,
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    scope = report.get("campaign_scope")
    scope = scope if isinstance(scope, Mapping) else {}
    coverage = report.get("coverage_requirements")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    safety = report.get("safety_invariants")
    safety = safety if isinstance(safety, Mapping) else {}
    lines = [
        "# Campaign Preregistered Sampling Plan",
        "",
        f"- proposal_status: {report.get('proposal_status', '')}",
        f"- proposal_id: {report.get('proposal_id', '')}",
        f"- campaign_id: {scope.get('campaign_id', '')}",
        f"- hypothesis_id: {scope.get('hypothesis_id', '')}",
        f"- preset_name: {scope.get('preset_name', '')}",
        f"- timeframe: {scope.get('timeframe', '')}",
        f"- window_count: {coverage.get('window_count', '')}",
        f"- minimum_common_trading_dates: {coverage.get('minimum_common_trading_dates', '')}",
        f"- action_authority: {(report.get('authority') or {}).get('action_authority', '')}",
        f"- can_execute: {safety.get('can_execute', False)}",
        "",
        "## Blocked reasons",
        "",
    ]
    reasons = list(report.get("blocked_reasons") or [])
    lines.extend(f"- {reason}" for reason in reasons)
    if not reasons:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path, *, repo_root: Path) -> None:
    allowed = {
        (repo_root / DEFAULT_JSON_OUTPUT_PATH).resolve(),
        (repo_root / DEFAULT_MARKDOWN_OUTPUT_PATH).resolve(),
    }
    if path.resolve() not in allowed:
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    json_path = repo_root / DEFAULT_JSON_OUTPUT_PATH
    markdown_path = repo_root / DEFAULT_MARKDOWN_OUTPUT_PATH
    for target in (json_path, markdown_path):
        _validate_write_target(target, repo_root=repo_root)
    _atomic_write_text(
        json_path,
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(markdown_path, render_markdown(report))
    return {
        "json": DEFAULT_JSON_OUTPUT_PATH.as_posix(),
        "markdown": DEFAULT_MARKDOWN_OUTPUT_PATH.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.campaign_preregistered_sampling_plan",
        description="Build a report-only campaign-scoped sampling-plan proposal.",
    )
    parser.add_argument("--from-current-decision", action="store_true", required=True)
    parser.add_argument("--preregistered-at", required=True)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    report = build_from_current_decision(
        preregistration_timestamp=args.preregistered_at,
    )
    if not args.no_write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
