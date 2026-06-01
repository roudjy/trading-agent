"""Read-only QRE observation-to-hypothesis projection rows."""

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
REPORT_KIND: Final[str] = "qre_observation_hypothesis_projector"
INPUT_REPORT_KIND: Final[str] = "qre_market_observation_snapshot"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_market_observations/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_observation_hypothesis_projection"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_observation_hypothesis_projection/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

NOTE_INPUT_ABSENT: Final[str] = "market_observation_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "market_observation_artifact_unparseable"
NOTE_NO_ROWS: Final[str] = "no_observation_hypothesis_projection_rows"
NOTE_ROWS_PRESENT: Final[str] = "observation_hypothesis_projection_rows_present"

RULES: Final[dict[str, tuple[str, str]]] = {
    "exit_failure_pattern": ("exit_invalidation_hypothesis", "exit_or_invalidation"),
    "low_trade_count": ("sample_liquidity_hypothesis", "sample_or_liquidity"),
    "high_window_end_impact": ("fold_window_boundary_hypothesis", "fold_boundary"),
    "source_quality_issue": ("data_quality_hypothesis", "data_quality"),
    "paper_divergence": ("engine_parity_hypothesis", "engine_or_parity"),
    "unknown": ("manual_classification_hypothesis", "manual_review"),
}


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


def _hypothesis_id(observation: dict[str, Any]) -> str:
    seed = "|".join(
        [
            _bounded_str(observation.get("observation_id"), max_len=160),
            _bounded_str(observation.get("observation_type"), max_len=80),
            ",".join(_str_list(observation.get("asset_scope"))),
            ",".join(_str_list(observation.get("timeframe_scope"))),
        ]
    )
    return "qre-hyp-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _projection_id(observation_id: str, hypothesis_id: str) -> str:
    seed = f"{observation_id}|{hypothesis_id}"
    return "qre-proj-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _build_row(observation: dict[str, Any]) -> dict[str, Any]:
    observation_type = _bounded_str(observation.get("observation_type"), max_len=80)
    rule_name, family = RULES.get(observation_type, RULES["unknown"])
    observation_id = _bounded_str(observation.get("observation_id"), max_len=160)
    hypothesis_id = _hypothesis_id(observation)
    return {
        "projection_id": _projection_id(observation_id, hypothesis_id),
        "observation_id": observation_id,
        "proposed_hypothesis_id": hypothesis_id,
        "observation_type": observation_type or "unknown",
        "projection_rule": rule_name,
        "hypothesis_family": family,
        "asset_scope": _str_list(observation.get("asset_scope")) or ["unknown"],
        "timeframe_scope": _str_list(observation.get("timeframe_scope")) or ["unknown"],
        "regime_tags": _str_list(observation.get("regime_tags")),
        "status": "proposed",
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_projection_rule": {rule[0]: 0 for rule in RULES.values()}}


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(row.get("projection_rule") or "") for row in rows)
    out = _empty_counts()
    out["total"] = len(rows)
    for rule_name, _family in RULES.values():
        out["by_projection_rule"][rule_name] = counter.get(rule_name, 0)
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    rows: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "projection_rows": rows,
        "counts": _counts(rows),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "projection_rows_ready_for_validation_planning"
            if rows
            else "no_projection_rows_available"
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
            rows=[],
            validation_warnings=[note],
        )

    raw_observations = payload.get("observations")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(
        raw_observations, list
    ) or not all(isinstance(item, dict) for item in raw_observations):
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            rows=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    rows = [_build_row(item) for item in raw_observations]
    rows.sort(key=lambda item: item["projection_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_ROWS_PRESENT if rows else NOTE_NO_ROWS,
        rows=rows,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE projection dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_observation_hypothesis_projection.",
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
        prog="reporting.qre_observation_hypothesis_projector",
        description="Project QRE observations into non-executable hypothesis links.",
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
    "RULES",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
