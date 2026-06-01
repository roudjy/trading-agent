"""Read-only QRE validation research-action candidate projector."""

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
REPORT_KIND: Final[str] = "qre_validation_research_action_candidates"
INPUT_REPORT_KIND: Final[str] = "qre_hypothesis_validation_plan"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_hypothesis_validation_plans/latest.json"
)
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "qre_validation_research_action_candidates"
)
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_validation_research_action_candidates/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STATUS_PENDING: Final[str] = "pending"
OUTCOME_NOT_RECORDED: Final[str] = "not_recorded"

FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "paper_runtime_activation",
    "shadow_runtime_activation",
    "live_runtime_activation",
    "broker_execution",
    "strategy_or_preset_mutation",
    "campaign_queue_mutation",
    "codex_execution",
)

NOTE_INPUT_ABSENT: Final[str] = "validation_plan_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "validation_plan_artifact_unparseable"
NOTE_NO_CANDIDATES: Final[str] = "no_validation_action_candidates_projected"
NOTE_CANDIDATES_PRESENT: Final[str] = "validation_action_candidates_present"


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


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _action_id(plan: dict[str, Any]) -> str:
    seed = "|".join(
        [
            _bounded_str(plan.get("validation_plan_id"), max_len=160),
            _bounded_str(plan.get("hypothesis_id"), max_len=160),
            _bounded_str(plan.get("status"), max_len=40),
        ]
    )
    return "qre-action-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _priority(plan: dict[str, Any]) -> str:
    minimum_trade_count = _int_or_default(plan.get("minimum_trade_count"), 0)
    if minimum_trade_count >= 100:
        return "high"
    if minimum_trade_count >= 60:
        return "medium"
    return "low"


def _build_candidate(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": _action_id(plan),
        "source_section": "qre_hypothesis_validation_plan",
        "target_hypothesis_id": _bounded_str(plan.get("hypothesis_id"), max_len=160),
        "target_validation_plan_id": _bounded_str(
            plan.get("validation_plan_id"), max_len=160
        ),
        "priority": _priority(plan),
        "status": STATUS_PENDING,
        "outcome_status": OUTCOME_NOT_RECORDED,
        "operator_approval_required": True,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_status": {STATUS_PENDING: 0}}


def _counts(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(item.get("status") or STATUS_PENDING) for item in candidates)
    out = _empty_counts()
    out["total"] = len(candidates)
    out["by_status"][STATUS_PENDING] = counter.get(STATUS_PENDING, 0)
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    action_candidates: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "action_candidates": action_candidates,
        "counts": _counts(action_candidates),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "validation_action_candidates_ready_for_operator_review"
            if action_candidates
            else "no_validation_action_candidates_available"
        ),
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
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
            action_candidates=[],
            validation_warnings=[note],
        )

    raw_plans = payload.get("validation_plans")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(
        raw_plans, list
    ) or not all(isinstance(item, dict) for item in raw_plans):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            action_candidates=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    action_candidates = [_build_candidate(item) for item in raw_plans]
    action_candidates.sort(key=lambda item: item["action_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_CANDIDATES_PRESENT if action_candidates else NOTE_NO_CANDIDATES,
        action_candidates=action_candidates,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE validation action dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_validation_research_action_candidates.",
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
        prog="reporting.qre_validation_research_action_candidates",
        description="Project validation plans into read-only research action candidates.",
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
    "FORBIDDEN_ACTIONS",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
