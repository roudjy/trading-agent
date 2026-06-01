"""Read-only QRE hypothesis validation result snapshot normalizer."""

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
REPORT_KIND: Final[str] = "qre_hypothesis_validation_results"
ACCEPTED_INPUT_REPORT_KINDS: Final[tuple[str, ...]] = (
    REPORT_KIND,
    "synthetic_validation_result_fixture",
    "qre_hypothesis_validation_result_fixture",
)

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_validation_result_fixtures/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_hypothesis_validation_results"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_hypothesis_validation_results/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STATUSES: Final[tuple[str, ...]] = ("passed", "failed", "inconclusive", "missing")

NOTE_INPUT_ABSENT: Final[str] = "validation_result_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "validation_result_artifact_unparseable"
NOTE_NO_RESULTS: Final[str] = "no_validation_results_normalized"
NOTE_RESULTS_PRESENT: Final[str] = "validation_results_present"


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


def _str_list(value: Any, *, max_items: int = 24, max_len: int = 180) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        text = _bounded_str(item, max_len=max_len)
        if text:
            out.append(text)
    return out


def _metric_results(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key in sorted(value):
        name = _bounded_str(key, max_len=80)
        if not name:
            continue
        raw = value[key]
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            out[name] = raw
        else:
            out[name] = _bounded_str(raw, max_len=160)
    return out


def _status(value: Any) -> str:
    text = _bounded_str(value, max_len=40).lower()
    return text if text in STATUSES else "missing"


def _result_id(result: dict[str, Any]) -> str:
    supplied = _bounded_str(result.get("result_id"), max_len=160)
    if supplied:
        return supplied
    seed = "|".join(
        [
            _bounded_str(result.get("hypothesis_id"), max_len=160),
            _bounded_str(result.get("validation_plan_id"), max_len=160),
            _bounded_str(result.get("run_manifest_id"), max_len=160),
            _status(result.get("status")),
        ]
    )
    return "qre-result-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _build_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_id": _result_id(result),
        "hypothesis_id": _bounded_str(result.get("hypothesis_id"), max_len=160),
        "validation_plan_id": _bounded_str(result.get("validation_plan_id"), max_len=160),
        "run_manifest_id": _bounded_str(result.get("run_manifest_id"), max_len=160),
        "status": _status(result.get("status")),
        "metric_results": _metric_results(result.get("metric_results")),
        "falsification_hits": _str_list(result.get("falsification_hits")),
        "supporting_evidence_refs": _str_list(result.get("supporting_evidence_refs")),
        "contradicting_evidence_refs": _str_list(
            result.get("contradicting_evidence_refs")
        ),
        "safe_to_execute": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_status": {status: 0 for status in STATUSES}}


def _counts(validation_results: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(item.get("status") or "missing") for item in validation_results)
    out = _empty_counts()
    out["total"] = len(validation_results)
    for status in STATUSES:
        out["by_status"][status] = counter.get(status, 0)
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    validation_results: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "validation_results": validation_results,
        "counts": _counts(validation_results),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "validation_results_ready_for_evidence_update"
            if validation_results
            else "no_validation_results_available"
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
            validation_results=[],
            validation_warnings=[note],
        )

    input_report_kind = _bounded_str(payload.get("report_kind"), max_len=120)
    raw_results = payload.get("validation_results")
    if (
        (input_report_kind and input_report_kind not in ACCEPTED_INPUT_REPORT_KINDS)
        or not isinstance(raw_results, list)
        or not all(isinstance(item, dict) for item in raw_results)
    ):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            validation_results=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    validation_results = [_build_result(item) for item in raw_results]
    validation_results.sort(key=lambda item: item["result_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_RESULTS_PRESENT if validation_results else NOTE_NO_RESULTS,
        validation_results=validation_results,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE validation result dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_hypothesis_validation_results.",
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
        prog="reporting.qre_hypothesis_validation_results",
        description="Normalize local validation result fixtures into read-only snapshots.",
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
    "ACCEPTED_INPUT_REPORT_KINDS",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "STATUSES",
    "collect_snapshot",
    "main",
    "write_outputs",
]
