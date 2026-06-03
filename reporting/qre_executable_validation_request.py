"""Read-only QRE executable validation request artifact builder."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from reporting import qre_market_observation_hypothesis_readiness as readiness
from reporting.qre_preset_strategy_eligibility_contract import validate_request

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_executable_validation_request"
INPUT_REPORT_KIND: Final[str] = "qre_hypothesis_candidates"
READINESS_REPORT_KIND: Final[str] = "qre_market_observation_hypothesis_readiness"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_hypothesis_candidates/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
READINESS_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_market_observation_hypothesis_readiness/latest.json"
)
READINESS_ARTIFACT_PATH: Final[Path] = REPO_ROOT / READINESS_ARTIFACT_RELATIVE_PATH
MARKET_OBSERVATION_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_market_observations" / "latest.json"
)
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_executable_validation_request"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_executable_validation_request/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

REQUEST_READY: Final[str] = "request_ready_for_operator_review"
REQUEST_BLOCKED_IDENTITY_MISSING: Final[str] = "request_blocked_identity_missing"
REQUEST_BLOCKED_PRESET_INELIGIBLE: Final[str] = "request_blocked_preset_ineligible"
REQUEST_BLOCKED_MARKET_CONTEXT_MISSING: Final[str] = "request_blocked_market_context_missing"
REQUEST_BLOCKED_VALIDATION_PLAN_MISSING: Final[str] = "request_blocked_validation_plan_missing"
REQUEST_BLOCKED_RUN_MANIFEST_MISSING: Final[str] = "request_blocked_run_manifest_missing"
REQUEST_MALFORMED: Final[str] = "request_malformed"

REQUEST_STATUSES: Final[tuple[str, ...]] = (
    REQUEST_READY,
    REQUEST_BLOCKED_IDENTITY_MISSING,
    REQUEST_BLOCKED_PRESET_INELIGIBLE,
    REQUEST_BLOCKED_MARKET_CONTEXT_MISSING,
    REQUEST_BLOCKED_VALIDATION_PLAN_MISSING,
    REQUEST_BLOCKED_RUN_MANIFEST_MISSING,
    REQUEST_MALFORMED,
)

NOTE_INPUT_ABSENT: Final[str] = "hypothesis_candidate_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "hypothesis_candidate_artifact_unparseable"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
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


def _first_scope(value: Any, *, max_len: int = 80) -> str:
    values = _str_list(value, max_items=1, max_len=max_len)
    return values[0] if values else ""


def _request_id(row: dict[str, Any]) -> str:
    seed = "|".join(
        [
            _bounded_str(row.get("hypothesis_id"), max_len=160),
            _bounded_str(row.get("executable_hypothesis_id"), max_len=160),
            _bounded_str(row.get("preset_name"), max_len=160),
            _bounded_str(row.get("validation_plan_id"), max_len=160),
            _bounded_str(row.get("run_manifest_id"), max_len=160),
        ]
    )
    return "qre-req-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _readiness_rows(
    *,
    readiness_path: Path,
    market_observation_path: Path,
    generated_at_utc: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    _available, payload = _read_json(readiness_path)
    if (
        isinstance(payload, dict)
        and payload.get("report_kind") == READINESS_REPORT_KIND
        and isinstance(payload.get("readiness_rows"), list)
    ):
        rows = payload.get("readiness_rows")
        return (
            {
                _bounded_str(item.get("observation_id"), max_len=160): item
                for item in rows
                if isinstance(item, dict) and _bounded_str(item.get("observation_id"), max_len=160)
            },
            [],
        )

    collected = readiness.collect_snapshot(
        input_artifact_path=market_observation_path,
        generated_at_utc=generated_at_utc,
    )
    rows = collected.get("readiness_rows")
    warnings = [
        _bounded_str(item, max_len=160)
        for item in collected.get("validation_warnings", [])
        if _bounded_str(item, max_len=160)
    ]
    if not isinstance(rows, list):
        return ({}, warnings)
    return (
        {
            _bounded_str(item.get("observation_id"), max_len=160): item
            for item in rows
            if isinstance(item, dict) and _bounded_str(item.get("observation_id"), max_len=160)
        },
        warnings,
    )


def _market_context_available(
    hypothesis: dict[str, Any], readiness_row: dict[str, Any] | None
) -> bool:
    asset = _bounded_str(hypothesis.get("asset"), max_len=80) or _first_scope(
        hypothesis.get("asset_scope"),
        max_len=80,
    )
    timeframe = _bounded_str(hypothesis.get("timeframe"), max_len=40) or _first_scope(
        hypothesis.get("timeframe_scope"),
        max_len=40,
    )
    if not asset or asset == "unknown" or not timeframe or timeframe == "unknown":
        return False
    if readiness_row is None:
        return True
    readiness_class = _bounded_str(readiness_row.get("readiness_class"), max_len=80)
    return readiness_class == "hypothesis_ready"


def _allowed_command_preview(row: dict[str, Any]) -> str:
    return (
        "Operator-reviewed validation request for "
        f"preset={row['preset_name']} "
        f"hypothesis={row['executable_hypothesis_id']} "
        f"asset_or_symbol={row.get('asset') or row.get('symbol') or 'unknown'} "
        f"timeframe_or_interval={row.get('timeframe') or row.get('interval') or 'unknown'}"
    )


def _build_request(
    hypothesis: Any,
    *,
    readiness_by_observation_id: dict[str, dict[str, Any]],
    presets: Any = None,
) -> dict[str, Any]:
    if not isinstance(hypothesis, dict):
        return {
            "request_id": "",
            "request_status": REQUEST_MALFORMED,
            "eligibility_status": "malformed_request",
            "safe_to_execute": False,
            "requires_operator_approval": True,
            "allowed_command_preview": None,
        }

    qre_hypothesis_id = _bounded_str(hypothesis.get("hypothesis_id"), max_len=160)
    source_observation_id = _bounded_str(hypothesis.get("source_observation_id"), max_len=160)
    executable_hypothesis_id = _bounded_str(
        hypothesis.get("executable_hypothesis_id"),
        max_len=160,
    )
    asset = _bounded_str(hypothesis.get("asset"), max_len=80) or _first_scope(
        hypothesis.get("asset_scope"),
        max_len=80,
    )
    timeframe = _bounded_str(hypothesis.get("timeframe"), max_len=40) or _first_scope(
        hypothesis.get("timeframe_scope"),
        max_len=40,
    )
    row = {
        "request_id": _request_id(hypothesis),
        "qre_hypothesis_id": qre_hypothesis_id,
        "executable_hypothesis_id": executable_hypothesis_id,
        "source_hypothesis_id": _bounded_str(hypothesis.get("source_hypothesis_id"), max_len=160),
        "validation_plan_id": _bounded_str(hypothesis.get("validation_plan_id"), max_len=160),
        "run_manifest_id": _bounded_str(hypothesis.get("run_manifest_id"), max_len=160),
        "preset_name": _bounded_str(hypothesis.get("preset_name"), max_len=160),
        "strategy_family": _bounded_str(hypothesis.get("strategy_family"), max_len=160),
        "strategy_template_id": _bounded_str(
            hypothesis.get("strategy_template_id"),
            max_len=160,
        ),
        "asset": asset,
        "symbol": _bounded_str(hypothesis.get("symbol"), max_len=80),
        "timeframe": timeframe,
        "interval": _bounded_str(hypothesis.get("interval"), max_len=40),
        "supporting_evidence_refs": _str_list(
            hypothesis.get("supporting_evidence_refs"),
            max_items=24,
            max_len=180,
        ),
        "safe_to_execute": False,
        "requires_operator_approval": True,
    }
    row = {key: value for key, value in row.items() if value not in ("", [])}
    readiness_row = readiness_by_observation_id.get(source_observation_id)
    eligibility = validate_request(row, presets=presets)
    row["eligibility_status"] = eligibility["eligibility_status"]
    row["eligibility_reason_codes"] = eligibility["reason_codes"]

    if not qre_hypothesis_id:
        status = REQUEST_MALFORMED
    elif not executable_hypothesis_id:
        status = REQUEST_BLOCKED_IDENTITY_MISSING
    elif not _market_context_available(hypothesis, readiness_row):
        status = REQUEST_BLOCKED_MARKET_CONTEXT_MISSING
    elif not eligibility["safe_to_request"]:
        status = REQUEST_BLOCKED_PRESET_INELIGIBLE
    elif not row.get("validation_plan_id"):
        status = REQUEST_BLOCKED_VALIDATION_PLAN_MISSING
    elif not row.get("run_manifest_id"):
        status = REQUEST_BLOCKED_RUN_MANIFEST_MISSING
    else:
        status = REQUEST_READY

    row["request_status"] = status
    row["allowed_command_preview"] = (
        _allowed_command_preview(row) if status == REQUEST_READY else None
    )
    return row


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(row.get("request_status") for row in rows)
    return {
        "total": len(rows),
        "ready": counter.get(REQUEST_READY, 0),
        "blocked": len(rows) - counter.get(REQUEST_READY, 0),
        "by_request_status": {status: counter.get(status, 0) for status in REQUEST_STATUSES},
    }


def _final_recommendation(rows: list[dict[str, Any]]) -> str:
    if any(row.get("request_status") == REQUEST_READY for row in rows):
        return "executable_validation_requests_ready_for_operator_review"
    if rows:
        return "executable_validation_requests_blocked_before_operator_review"
    return "no_executable_validation_requests_available"


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    validation_requests: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "safe_to_execute": False,
        "read_only": True,
        "launches_subprocess": False,
        "mutates_research_artifacts": False,
        "final_recommendation": _final_recommendation(validation_requests),
        "counts": _counts(validation_requests),
        "validation_requests": validation_requests,
        "validation_warnings": validation_warnings,
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
    readiness_artifact_path: Path | None = None,
    market_observation_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
    presets: Any = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = input_artifact_path or INPUT_ARTIFACT_PATH
    available, payload = _read_json(source)
    if payload is None:
        warning = NOTE_INPUT_UNPARSEABLE if available else NOTE_INPUT_ABSENT
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=available,
            validation_requests=[],
            validation_warnings=[warning],
        )

    raw_hypotheses = payload.get("hypotheses")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(raw_hypotheses, list):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            validation_requests=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    readiness_by_observation_id, readiness_warnings = _readiness_rows(
        readiness_path=readiness_artifact_path or READINESS_ARTIFACT_PATH,
        market_observation_path=market_observation_artifact_path
        or MARKET_OBSERVATION_ARTIFACT_PATH,
        generated_at_utc=generated,
    )
    validation_requests = [
        _build_request(
            item,
            readiness_by_observation_id=readiness_by_observation_id,
            presets=presets,
        )
        for item in raw_hypotheses
    ]
    validation_requests.sort(key=lambda row: row.get("request_id", ""))
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        validation_requests=validation_requests,
        validation_warnings=readiness_warnings,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE executable validation request dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_executable_validation_request.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
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
        prog="reporting.qre_executable_validation_request",
        description="Build non-executing QRE executable validation requests.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--readiness-source", type=Path, default=None)
    parser.add_argument("--market-observation-source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        input_artifact_path=args.source,
        readiness_artifact_path=args.readiness_source,
        market_observation_artifact_path=args.market_observation_source,
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
    "REQUEST_BLOCKED_IDENTITY_MISSING",
    "REQUEST_BLOCKED_MARKET_CONTEXT_MISSING",
    "REQUEST_BLOCKED_PRESET_INELIGIBLE",
    "REQUEST_BLOCKED_RUN_MANIFEST_MISSING",
    "REQUEST_BLOCKED_VALIDATION_PLAN_MISSING",
    "REQUEST_MALFORMED",
    "REQUEST_READY",
    "REQUEST_STATUSES",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
