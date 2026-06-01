"""Read-only QRE hypothesis evidence update projector."""

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
REPORT_KIND: Final[str] = "qre_hypothesis_evidence_update"
HYPOTHESIS_INPUT_REPORT_KIND: Final[str] = "qre_hypothesis_candidates"
RESULT_INPUT_REPORT_KIND: Final[str] = "qre_hypothesis_validation_results"

HYPOTHESIS_INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_hypothesis_candidates/latest.json"
)
RESULT_INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_hypothesis_validation_results/latest.json"
)
HYPOTHESIS_INPUT_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / HYPOTHESIS_INPUT_ARTIFACT_RELATIVE_PATH
)
RESULT_INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / RESULT_INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_hypothesis_evidence_updates"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_hypothesis_evidence_updates/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DECISIONS: Final[tuple[str, ...]] = (
    "supported",
    "weakened",
    "falsified",
    "inconclusive",
    "needs_more_data",
    "contradiction_detected",
)

NOTE_INPUT_ABSENT: Final[str] = "evidence_update_input_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "evidence_update_input_artifact_unparseable"
NOTE_NO_UPDATES: Final[str] = "no_evidence_updates_projected"
NOTE_UPDATES_PRESENT: Final[str] = "evidence_updates_present"


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


def _evidence_update_id(hypothesis_id: str, result_id: str, decision: str) -> str:
    seed = f"{hypothesis_id}|{result_id}|{decision}"
    return "qre-evidence-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _result_for_hypothesis(
    hypothesis_id: str,
    validation_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matches = [
        item
        for item in validation_results
        if _bounded_str(item.get("hypothesis_id"), max_len=160) == hypothesis_id
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: _bounded_str(item.get("result_id"), max_len=160))
    return matches[0]


def _decision(result: dict[str, Any] | None) -> tuple[str, str, str, list[str]]:
    if result is None:
        return (
            "needs_more_data",
            "needs_more_data",
            "No validation result is linked to this hypothesis.",
            ["operator_review_missing_validation_result"],
        )

    status = _bounded_str(result.get("status"), max_len=40)
    falsification_hits = _str_list(result.get("falsification_hits"))
    supporting_refs = _str_list(result.get("supporting_evidence_refs"))
    contradicting_refs = _str_list(result.get("contradicting_evidence_refs"))

    if supporting_refs and contradicting_refs:
        return (
            "contradiction_detected",
            "operator_review_required",
            "Validation evidence contains both support and contradiction references.",
            ["operator_review_contradiction"],
        )
    if status == "failed" or falsification_hits:
        return (
            "falsified",
            "falsified",
            "Validation failed or triggered falsification criteria.",
            ["preserve_negative_result"],
        )
    if status == "passed":
        return (
            "supported",
            "supported",
            "Validation passed without recorded falsification hits.",
            ["consider_repeatability_review"],
        )
    if status == "inconclusive":
        return (
            "inconclusive",
            "needs_more_data",
            "Validation result is inconclusive.",
            ["collect_additional_evidence"],
        )
    return (
        "needs_more_data",
        "needs_more_data",
        "Validation result is missing or incomplete.",
        ["collect_validation_result"],
    )


