from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_routing_readiness_from_basket as routing


REPORT_KIND: Final[str] = "qre_sampling_readiness_from_basket"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_sampling_readiness_from_basket")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_sampling_readiness_from_basket/"
_STATE_ORDER: Final[tuple[str, ...]] = ("ready", "blocked", "deferred", "fail_closed")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _max_oos_trades(row: Mapping[str, Any]) -> int:
    counts = row.get("validation_evidence_status_counts")
    if not isinstance(counts, Mapping):
        return 0
    if int(counts.get("sufficient_oos_evidence") or 0) > 0:
        return 12
    if int(counts.get("insufficient_oos_trades") or 0) > 0:
        return 5
    return 0


def _sampling_state(row: Mapping[str, Any]) -> tuple[str, str, bool]:
    routing_state = str(row.get("routing_readiness_state") or "fail_closed")
    primary_reason = str(row.get("primary_reason_code") or "supporting_artifacts_missing")
    if routing_state == "fail_closed":
        return ("fail_closed", "supporting_artifacts_missing", False)
    if routing_state == "blocked":
        return ("blocked", primary_reason, False)
    if routing_state == "deferred":
        return ("deferred", primary_reason, False)
    evidence = row.get("evidence_presence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    if not bool(evidence.get("cache_ready")):
        return ("blocked", "sampling_cache_not_ready", False)
    if not bool(evidence.get("oos_evidence_known")):
        return ("deferred", "sampling_oos_window_unknown", False)
    return ("ready", "sampling_ready_for_readonly_requirements", True)


def _sampling_score(row: Mapping[str, Any], *, sampling_ready: bool) -> int:
    routing_score = int(row.get("routing_readiness_score_pct") or 0)
    score = routing_score
    if sampling_ready:
        score += 10
    if _max_oos_trades(row) >= 10:
        score += 5
    return min(score, 100)


def build_sampling_readiness_from_basket(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    base = routing.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    source_rows = base.get("rows")
    if not isinstance(source_rows, list):
        source_rows = []

    rows: list[dict[str, Any]] = []
    for row in source_rows:
        if not isinstance(row, Mapping):
            continue
        state, primary_reason, sampling_ready = _sampling_state(row)
        score = _sampling_score(row, sampling_ready=sampling_ready)
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "symbol": row.get("symbol"),
                "region": row.get("region"),
                "asset_class": row.get("asset_class"),
                "preset_id": row.get("preset_id"),
                "hypothesis_id": row.get("hypothesis_id"),
                "behavior_family": row.get("behavior_family"),
                "timeframes": list(row.get("timeframes") or []),
                "routing_readiness_state": row.get("routing_readiness_state"),
                "routing_readiness_score_pct": int(row.get("routing_readiness_score_pct") or 0),
                "sampling_readiness_state": state,
                "sampling_readiness_score_pct": score,
                "sampling_ready": sampling_ready,
                "primary_reason_code": primary_reason,
                "recommended_sampling_requirements": [
                    "require_readonly_cache_coverage",
                    "require_explicit_oos_window",
                    "require_non_mutating_sampling_plan",
                ],
                "evidence_presence": dict(row.get("evidence_presence") or {}),
                "validation_evidence_status_counts": dict(
                    row.get("validation_evidence_status_counts") or {}
                ),
                "follow_up": (
                    "eligible_for_readonly_sampling"
                    if sampling_ready
                    else row.get("follow_up") or "keep_fail_closed"
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            _STATE_ORDER.index(str(row["sampling_readiness_state"])),
            -int(row["sampling_readiness_score_pct"]),
            str(row["symbol"]),
            str(row["preset_id"]),
        )
    )
    counts = Counter(str(row["sampling_readiness_state"]) for row in rows)
    ready_count = counts.get("ready", 0)
    blocked_count = counts.get("blocked", 0)
    deferred_count = counts.get("deferred", 0)
    fail_closed_count = counts.get("fail_closed", 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "basket_source": base.get("basket_source"),
        "max_candidates": max_candidates,
        "summary": {
            "basket_inventory_count": len(rows),
            "sampling_readiness_state_counts": {
                key: counts.get(key, 0) for key in _STATE_ORDER
            },
            "sampling_ready_count": ready_count,
            "sampling_blocked_count": blocked_count,
            "sampling_deferred_count": deferred_count,
            "sampling_fail_closed_count": fail_closed_count,
            "evidence_backed_zero_ready": ready_count == 0
            and (blocked_count > 0 or deferred_count > 0 or fail_closed_count > 0),
            "final_recommendation": (
                "nothing_sampling_ready_evidence_backed"
                if ready_count == 0
                else "read_only_sampling_ready_items_present"
            ),
            "operator_summary": (
                "Sampling readiness is a read-only projection from routing-ready basket "
                "evidence. No sampling runner or parameter mutation is introduced."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "sampling_runner": False,
            "parameter_mutation": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    counts = summary.get("sampling_readiness_state_counts") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket inventory", str(summary.get("basket_inventory_count") or 0)],
            ["ready", str(counts.get("ready") or 0)],
            ["blocked", str(counts.get("blocked") or 0)],
            ["deferred", str(counts.get("deferred") or 0)],
            ["fail closed", str(counts.get("fail_closed") or 0)],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "Sampling state",
            "Score",
            "Primary reason",
            "Follow-up",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                str(row.get("sampling_readiness_state") or ""),
                str(row.get("sampling_readiness_score_pct") or 0),
                str(row.get("primary_reason_code") or ""),
                str(row.get("follow_up") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Sampling Readiness From Basket Evidence",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Sampling readiness counts",
            count_table,
            "",
            "## 3. Sampling readiness by basket",
            basket_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_sampling_readiness_from_basket: refusing write outside allowlist: {path!r}"
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
    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_sampling_readiness_from_basket",
        description="Build read-only sampling readiness from real basket evidence.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_sampling_readiness_from_basket(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
