"""Read-only QRE hypothesis validation-plan projector."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_hypothesis_validation_plan"
INPUT_REPORT_KIND: Final[str] = "qre_hypothesis_candidates"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_hypothesis_candidates/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_hypothesis_validation_plans"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_hypothesis_validation_plans/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STATUS_PLANNED: Final[str] = "planned"

NOTE_INPUT_ABSENT: Final[str] = "hypothesis_candidate_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "hypothesis_candidate_artifact_unparseable"
NOTE_NO_PLANS: Final[str] = "no_validation_plans_projected"
NOTE_PLANS_PRESENT: Final[str] = "validation_plans_present"


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> tuple[bool, dict[str, Any] | None]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return (False, None)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return (True, None)
    return (True, parsed if isinstance(parsed, dict) else None)


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _str_list(value: Any, *, max_items: int = 16, max_len: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        text = _bounded_str(item, max_len=max_len)
        if text:
            out.append(text)
    return out


def _minimum_trade_count(timeframes: list[str]) -> int:
    normalized = {item.lower() for item in timeframes}
    if any(item in {"1m", "5m", "15m", "30m", "1h"} for item in normalized):
        return 100
    if any(item in {"2h", "4h"} for item in normalized):
        return 60
    return 50


def _experiments_for_claim(claim: str) -> list[str]:
    lowered = claim.lower()
    if "exit" in lowered or "invalidation" in lowered:
        return [
            "exit_diagnostic_replay_plan",
            "loss_cluster_review_plan",
            "hold_time_distribution_check_plan",
        ]
    if "underpowered" in lowered or "liquidity" in lowered or "sample" in lowered:
        return [
            "sample_size_sufficiency_check_plan",
            "liquidity_filter_sensitivity_plan",
            "asset_timeframe_expansion_feasibility_plan",
        ]
    if "window" in lowered or "fold" in lowered:
        return [
            "walk_forward_boundary_shift_plan",
            "fold_metric_stability_plan",
            "window_end_sensitivity_plan",
        ]
    if "source" in lowered or "data" in lowered:
        return [
            "source_schema_quality_check_plan",
            "missingness_and_duplicate_scan_plan",
            "artifact_integrity_review_plan",
        ]
    if "paper" in lowered or "parity" in lowered or "engine" in lowered:
        return [
            "research_paper_parity_review_plan",
            "fill_semantics_comparison_plan",
            "runtime_assumption_diff_plan",
        ]
    return [
        "manual_hypothesis_classification_plan",
        "evidence_completeness_review_plan",
    ]


def _validation_plan_id(hypothesis_id: str, required_experiments: list[str]) -> str:
    seed = hypothesis_id + "|" + ",".join(required_experiments)
    return "qre-plan-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _build_plan(hypothesis: dict[str, Any]) -> dict[str, Any]:
    hypothesis_id = _bounded_str(hypothesis.get("hypothesis_id"), max_len=160)
    asset_scope = _str_list(hypothesis.get("asset_scope")) or ["unknown"]
    timeframe_scope = _str_list(hypothesis.get("timeframe_scope")) or ["unknown"]
    required_experiments = _experiments_for_claim(
        _bounded_str(hypothesis.get("claim"), max_len=600)
    )
    return {
        "validation_plan_id": _validation_plan_id(hypothesis_id, required_experiments),
        "hypothesis_id": hypothesis_id,
        "required_experiments": required_experiments,
        "asset_scope": asset_scope,
        "timeframe_scope": timeframe_scope,
        "minimum_trade_count": _minimum_trade_count(timeframe_scope),
        "primary_metrics": [
            "deflated_sharpe",
            "max_drawdown",
            "trade_count",
            "fold_consistency",
        ],
        "falsification_criteria": _bounded_str(
            hypothesis.get("falsification_criteria"), max_len=600
        ),
        "status": STATUS_PLANNED,
        "safe_to_execute": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_status": {STATUS_PLANNED: 0}}


def _counts(plans: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(item.get("status") or STATUS_PLANNED) for item in plans)
    out = _empty_counts()
    out["total"] = len(plans)
    out["by_status"][STATUS_PLANNED] = counter.get(STATUS_PLANNED, 0)
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    validation_plans: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "validation_plans": validation_plans,
        "counts": _counts(validation_plans),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "validation_plans_ready_for_action_candidate_projection"
            if validation_plans
            else "no_validation_plans_available"
        ),
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "eligible_for_direct_execution": False,
    }


def collect_snapshot(
    *,
    input_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = input_artifact_path or INPUT_ARTIFACT_PATH
    available, payload = _read_json(source)
    if payload is None:
        note = NOTE_INPUT_UNPARSEABLE if available else NOTE_INPUT_ABSENT
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=available,
            note=note,
            validation_plans=[],
            validation_warnings=[note],
        )

    raw_hypotheses = payload.get("hypotheses")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(
        raw_hypotheses, list
    ) or not all(isinstance(item, dict) for item in raw_hypotheses):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            validation_plans=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    validation_plans = [_build_plan(item) for item in raw_hypotheses]
    validation_plans.sort(key=lambda item: item["validation_plan_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_PLANS_PRESENT if validation_plans else NOTE_NO_PLANS,
        validation_plans=validation_plans,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE validation plan dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_hypothesis_validation_plans.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_hypothesis_validation_plan",
        description="Project QRE hypotheses into read-only validation plans.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        input_artifact_path=args.source,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "STATUS_PLANNED",
    "collect_snapshot",
    "main",
    "write_outputs",
]
