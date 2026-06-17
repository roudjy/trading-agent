from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_first_batch_evidence_recovery_cascade as first_batch_cascade


REPORT_KIND: Final[str] = "qre_guarded_preset_timeframe_alias_policy"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_guarded_preset_timeframe_alias_policy")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_guarded_preset_timeframe_alias_policy/"

FIRST_BATCH_SYMBOLS: Final[tuple[str, ...]] = ("AAPL", "NVDA")
CURRENT_PRESET: Final[str] = "trend_pullback_continuation_daily_v1"
CURRENT_TIMEFRAME: Final[str] = "daily_v1"
LEGACY_PRESET: Final[str] = "trend_pullback_v1"
LEGACY_TIMEFRAME: Final[str] = "4h"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _legacy_rows_by_symbol(cascade_report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = (cascade_report.get("legacy_compatibility") or {}).get("rows")
    if not isinstance(rows, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "")
        legacy_preset = str(row.get("legacy_preset_id") or "")
        legacy_timeframe = str(row.get("legacy_timeframe") or "")
        if (
            symbol in FIRST_BATCH_SYMBOLS
            and legacy_preset == LEGACY_PRESET
            and legacy_timeframe == LEGACY_TIMEFRAME
            and symbol not in indexed
        ):
            indexed[symbol] = dict(row)
    return indexed


def _policy_row(*, symbol: str, legacy_row: Mapping[str, Any]) -> dict[str, Any]:
    preset_outcome = str(legacy_row.get("preset_alias_outcome") or "blocked_no_equivalence_policy")
    timeframe_outcome = str(legacy_row.get("timeframe_alias_outcome") or "blocked_timeframe_mismatch")
    safe_for_operator_context = preset_outcome in {
        "alias_allowed_for_context_only",
        "alias_allowed_for_oos_context_not_lineage",
    }
    safe_for_oos_context = str(legacy_row.get("oos_context_eligible") or "") == "True" or preset_outcome == "alias_allowed_for_oos_context_not_lineage"
    safe_for_campaign_lineage = bool(legacy_row.get("campaign_lineage_eligible"))
    safe_for_evidence_completion = False
    policy_decision = (
        "context_only_allowed"
        if safe_for_operator_context and timeframe_outcome == "alias_blocked_timeframe_mismatch"
        else "blocked_timeframe_mismatch"
        if timeframe_outcome == "alias_blocked_timeframe_mismatch"
        else "blocked_no_equivalence_policy"
    )
    blocked_usage = [
        "current_daily_campaign_lineage_proof",
        "current_daily_oos_proof",
        "evidence_completeness_proof",
        "routing_readiness_proof",
        "sampling_readiness_proof",
        "strategy_synthesis_readiness",
    ]
    allowed_usage = ["operator_context", "contextual_research_memory", "source_candidate_history"]
    if safe_for_oos_context:
        allowed_usage.append("oos_context")
    return {
        "symbol": symbol,
        "legacy_preset_id": str(legacy_row.get("legacy_preset_id") or LEGACY_PRESET),
        "current_preset_id": str(legacy_row.get("target_preset_id") or CURRENT_PRESET),
        "legacy_timeframe": str(legacy_row.get("legacy_timeframe") or LEGACY_TIMEFRAME),
        "current_timeframe": str(legacy_row.get("target_timeframe") or CURRENT_TIMEFRAME),
        "mapping_scope": "legacy_validation_to_current_first_batch_context",
        "allowed_usage": allowed_usage,
        "blocked_usage": blocked_usage,
        "policy_decision": policy_decision,
        "policy_reason": (
            "legacy trend_pullback 4h artifacts may inform operator context, "
            "but they do not prove current daily preset lineage or OOS evidence"
        ),
        "required_evidence_for_upgrade": [
            "approved_current_basket_generation_artifact",
            "matching_current_preset_id",
            "matching_current_timeframe",
            "campaign_or_generation_run_identity",
            "structured_oos_fields",
            "structured_lineage_fields",
        ],
        "safe_for_operator_context": safe_for_operator_context,
        "safe_for_oos_context": safe_for_oos_context,
        "safe_for_campaign_lineage": safe_for_campaign_lineage,
        "safe_for_evidence_completion": safe_for_evidence_completion,
        "operator_approval_required": False,
        "downstream_expected_effect": (
            "legacy evidence remains available for context only while "
            "current daily evidence completeness stays fail closed"
        ),
    }


def build_guarded_preset_timeframe_alias_policy(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    cascade_report = first_batch_cascade.build_first_batch_evidence_recovery_cascade(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    legacy_rows = _legacy_rows_by_symbol(cascade_report)
    rows = [
        _policy_row(symbol=symbol, legacy_row=legacy_rows.get(symbol, {}))
        for symbol in FIRST_BATCH_SYMBOLS
    ]
    decisions = Counter(str(row["policy_decision"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "first_batch": list(FIRST_BATCH_SYMBOLS),
            "decision_counts": dict(sorted(decisions.items())),
            "context_only_count": sum(1 for row in rows if row["policy_decision"] == "context_only_allowed"),
            "evidence_completion_allowed_count": sum(1 for row in rows if row["safe_for_evidence_completion"]),
            "operator_summary": (
                "Guarded preset/timeframe alias policy keeps legacy first-batch evidence "
                "available for operator context while blocking evidence-complete use by default."
            ),
            "final_recommendation": (
                "guarded_alias_policy_context_only"
                if rows and all(str(row["policy_decision"]) == "context_only_allowed" for row in rows)
                else "guarded_alias_policy_fail_closed"
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "auto_run_allowed": False,
            "mutates_campaigns": False,
            "mutates_frozen_contracts": False,
            "context_only_not_promoted_to_proof": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Guarded Preset Timeframe Alias Policy",
            "",
            "## 1. Summary",
            _table(
                ["Field", "Value"],
                [
                    ["first_batch", ", ".join(str(v) for v in summary.get("first_batch") or []) or "none"],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                    ["context_only_count", str(summary.get("context_only_count") or 0)],
                    ["evidence_completion_allowed_count", str(summary.get("evidence_completion_allowed_count") or 0)],
                ],
            ),
            "",
            "## 2. Policy rows",
            _table(
                ["Symbol", "Legacy preset", "Current preset", "Legacy tf", "Current tf", "Decision"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(row.get("legacy_preset_id") or ""),
                        str(row.get("current_preset_id") or ""),
                        str(row.get("legacy_timeframe") or ""),
                        str(row.get("current_timeframe") or ""),
                        str(row.get("policy_decision") or ""),
                    ]
                    for row in rows
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_guarded_preset_timeframe_alias_policy: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_guarded_preset_timeframe_alias_policy",
        description="Build the guarded preset/timeframe alias policy report.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_guarded_preset_timeframe_alias_policy(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
