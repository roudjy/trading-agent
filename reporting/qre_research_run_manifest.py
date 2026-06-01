"""Read-only QRE research run manifest projector."""

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
REPORT_KIND: Final[str] = "qre_research_run_manifest"
INPUT_REPORT_KIND: Final[str] = "qre_validation_research_action_candidates"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_validation_research_action_candidates/latest.json"
)
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_research_run_manifest"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_research_run_manifest/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STATUS_OPERATOR_REVIEW_REQUIRED: Final[str] = "operator_review_required"

FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "runtime_activation",
    "broker_execution",
    "strategy_or_preset_mutation",
    "campaign_queue_mutation",
    "tool_execution",
)

NOTE_INPUT_ABSENT: Final[str] = "validation_action_candidate_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "validation_action_candidate_artifact_unparseable"
NOTE_NO_MANIFESTS: Final[str] = "no_research_run_manifests_projected"
NOTE_MANIFESTS_PRESENT: Final[str] = "research_run_manifests_present"


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


def _manifest_id(action: dict[str, Any]) -> str:
    seed = "|".join(
        [
            _bounded_str(action.get("action_id"), max_len=160),
            _bounded_str(action.get("target_hypothesis_id"), max_len=160),
            _bounded_str(action.get("target_validation_plan_id"), max_len=160),
        ]
    )
    return "qre-run-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _build_manifest(action: dict[str, Any]) -> dict[str, Any]:
    action_id = _bounded_str(action.get("action_id"), max_len=160)
    plan_id = _bounded_str(action.get("target_validation_plan_id"), max_len=160)
    hypothesis_id = _bounded_str(action.get("target_hypothesis_id"), max_len=160)
    forbidden_actions = _str_list(action.get("forbidden_actions")) or list(
        FORBIDDEN_ACTIONS
    )
    return {
        "run_manifest_id": _manifest_id(action),
        "source_action_id": action_id,
        "target_hypothesis_id": hypothesis_id,
        "target_validation_plan_id": plan_id,
        "status": STATUS_OPERATOR_REVIEW_REQUIRED,
        "suggested_command": (
            "Informational only: operator may prepare a validation research run "
            f"for plan {plan_id or 'unknown'} after explicit approval."
        ),
        "expected_outputs": [
            "validation_result_snapshot",
            "metric_results",
            "falsification_review",
        ],
        "operator_approval_required": True,
        "forbidden_actions": forbidden_actions,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_status": {STATUS_OPERATOR_REVIEW_REQUIRED: 0}}


def _counts(run_manifests: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(
        str(item.get("status") or STATUS_OPERATOR_REVIEW_REQUIRED)
        for item in run_manifests
    )
    out = _empty_counts()
    out["total"] = len(run_manifests)
    out["by_status"][STATUS_OPERATOR_REVIEW_REQUIRED] = counter.get(
        STATUS_OPERATOR_REVIEW_REQUIRED, 0
    )
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    run_manifests: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "run_manifests": run_manifests,
        "counts": _counts(run_manifests),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "research_run_manifests_ready_for_operator_review"
            if run_manifests
            else "no_research_run_manifests_available"
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
            run_manifests=[],
            validation_warnings=[note],
        )

    raw_candidates = payload.get("action_candidates")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(
        raw_candidates, list
    ) or not all(isinstance(item, dict) for item in raw_candidates):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            run_manifests=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    run_manifests = [_build_manifest(item) for item in raw_candidates]
    run_manifests.sort(key=lambda item: item["run_manifest_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_MANIFESTS_PRESENT if run_manifests else NOTE_NO_MANIFESTS,
        run_manifests=run_manifests,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE research run manifest dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_research_run_manifest.",
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
        prog="reporting.qre_research_run_manifest",
        description="Project validation action candidates into operator-gated manifests.",
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
    "STATUS_OPERATOR_REVIEW_REQUIRED",
    "collect_snapshot",
    "main",
    "write_outputs",
]
