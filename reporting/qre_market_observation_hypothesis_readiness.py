"""Read-only QRE market observation hypothesis-readiness diagnostic."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import tempfile
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_market_observation_hypothesis_readiness"
INPUT_REPORT_KIND: Final[str] = "qre_market_observation_snapshot"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_market_observations/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_market_observation_hypothesis_readiness"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_market_observation_hypothesis_readiness/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

EXAMPLE_LIMIT: Final[int] = 20
WARNING_LIMIT: Final[int] = 50

BRIDGE_FIELDS: Final[tuple[str, ...]] = (
    "executable_hypothesis_id",
    "source_hypothesis_id",
    "strategy_family",
    "strategy_template_id",
    "preset_name",
)

READINESS_CLASSES: Final[tuple[str, ...]] = (
    "hypothesis_ready",
    "identity_missing",
    "execution_identity_missing",
    "insufficient_market_context",
    "insufficient_evidence_refs",
    "unsupported_observation_schema",
    "malformed_observation",
)

NOTE_INPUT_ABSENT: Final[str] = "market_observation_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "market_observation_artifact_unparseable"


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


def _scope_present(row: dict[str, Any], *fields: str) -> bool:
    for field in fields:
        if field in {"asset_scope", "timeframe_scope"}:
            continue
        if _bounded_str(row.get(field), max_len=120):
            return True
    for field in ("asset_scope", "timeframe_scope"):
        if field in fields:
            values = [
                value.lower()
                for value in _str_list(row.get(field), max_items=8, max_len=80)
                if value
            ]
            if values and any(value != "unknown" for value in values):
                return True
    return False


def _has_evidence_refs(row: dict[str, Any]) -> bool:
    return bool(_str_list(row.get("supporting_evidence_refs"), max_items=1, max_len=120))


def _dimension_flags(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "has_observation_id": bool(_bounded_str(row.get("observation_id"), max_len=160)),
        "has_observation_type": bool(_bounded_str(row.get("observation_type"), max_len=80)),
        "has_supporting_evidence_refs": _has_evidence_refs(row),
        "has_source_artifact": bool(_bounded_str(row.get("source_artifact"), max_len=240)),
        "has_executable_hypothesis_id": bool(
            _bounded_str(row.get("executable_hypothesis_id"), max_len=160)
        ),
        "has_strategy_family": bool(_bounded_str(row.get("strategy_family"), max_len=160)),
        "has_strategy_template_id": bool(
            _bounded_str(row.get("strategy_template_id"), max_len=160)
        ),
        "has_preset_name": bool(_bounded_str(row.get("preset_name"), max_len=160)),
        "has_asset_or_symbol": _scope_present(row, "asset", "symbol", "asset_scope"),
        "has_timeframe_or_interval": _scope_present(
            row,
            "timeframe",
            "interval",
            "timeframe_scope",
        ),
        "bounded_text_available": bool(
            _bounded_str(row.get("summary"), max_len=360)
            or _bounded_str(row.get("title"), max_len=240)
            or _bounded_str(row.get("claim"), max_len=360)
        ),
    }


def classify_observation(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {
            "observation_id": "",
            "readiness_class": "malformed_observation",
            "dimensions": {
                "has_observation_id": False,
                "has_observation_type": False,
                "has_supporting_evidence_refs": False,
                "has_source_artifact": False,
                "has_executable_hypothesis_id": False,
                "has_strategy_family": False,
                "has_strategy_template_id": False,
                "has_preset_name": False,
                "has_asset_or_symbol": False,
                "has_timeframe_or_interval": False,
                "bounded_text_available": False,
            },
            "reason_codes": ["observation_row_not_object"],
        }

    dimensions = _dimension_flags(row)
    reason_codes = [key for key, present in dimensions.items() if not present]
    if not (
        dimensions["has_observation_id"]
        and dimensions["has_observation_type"]
        and dimensions["has_source_artifact"]
    ):
        readiness_class = "unsupported_observation_schema"
    elif not dimensions["has_supporting_evidence_refs"]:
        readiness_class = "insufficient_evidence_refs"
    elif not dimensions["has_executable_hypothesis_id"]:
        readiness_class = "execution_identity_missing"
    elif not (
        dimensions["has_strategy_family"]
        and dimensions["has_strategy_template_id"]
        and dimensions["has_preset_name"]
    ):
        readiness_class = "identity_missing"
    elif not (
        dimensions["has_asset_or_symbol"]
        and dimensions["has_timeframe_or_interval"]
        and dimensions["bounded_text_available"]
    ):
        readiness_class = "insufficient_market_context"
    else:
        readiness_class = "hypothesis_ready"
        reason_codes = []
    return {
        "observation_id": _bounded_str(row.get("observation_id"), max_len=160),
        "readiness_class": readiness_class,
        "dimensions": dimensions,
        "reason_codes": reason_codes,
    }


def _bridge_field_counts(observations: list[Any]) -> dict[str, int]:
    counts = {field: 0 for field in BRIDGE_FIELDS}
    for row in observations:
        if not isinstance(row, dict):
            continue
        for field in BRIDGE_FIELDS:
            if _bounded_str(row.get(field), max_len=160):
                counts[field] += 1
    return counts


def _counts(readiness_rows: list[dict[str, Any]], observations: list[Any]) -> dict[str, Any]:
    counter = Counter(row["readiness_class"] for row in readiness_rows)
    return {
        "total_observations": len(observations),
        "readiness_rows": len(readiness_rows),
        "hypothesis_ready": counter.get("hypothesis_ready", 0),
        "not_ready": len(readiness_rows) - counter.get("hypothesis_ready", 0),
    }


def _by_readiness_class(readiness_rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(row["readiness_class"] for row in readiness_rows)
    return {status: counter.get(status, 0) for status in READINESS_CLASSES}


def _examples(readiness_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "observation_id": row["observation_id"],
            "readiness_class": row["readiness_class"],
            "reason_codes": row["reason_codes"][:12],
        }
        for row in readiness_rows[:EXAMPLE_LIMIT]
    ]


def _final_recommendation(readiness_rows: list[dict[str, Any]]) -> str:
    if readiness_rows and all(
        row["readiness_class"] == "hypothesis_ready" for row in readiness_rows
    ):
        return "market_observations_ready_for_executable_hypothesis_projection"
    if any(row["readiness_class"] == "execution_identity_missing" for row in readiness_rows):
        return "explicit_executable_hypothesis_identity_required"
    if readiness_rows:
        return "market_observations_require_operator_triage"
    return "no_market_observations_available"


def _recommended_next_action(readiness_rows: list[dict[str, Any]]) -> str:
    classes = {row["readiness_class"] for row in readiness_rows}
    if "execution_identity_missing" in classes:
        return "add_explicit_executable_hypothesis_id_to_upstream_source"
    if "identity_missing" in classes:
        return "add_explicit_strategy_and_preset_identity_fields_to_upstream_source"
    if "insufficient_market_context" in classes:
        return "add_explicit_asset_or_timeframe_context_to_observations"
    if "insufficient_evidence_refs" in classes:
        return "add_supporting_evidence_refs_to_observations"
    if "hypothesis_ready" in classes and len(classes) == 1:
        return "build_executable_validation_request_artifact"
    return "review_market_observation_schema_before_projection"


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    observations: list[Any],
    readiness_rows: list[dict[str, Any]],
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
        "final_recommendation": _final_recommendation(readiness_rows),
        "recommended_next_action": _recommended_next_action(readiness_rows),
        "counts": _counts(readiness_rows, observations),
        "by_readiness_class": _by_readiness_class(readiness_rows),
        "bridge_field_counts": _bridge_field_counts(observations),
        "readiness_rows": readiness_rows,
        "examples": _examples(readiness_rows),
        "validation_warnings": validation_warnings[:WARNING_LIMIT],
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_research_artifacts": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "launches_subprocess": False,
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
        warning = NOTE_INPUT_UNPARSEABLE if available else NOTE_INPUT_ABSENT
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=available,
            observations=[],
            readiness_rows=[],
            validation_warnings=[warning],
        )

    raw_observations = payload.get("observations")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(raw_observations, list):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            observations=[],
            readiness_rows=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    readiness_rows = [classify_observation(row) for row in raw_observations]
    readiness_rows.sort(key=lambda row: (row["readiness_class"], row["observation_id"]))
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        observations=raw_observations,
        readiness_rows=readiness_rows,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE readiness dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_market_observation_hypothesis_readiness.",
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
        prog="reporting.qre_market_observation_hypothesis_readiness",
        description="Diagnose whether QRE market observations can become executable hypotheses.",
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
    "BRIDGE_FIELDS",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "READINESS_CLASSES",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "classify_observation",
    "collect_snapshot",
    "main",
    "write_outputs",
]
