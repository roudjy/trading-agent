from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research import qre_preregistered_multiwindow_evidence_run as multiwindow
from research import qre_sampling_plan as sampling

DEFAULT_CAMPAIGN_PLAN_PATH: Final[Path] = Path(
    "research/campaign_preregistered_sampling_plan_latest.v1.json"
)
DEFAULT_APPROVAL_PATH: Final[Path] = multiwindow.DEFAULT_APPROVAL_PATH


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path.as_posix()}")
    return payload


def _proposal_scope(proposal: Mapping[str, Any]) -> dict[str, Any]:
    scope = proposal.get("campaign_scope")
    return dict(scope) if isinstance(scope, Mapping) else {}


def validate_proposal_approval_binding(
    *,
    proposal: Mapping[str, Any],
    approval_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact operator approval binding for a campaign proposal."""
    if _text(proposal.get("proposal_status")) != "proposal_ready_coverage_required":
        raise ValueError("campaign_sampling_proposal_not_coverage_ready")
    authority = proposal.get("authority")
    authority = authority if isinstance(authority, Mapping) else {}
    if (
        _text(authority.get("action_authority")) != "report_only"
        or authority.get("approval_required_before_execution") is not True
    ):
        raise ValueError("invalid_campaign_sampling_proposal_authority")
    safety = proposal.get("safety_invariants")
    safety = safety if isinstance(safety, Mapping) else {}
    if not safety or any(value is not False for value in safety.values()):
        raise ValueError("unsafe_campaign_sampling_proposal")

    scope = _proposal_scope(proposal)
    approval_scope = approval_manifest.get("scope")
    approval_scope = (
        dict(approval_scope) if isinstance(approval_scope, Mapping) else {}
    )
    expected = {
        "campaign_id": _text(scope.get("campaign_id")),
        "proposal_id": _text(proposal.get("proposal_id")),
        "proposal_hash": _text(proposal.get("hash")),
        "preset_id": _text(scope.get("preset_name")),
        "timeframe": _text(scope.get("timeframe")),
    }
    for field, expected_value in expected.items():
        if not expected_value or _text(approval_scope.get(field)) != expected_value:
            raise ValueError(f"campaign_proposal_approval_scope_mismatch:{field}")

    expected_symbols = sorted(
        {_text(value).upper() for value in scope.get("universe") or [] if _text(value)}
    )
    approved_symbols = sorted(
        {
            _text(value).upper()
            for value in approval_scope.get("symbols") or []
            if _text(value)
        }
    )
    if not expected_symbols or approved_symbols != expected_symbols:
        raise ValueError("campaign_proposal_approval_scope_mismatch:symbols")
    if bool(approval_manifest.get("external_fetch_allowed", False)):
        raise ValueError("campaign_proposal_external_fetch_not_allowed")
    return scope


def materialize_campaign_sampling_plan(
    *,
    proposal: Mapping[str, Any],
    approval_manifest: Mapping[str, Any],
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Derive locked windows from local cache without changing research scope."""
    scope = validate_proposal_approval_binding(
        proposal=proposal,
        approval_manifest=approval_manifest,
    )
    coverage = proposal.get("coverage_requirements")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    source_plan = proposal.get("sampling_plan")
    source_plan = source_plan if isinstance(source_plan, Mapping) else {}
    if sampling.validate_sampling_plan(source_plan).get("valid") is not True:
        raise ValueError("invalid_campaign_sampling_plan_contract")

    symbols = sorted(
        {_text(value).upper() for value in scope.get("universe") or [] if _text(value)}
    )
    timeframe = _text(scope.get("timeframe"))
    common_dates = multiwindow._load_common_trading_dates(
        repo_root,
        symbols=symbols,
        timeframe=timeframe,
    )
    window_count = int(coverage.get("window_count") or 0)
    minimum_window_length = int(coverage.get("minimum_window_length") or 0)
    minimum_warmup_period = int(coverage.get("minimum_warmup_period") or 0)
    minimum_dates = int(coverage.get("minimum_common_trading_dates") or 0)
    if len(common_dates) < minimum_dates:
        raise ValueError("insufficient_common_local_trading_dates")

    windows = sampling.derive_preregistered_windows(
        trading_dates=common_dates,
        window_count=window_count,
        minimum_window_length=minimum_window_length,
        minimum_warmup_period=minimum_warmup_period,
    )
    approval_scope = approval_manifest.get("scope")
    approval_scope = approval_scope if isinstance(approval_scope, Mapping) else {}
    plan = sampling.build_preregistered_sampling_plan(
        hypothesis_ref=_text(source_plan.get("hypothesis_ref")),
        behavior_id=_text(source_plan.get("behavior_id")),
        preset_id=_text(source_plan.get("preset_id")),
        timeframe=timeframe,
        bounded_source_data_availability={
            "status": "materialized_from_local_cache",
            "local_only": True,
            "source_data_ref": _text(approval_scope.get("source_data_ref")),
            "symbols": symbols,
            "common_trading_date_count": len(common_dates),
            "timeframe": timeframe,
        },
        proposed_total_validation_range={
            "status": "materialized",
            "start": common_dates[0],
            "end": common_dates[-1],
            "common_trading_date_count": len(common_dates),
            "window_count": window_count,
        },
        minimum_window_length=minimum_window_length,
        minimum_warmup_period=minimum_warmup_period,
        required_oos_evidence_types=list(
            source_plan.get("required_oos_evidence_types") or []
        ),
        null_control_definitions=list(
            source_plan.get("null_control_definitions") or []
        ),
        known_previous_failed_windows=list(
            source_plan.get("known_previous_failed_windows") or []
        ),
        regime_buckets=list(source_plan.get("regime_buckets") or []),
        window_definitions=windows,
        preregistration_timestamp=_text(
            source_plan.get("preregistration_timestamp")
        ),
        minimum_trade_requirement=int(
            source_plan.get("minimum_trade_requirement") or 1
        ),
        selection_policy=_text(source_plan.get("selection_policy")),
        forbidden_adaptations=list(
            source_plan.get("forbidden_adaptations") or []
        ),
    )
    validation = sampling.validate_sampling_plan(plan)
    if validation.get("valid") is not True:
        raise ValueError("materialized_sampling_plan_contract_invalid")
    if _text(plan.get("status")) != "sampling_plan_ready_context_only":
        raise ValueError("materialized_sampling_plan_not_ready")
    return plan


def build_campaign_preregistered_multiwindow_evidence_run(
    *,
    proposal: Mapping[str, Any],
    approval_manifest: Mapping[str, Any],
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Execute only the locked plan derived from the approved proposal."""
    scope = validate_proposal_approval_binding(
        proposal=proposal,
        approval_manifest=approval_manifest,
    )
    plan = materialize_campaign_sampling_plan(
        proposal=proposal,
        approval_manifest=approval_manifest,
        repo_root=repo_root,
    )
    return multiwindow.build_preregistered_multiwindow_evidence_run(
        approval_manifest=approval_manifest,
        repo_root=repo_root,
        sampling_plan_payload=plan,
        campaign_scope=scope,
        proposal_id=_text(proposal.get("proposal_id")),
        proposal_hash=_text(proposal.get("hash")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.campaign_preregistered_multiwindow_evidence_run",
        description="Execute an operator-approved campaign sampling proposal.",
    )
    parser.add_argument(
        "--campaign-plan-file",
        default=DEFAULT_CAMPAIGN_PLAN_PATH.as_posix(),
    )
    parser.add_argument(
        "--approval-file",
        default=DEFAULT_APPROVAL_PATH.as_posix(),
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_campaign_preregistered_multiwindow_evidence_run(
        proposal=_read_json(Path(args.campaign_plan_file)),
        approval_manifest=_read_json(Path(args.approval_file)),
    )
    if args.write:
        report["_artifact_paths"] = multiwindow.write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
