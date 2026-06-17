from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_first_batch_generation_decision as generation_decision
from research import qre_bounded_generation_artifact_acceptance_verifier as acceptance_verifier
from research import qre_evidence_complete_basket_closure as closure
from research import qre_first_batch_evidence_recovery_cascade as first_batch_cascade
from research import qre_guarded_preset_timeframe_alias_policy as alias_policy


REPORT_KIND: Final[str] = "qre_guarded_alias_bounded_generation_cascade"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_guarded_alias_bounded_generation_cascade")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_guarded_alias_bounded_generation_cascade/"
FIRST_BATCH_SYMBOLS: Final[tuple[str, ...]] = ("AAPL", "NVDA")
AUTHORITY_BOUNDARY: Final[dict[str, Any]] = {
    "read_only_report_only": True,
    "not_campaign_launcher": True,
    "not_campaign_queue_mutation": True,
    "not_campaign_registry_mutation": True,
    "not_run_campaign_mutation": True,
    "not_broad_research_run": True,
    "not_strategy_synthesis": True,
    "not_strategy_registration": True,
    "not_candidate_promotion": True,
    "not_routing_mutation": True,
    "not_sampling_mutation": True,
    "not_paper_shadow_live": True,
    "not_broker_risk_execution": True,
    "not_provider_activation": True,
    "not_external_data_fetch": True,
    "not_frozen_contract_mutation": True,
}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _index_by_symbol(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if symbol and symbol not in indexed:
            indexed[symbol] = dict(row)
    return indexed


def _usage_row(
    *,
    symbol: str,
    alias_row: Mapping[str, Any],
    closure_row: Mapping[str, Any],
) -> dict[str, Any]:
    before_blockers = list(closure_row.get("exact_blockers") or [])
    context_allowed = bool(alias_row.get("safe_for_operator_context"))
    return {
        "symbol": symbol,
        "legacy_artifacts_found": [
            f"{alias_row.get('legacy_preset_id') or 'unknown'}@{alias_row.get('legacy_timeframe') or 'unknown'}"
        ],
        "context_usage_allowed": context_allowed,
        "current_evidence_usage_blocked": True,
        "oos_proof_allowed": bool(alias_row.get("safe_for_oos_context")) and bool(alias_row.get("safe_for_evidence_completion")),
        "campaign_lineage_proof_allowed": bool(alias_row.get("safe_for_campaign_lineage")),
        "evidence_completeness_allowed": bool(alias_row.get("safe_for_evidence_completion")),
        "routing_readiness_allowed": False,
        "sampling_readiness_allowed": False,
        "strategy_synthesis_readiness_allowed": False,
        "reason": str(alias_row.get("policy_reason") or ""),
        "exact_missing_evidence_required_for_upgrade": list(alias_row.get("required_evidence_for_upgrade") or []),
        "next_action": "operator_approve_bounded_aapl_nvda_current_basket_grid_generation",
        "before_blockers": before_blockers,
        "after_blockers": before_blockers,
        "authority_boundary": dict(AUTHORITY_BOUNDARY),
    }


def _dry_run_simulation(*, usage_matrix: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for usage_row in usage_matrix:
        symbol = str(usage_row.get("symbol") or "")
        before_blockers = list(usage_row.get("before_blockers") or [])
        after_lineage = [item for item in before_blockers if item != "campaign_lineage_missing"]
        after_oos = [item for item in before_blockers if item != "no_oos_evidence"]
        after_both = [item for item in before_blockers if item not in {"campaign_lineage_missing", "no_oos_evidence"}]
        rows.append(
            {
                "symbol": symbol,
                "if_campaign_lineage_artifact_accepted": {
                    "would_clear": "campaign_lineage_missing",
                    "remaining_blockers": after_lineage,
                },
                "if_oos_artifact_accepted": {
                    "would_clear": "no_oos_evidence",
                    "remaining_blockers": after_oos,
                },
                "if_both_accepted": {
                    "remaining_blockers": after_both,
                    "evidence_complete_may_improve": len(after_both) == 0,
                },
            }
        )
    return {
        "hypothetical_only": True,
        "rows": rows,
        "trusted_loop_effect": "remains_fail_closed_until_actual_accepted_artifacts_exist",
    }


def build_guarded_alias_bounded_generation_cascade(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    alias_report = alias_policy.build_guarded_preset_timeframe_alias_policy(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    closure_report = closure.build_evidence_complete_basket_closure(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    recovery_cascade = first_batch_cascade.build_first_batch_evidence_recovery_cascade(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    decision_report = generation_decision.build_bounded_first_batch_generation_decision(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    verifier_report = acceptance_verifier.build_bounded_generation_artifact_acceptance_verifier(
        repo_root=repo_root,
    )
    alias_rows = _index_by_symbol(alias_report.get("rows") if isinstance(alias_report.get("rows"), list) else [])
    closure_rows = _index_by_symbol(closure_report.get("rows") if isinstance(closure_report.get("rows"), list) else [])
    usage_matrix = [
        _usage_row(
            symbol=symbol,
            alias_row=alias_rows.get(symbol, {}),
            closure_row=closure_rows.get(symbol, {}),
        )
        for symbol in FIRST_BATCH_SYMBOLS
    ]
    simulation = _dry_run_simulation(usage_matrix=usage_matrix)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
        "summary": {
            "first_batch": list(FIRST_BATCH_SYMBOLS),
            "alias_policy_status": str(alias_report.get("summary", {}).get("final_recommendation") or ""),
            "legacy_context_only": all(bool(row.get("context_usage_allowed")) for row in usage_matrix),
            "evidence_complete_count": int((closure_report.get("summary") or {}).get("evidence_complete_count") or 0),
            "unknown_blocker_count": int((closure_report.get("summary") or {}).get("unknown_blocker_count") or 0),
            "current_top_blocker": "operator_approval_required_for_bounded_generation",
            "bounded_generation_decision_status": str((decision_report.get("summary") or {}).get("final_recommendation") or ""),
            "acceptance_verifier_status": str((verifier_report.get("summary") or {}).get("final_recommendation") or ""),
            "operator_summary": (
                "Guarded alias analysis confirms legacy first-batch pullback evidence is context-only "
                "and the bounded current-basket generation packet is prepared without running generation."
            ),
        },
        "alias_policy": alias_report,
        "legacy_evidence_usage_matrix": usage_matrix,
        "bounded_generation_decision": decision_report,
        "artifact_acceptance_verifier": verifier_report,
        "dry_run_simulation": simulation,
        "upstream_context": {
            "first_batch_recovery_cascade_result": str(recovery_cascade.get("overall_result") or ""),
            "first_batch_recovery_cascade_stop_condition": str(recovery_cascade.get("fundamental_stop_condition") or ""),
        },
        "fundamental_stop_condition": "operator_approval_required_for_bounded_generation",
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
            "mutates_frozen_contracts": False,
            "context_only_not_promoted_to_proof": True,
            "evidence_complete_count_unchanged": int((closure_report.get("summary") or {}).get("evidence_complete_count") or 0) == 0,
            "unknown_blocker_count_unchanged": int((closure_report.get("summary") or {}).get("unknown_blocker_count") or 0) == 0,
            "no_actual_bounded_generation_run": True,
        },
        "authority_boundary": dict(AUTHORITY_BOUNDARY),
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("legacy_evidence_usage_matrix") if isinstance(report.get("legacy_evidence_usage_matrix"), list) else []
    return "\n".join(
        [
            "# QRE Guarded Alias And Bounded Generation Cascade",
            "",
            "## 1. Summary",
            _table(
                ["Field", "Value"],
                [
                    ["first_batch", ", ".join(str(v) for v in summary.get("first_batch") or []) or "none"],
                    ["overall_result", str(report.get("overall_result") or "")],
                    ["alias_policy_status", str(summary.get("alias_policy_status") or "")],
                    ["current_top_blocker", str(summary.get("current_top_blocker") or "")],
                    ["evidence_complete_count", str(summary.get("evidence_complete_count") or 0)],
                    ["bounded_generation_decision_status", str(summary.get("bounded_generation_decision_status") or "")],
                ],
            ),
            "",
            "## 2. Legacy usage matrix",
            _table(
                ["Symbol", "Context allowed", "OOS proof", "Lineage proof", "Evidence complete", "Next action"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(bool(row.get("context_usage_allowed"))).lower(),
                        str(bool(row.get("oos_proof_allowed"))).lower(),
                        str(bool(row.get("campaign_lineage_proof_allowed"))).lower(),
                        str(bool(row.get("evidence_completeness_allowed"))).lower(),
                        str(row.get("next_action") or ""),
                    ]
                    for row in rows
                ],
            ),
            "",
            "## 3. Hypothetical dry run",
            _table(
                ["Symbol", "Campaign accepted", "OOS accepted", "Both accepted"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str((row.get("if_campaign_lineage_artifact_accepted") or {}).get("remaining_blockers") or []),
                        str((row.get("if_oos_artifact_accepted") or {}).get("remaining_blockers") or []),
                        str((row.get("if_both_accepted") or {}).get("remaining_blockers") or []),
                    ]
                    for row in (report.get("dry_run_simulation") or {}).get("rows", [])
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_guarded_alias_bounded_generation_cascade: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_guarded_alias_bounded_generation_cascade",
        description="Build the guarded alias and bounded generation cascade report.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_guarded_alias_bounded_generation_cascade(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