def _build_update(
    hypothesis: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    hypothesis_id = _bounded_str(hypothesis.get("hypothesis_id"), max_len=160)
    result_id = _bounded_str(result.get("result_id"), max_len=160) if result else ""
    decision, next_status, reason, next_actions = _decision(result)
    supporting_refs = _str_list(result.get("supporting_evidence_refs")) if result else []
    contradicting_refs = (
        _str_list(result.get("contradicting_evidence_refs")) if result else []
    )
    return {
        "evidence_update_id": _evidence_update_id(
            hypothesis_id,
            result_id or "missing",
            decision,
        ),
        "hypothesis_id": hypothesis_id,
        "previous_status": _bounded_str(hypothesis.get("status"), max_len=80)
        or "unknown",
        "evidence_decision": decision,
        "recommended_next_status": next_status,
        "supporting_evidence_refs": supporting_refs,
        "contradicting_evidence_refs": contradicting_refs,
        "reason": reason,
        "next_actions": next_actions,
        "safe_to_execute": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_decision": {decision: 0 for decision in DECISIONS}}


def _counts(evidence_updates: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(
        str(item.get("evidence_decision") or "needs_more_data")
        for item in evidence_updates
    )
    out = _empty_counts()
    out["total"] = len(evidence_updates)
    for decision in DECISIONS:
        out["by_decision"][decision] = counter.get(decision, 0)
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    hypothesis_input_artifact_path: Path,
    result_input_artifact_path: Path,
    hypothesis_input_artifact_available: bool,
    result_input_artifact_available: bool,
    note: str,
    evidence_updates: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "hypothesis_input_artifact_path": _rel(hypothesis_input_artifact_path),
        "result_input_artifact_path": _rel(result_input_artifact_path),
        "hypothesis_input_artifact_available": hypothesis_input_artifact_available,
        "result_input_artifact_available": result_input_artifact_available,
        "note": note,
        "evidence_updates": evidence_updates,
        "counts": _counts(evidence_updates),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "evidence_updates_ready_for_operator_report"
            if evidence_updates
            else "no_evidence_updates_available"
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
    hypothesis_input_artifact_path: Path | None = None,
    result_input_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    hypothesis_source = hypothesis_input_artifact_path or HYPOTHESIS_INPUT_ARTIFACT_PATH
    result_source = result_input_artifact_path or RESULT_INPUT_ARTIFACT_PATH
    hypothesis_available, hypothesis_payload = _read_json(hypothesis_source)
    result_available, result_payload = _read_json(result_source)

    if hypothesis_payload is None or result_payload is None:
        return _base_snapshot(
            generated_at_utc=generated,
            hypothesis_input_artifact_path=hypothesis_source,
            result_input_artifact_path=result_source,
            hypothesis_input_artifact_available=hypothesis_available,
            result_input_artifact_available=result_available,
            note=NOTE_INPUT_UNPARSEABLE
            if hypothesis_available or result_available
            else NOTE_INPUT_ABSENT,
            evidence_updates=[],
            validation_warnings=[NOTE_INPUT_ABSENT]
            if not hypothesis_available or not result_available
            else [NOTE_INPUT_UNPARSEABLE],
        )

    raw_hypotheses = hypothesis_payload.get("hypotheses")
    raw_results = result_payload.get("validation_results")
    if (
        hypothesis_payload.get("report_kind") != HYPOTHESIS_INPUT_REPORT_KIND
        or result_payload.get("report_kind") != RESULT_INPUT_REPORT_KIND
        or not isinstance(raw_hypotheses, list)
        or not isinstance(raw_results, list)
        or not all(isinstance(item, dict) for item in raw_hypotheses)
        or not all(isinstance(item, dict) for item in raw_results)
    ):
        return _base_snapshot(
            generated_at_utc=generated,
            hypothesis_input_artifact_path=hypothesis_source,
            result_input_artifact_path=result_source,
            hypothesis_input_artifact_available=True,
            result_input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            evidence_updates=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    evidence_updates = [
        _build_update(item, _result_for_hypothesis(_bounded_str(item.get("hypothesis_id"), max_len=160), raw_results))
        for item in raw_hypotheses
    ]
    evidence_updates.sort(key=lambda item: item["evidence_update_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        hypothesis_input_artifact_path=hypothesis_source,
        result_input_artifact_path=result_source,
        hypothesis_input_artifact_available=True,
        result_input_artifact_available=True,
        note=NOTE_UPDATES_PRESENT if evidence_updates else NOTE_NO_UPDATES,
        evidence_updates=evidence_updates,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE evidence update dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_hypothesis_evidence_updates.",
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
        prog="reporting.qre_hypothesis_evidence_update",
        description="Project validation results into read-only evidence decisions.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--hypotheses-source", type=Path, default=None)
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        hypothesis_input_artifact_path=args.hypotheses_source,
        result_input_artifact_path=args.results_source,
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
    "DECISIONS",
    "HYPOTHESIS_INPUT_ARTIFACT_PATH",
    "HYPOTHESIS_INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "RESULT_INPUT_ARTIFACT_PATH",
    "RESULT_INPUT_ARTIFACT_RELATIVE_PATH",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
