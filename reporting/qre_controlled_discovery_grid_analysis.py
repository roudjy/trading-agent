from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SUMMARY_FILENAME = "summary_latest.v1.json"
OPERATOR_SUMMARY_FILENAME = "operator_summary.md"
RESULTS_FILENAME = "combination_results.v1.jsonl"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _group_counts(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get(field) or "unknown")] += 1
    return [
        {"value": key, "count": counts[key]}
        for key in sorted(counts)
    ]


def build_summary(*, run_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counter = Counter(str(row.get("blocker_class") or "unknown") for row in results)
    outcome_counter = Counter(str(row.get("outcome_class") or "unknown") for row in results)
    status_counter = Counter(str(row.get("status") or "unknown") for row in results)

    deferred_count = status_counter.get("execution_integration_deferred", 0)
    summary = {
        "report_kind": "qre_controlled_discovery_grid_analysis",
        "run_dir": run_dir.as_posix(),
        "result_count": len(results),
        "counts": {
            "total_combinations_planned": len(results),
            "total_completed": status_counter.get("completed", 0),
            "total_skipped": sum(
                status_counter.get(name, 0)
                for name in ("skipped_invalid_metadata", "blocked_by_safety")
            ),
            "execution_integration_deferred": deferred_count,
            "insufficient_trades": blocker_counter.get("insufficient_trades", 0),
            "no_oos_evidence": blocker_counter.get("no_oos_evidence", 0),
            "criteria_win_rate_failed": blocker_counter.get("criteria_win_rate_failed", 0),
            "criteria_trades_per_maand_failed": blocker_counter.get(
                "criteria_trades_per_maand_failed", 0
            ),
            "criteria_consistentie_failed": blocker_counter.get(
                "criteria_consistentie_failed", 0
            ),
            "data_coverage_blocker": blocker_counter.get("data_coverage_blocker", 0),
            "near_pass": outcome_counter.get("near_pass", 0),
            "promotion_candidate": outcome_counter.get("promotion_candidate", 0),
            "unknown": outcome_counter.get("unknown", 0),
        },
        "by_region": _group_counts(results, "region"),
        "by_asset": _group_counts(results, "instrument_symbol"),
        "by_behavior_preset": _group_counts(results, "behavior_preset_id"),
        "by_outcome_class": _group_counts(results, "outcome_class"),
        "by_blocker_class": _group_counts(results, "blocker_class"),
        "next_action": "DEFER_EXECUTION_INTEGRATION"
        if deferred_count
        else "MERGE_AND_RUN_ON_VPS",
    }
    return summary


def render_operator_summary(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    evidence_table = _table(
        ["Field", "Count"],
        [
            ["total combinations planned", str(counts["total_combinations_planned"])],
            ["total completed", str(counts["total_completed"])],
            ["total skipped", str(counts["total_skipped"])],
            ["execution integration deferred", str(counts["execution_integration_deferred"])],
            ["insufficient trades", str(counts["insufficient_trades"])],
            ["no OOS evidence", str(counts["no_oos_evidence"])],
            ["criteria win-rate failed", str(counts["criteria_win_rate_failed"])],
            [
                "criteria trades-per-month failed",
                str(counts["criteria_trades_per_maand_failed"]),
            ],
            ["criteria consistentie failed", str(counts["criteria_consistentie_failed"])],
            ["data coverage blocker", str(counts["data_coverage_blocker"])],
            ["near pass", str(counts["near_pass"])],
            ["promotion candidate", str(counts["promotion_candidate"])],
            ["unknown", str(counts["unknown"])],
        ],
    )
    region_table = _table(
        ["Region", "Count"],
        [[row["value"], str(row["count"])] for row in summary["by_region"]],
    )
    preset_table = _table(
        ["Behavior preset", "Count"],
        [[row["value"], str(row["count"])] for row in summary["by_behavior_preset"]],
    )
    return "\n".join(
        [
            "# QRE Controlled Discovery Grid Operator Summary",
            "",
            "## 1. Korte conclusie",
            "- This run prepared a deterministic controlled discovery grid over the read-only production discovery catalog.",
            "- Planning, chunking, resume, and sidecar-only artifact writing are ready for VPS use.",
            "- Direct controlled execution integration is still deferred; current result rows make that explicit instead of pretending market evidence exists.",
            "",
            "## 2. Outcome counts",
            evidence_table,
            "",
            "## 3. Region coverage",
            region_table,
            "",
            "## 4. Behavior preset coverage",
            preset_table,
            "",
            "## 5. Next action",
            f"- NEXT_ACTION: {summary['next_action']}",
        ]
    )


def _resolve_run_dir(input_dir: Path) -> Path:
    if (input_dir / RESULTS_FILENAME).exists():
        return input_dir
    run_dirs = sorted(
        [path for path in input_dir.iterdir() if path.is_dir()],
        key=lambda path: path.name,
    )
    if not run_dirs:
        raise FileNotFoundError(f"no run directories found under {input_dir}")
    return run_dirs[-1]


def summarize_run(
    *,
    input_dir: Path,
    write_summary: bool,
) -> dict[str, Any]:
    run_dir = _resolve_run_dir(input_dir)
    results = _load_jsonl(run_dir / RESULTS_FILENAME)
    summary = build_summary(run_dir=run_dir, results=results)
    if write_summary:
        (run_dir / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (run_dir / OPERATOR_SUMMARY_FILENAME).write_text(
            render_operator_summary(summary) + "\n",
            encoding="utf-8",
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_controlled_discovery_grid_analysis",
        description="Summarize controlled discovery grid sidecar artifacts.",
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args(argv)

    summary = summarize_run(
        input_dir=Path(args.input_dir),
        write_summary=bool(args.write_summary),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
