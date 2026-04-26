from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


EXIT_CODE_DEGENERATE_NO_SURVIVORS = 2
"""Reserved CLI exit code for a controlled `DegenerateResearchRunError` raise.

Only `research.run_research`'s ``__main__`` wrapper may produce this exit
code, and only by translating an uncaught :class:`DegenerateResearchRunError`.
The campaign launcher uses this code to map runs to the
``degenerate_no_survivors`` outcome (v3.15.5).
"""


class DegenerateResearchRunError(RuntimeError):
    """Raised when a research run has no evaluable support."""


def primary_drop_reasons(pair_diagnostics: list[dict[str, Any]]) -> list[str]:
    counts = Counter(
        str(item["drop_reason"])
        for item in pair_diagnostics
        if item.get("status") == "dropped" and item.get("drop_reason")
    )
    return [
        reason
        for reason, _ in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def build_degenerate_run_message(
    *,
    failure_stage: str,
    evaluable_pair_count: int,
    selected_assets: list[str],
    selected_intervals: list[str],
    primary_drop_reasons_list: list[str],
    evaluations_with_oos_daily_returns: int | None = None,
) -> str:
    parts = [
        f"Degenerate research run at stage={failure_stage}",
        f"evaluable_pair_count={evaluable_pair_count}",
        f"selected_assets={selected_assets}",
        f"selected_intervals={selected_intervals}",
        f"primary_drop_reasons={primary_drop_reasons_list}",
    ]
    if evaluations_with_oos_daily_returns is not None:
        parts.append(
            f"evaluations_with_oos_daily_returns={evaluations_with_oos_daily_returns}"
        )
    parts.append(
        "public_outputs_written=False existing_public_outputs_may_be_stale=True"
    )
    return " ".join(parts)


def build_empty_run_diagnostics_payload(
    *,
    as_of_utc: datetime,
    failure_stage: str,
    selected_assets: list[str],
    selected_intervals: list[str],
    interval_ranges: dict[str, dict[str, str]],
    pair_diagnostics: list[dict[str, Any]],
    evaluations_count: int = 0,
    evaluations_with_oos_daily_returns: int = 0,
    col_campaign_id: str | None = None,
) -> dict[str, Any]:
    sorted_pairs = sorted(
        (
            {
                "asset": str(item["asset"]),
                "interval": str(item["interval"]),
                "requested_start": str(item["requested_start"]),
                "requested_end": str(item["requested_end"]),
                "bar_count": int(item["bar_count"]),
                "fold_count": int(item["fold_count"]),
                "status": str(item["status"]),
                "drop_reason": item.get("drop_reason"),
            }
            for item in pair_diagnostics
        ),
        key=lambda item: (item["interval"], item["asset"]),
    )
    evaluable_pair_count = sum(
        1 for item in sorted_pairs if item["status"] == "evaluable"
    )
    drop_reasons = primary_drop_reasons(sorted_pairs)
    message = build_degenerate_run_message(
        failure_stage=failure_stage,
        evaluable_pair_count=evaluable_pair_count,
        selected_assets=list(selected_assets),
        selected_intervals=list(selected_intervals),
        primary_drop_reasons_list=drop_reasons,
        evaluations_with_oos_daily_returns=evaluations_with_oos_daily_returns,
    )
    return {
        "version": "v1",
        "generated_at_utc": as_of_utc.isoformat(),
        "failure_stage": failure_stage,
        "message": message,
        "col_campaign_id": col_campaign_id,
        "selected_assets": list(selected_assets),
        "selected_intervals": list(selected_intervals),
        "interval_ranges": {
            interval: {
                "start": str(bounds["start"]),
                "end": str(bounds["end"]),
            }
            for interval, bounds in interval_ranges.items()
        },
        "summary": {
            "pair_count": len(sorted_pairs),
            "evaluable_pair_count": evaluable_pair_count,
            "dropped_pair_count": len(sorted_pairs) - evaluable_pair_count,
            "evaluations_count": int(evaluations_count),
            "evaluations_with_oos_daily_returns": int(
                evaluations_with_oos_daily_returns
            ),
            "primary_drop_reasons": drop_reasons,
        },
        "pairs": sorted_pairs,
        "public_output_status": {
            "public_outputs_written": False,
            "existing_public_outputs_may_be_stale": True,
            "public_paths": [
                "research/research_latest.json",
                "research/strategy_matrix.csv",
            ],
        },
    }
