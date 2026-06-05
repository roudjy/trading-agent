from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
from pathlib import Path
from typing import Any

from reporting import qre_controlled_discovery_grid_analysis as analysis


OUTPUT_DIR_DEFAULT = Path("research/controlled_discovery_grid_runs")
PLAN_FILENAME = "grid_plan.v1.json"
RESULTS_FILENAME = "combination_results.v1.jsonl"
SUMMARY_FILENAME = "summary_latest.v1.json"
OPERATOR_SUMMARY_FILENAME = "operator_summary.md"


def _utcnow_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _planner_module():
    return importlib.import_module("research.controlled_discovery_grid")


def _plan_payload() -> dict[str, Any]:
    planner = _planner_module()
    return planner.controlled_discovery_grid_payload()


def _selected_combinations(
    *,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    combinations = list(_plan_payload()["combinations"])
    if start < 1 or end < start or end > len(combinations):
        raise ValueError(
            f"invalid range start={start} end={end}; total={len(combinations)}"
        )
    return combinations[start - 1 : end]


def _run_dir(*, output_dir: Path, run_id: str) -> Path:
    return output_dir / run_id


def _result_row(
    combination: dict[str, Any],
    *,
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    row = dict(combination)
    row.update(
        {
            "run_id": run_id,
            "status": "execution_integration_deferred",
            "result_path": (
                f"{run_dir.as_posix()}/combination_{combination['sequence_number']:03d}.json"
            ),
            "blocker_class": "execution_integration_deferred",
            "outcome_class": "unknown",
            "execution_notes": [
                "planner_ready",
                "chunking_ready",
                "resume_ready",
                "sidecar_only_artifacts",
                "no_paper_activation",
                "no_shadow_activation",
                "no_live_activation",
                "execution_integration_deferred",
            ],
        }
    )
    return row


def _load_existing_sequence_numbers(results_path: Path) -> set[int]:
    if not results_path.exists():
        return set()
    sequence_numbers: set[int] = set()
    for line in results_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("sequence_number") is not None:
            sequence_numbers.add(int(payload["sequence_number"]))
    return sequence_numbers


def plan_snapshot() -> dict[str, Any]:
    payload = _plan_payload()
    return {
        "report_kind": "qre_controlled_discovery_grid_runner_plan",
        "grid_kind": payload["grid_kind"],
        "instrument_count": payload["instrument_count"],
        "behavior_preset_count": payload["behavior_preset_count"],
        "total_combinations": payload["total_combinations"],
        "paper_activation_allowed": payload["paper_activation_allowed"],
        "shadow_activation_allowed": payload["shadow_activation_allowed"],
        "live_activation_allowed": payload["live_activation_allowed"],
        "read_only": payload["read_only"],
        "not_alpha_claim": payload["not_alpha_claim"],
    }


def execute_range(
    *,
    start: int,
    end: int,
    output_dir: Path,
    run_id: str | None,
    resume: bool,
) -> dict[str, Any]:
    payload = _plan_payload()
    selected = _selected_combinations(start=start, end=end)
    resolved_run_id = run_id or _utcnow_stamp()
    run_dir = _run_dir(output_dir=output_dir, run_id=resolved_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    plan_path = run_dir / PLAN_FILENAME
    results_path = run_dir / RESULTS_FILENAME

    if not plan_path.exists():
        plan_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    existing_sequence_numbers = _load_existing_sequence_numbers(results_path) if resume else set()
    rows_to_write = [
        _result_row(item, run_id=resolved_run_id, run_dir=run_dir)
        for item in selected
        if int(item["sequence_number"]) not in existing_sequence_numbers
    ]
    if rows_to_write:
        with results_path.open("a", encoding="utf-8") as handle:
            for row in rows_to_write:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = analysis.summarize_run(input_dir=run_dir, write_summary=True)
    return {
        "report_kind": "qre_controlled_discovery_grid_runner_execution",
        "run_id": resolved_run_id,
        "run_dir": run_dir.as_posix(),
        "selected_range": {"start": start, "end": end},
        "selected_count": len(selected),
        "written_count": len(rows_to_write),
        "resume": resume,
        "execution_integration_deferred": True,
        "deferred_reason": (
            "RUNNER_EXECUTION_INTEGRATION_DEFERRED: planner and runbook are ready, "
            "execution integration needs next PR"
        ),
        "artifacts": {
            "grid_plan": plan_path.as_posix(),
            "combination_results": results_path.as_posix(),
            "summary": (run_dir / SUMMARY_FILENAME).as_posix(),
            "operator_summary": (run_dir / OPERATOR_SUMMARY_FILENAME).as_posix(),
        },
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_controlled_discovery_grid_runner",
        description="Plan or stage a controlled QRE discovery grid run.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR_DEFAULT))
    parser.add_argument("--run-id")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    if args.plan_only:
        print(json.dumps(plan_snapshot(), indent=2, ensure_ascii=False))
        return 0

    if args.start is None or args.end is None:
        raise SystemExit("--run requires --start and --end")

    payload = execute_range(
        start=int(args.start),
        end=int(args.end),
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
        resume=bool(args.resume),
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
