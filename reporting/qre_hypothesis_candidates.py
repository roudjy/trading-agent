"""Read-only QRE hypothesis candidate projector."""

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
REPORT_KIND: Final[str] = "qre_hypothesis_candidates"
INPUT_REPORT_KIND: Final[str] = "qre_market_observation_snapshot"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_market_observations/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_hypothesis_candidates"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_hypothesis_candidates/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STATUS_PROPOSED: Final[str] = "proposed"

NOTE_INPUT_ABSENT: Final[str] = "market_observation_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "market_observation_artifact_unparseable"
NOTE_NO_HYPOTHESES: Final[str] = "no_hypotheses_projected"
NOTE_HYPOTHESES_PRESENT: Final[str] = "hypothesis_candidates_present"


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


def _template_for_type(observation_type: str) -> dict[str, str]:
    templates = {
        "exit_failure_pattern": {
            "title": "Exit and invalidation rule quality",
            "claim": "Observed exit weakness may be caused by invalidation logic rather than entry signal quality.",
            "expected_edge": "Cleaner exits should reduce adverse hold time without changing strategy definitions.",
            "falsification_criteria": "The exit-focused diagnostic shows no improvement in drawdown, hold-time, or loss clustering.",
        },
        "low_trade_count": {
            "title": "Sample and liquidity sufficiency",
            "claim": "The observation may be underpowered because trade count or liquidity support is too low.",
            "expected_edge": "A broader or better-sampled validation should separate weak evidence from genuine absence of edge.",
            "falsification_criteria": "Expanded validation still produces insufficient sample support or unstable metrics.",
        },
        "high_window_end_impact": {
            "title": "Fold and window-boundary sensitivity",
            "claim": "The observation may be driven by fold timing or window-end effects instead of durable market behavior.",
            "expected_edge": "Boundary-robust validation should reduce metric variance across folds.",
            "falsification_criteria": "Walk-forward and boundary-shift checks show the same instability.",
        },
        "source_quality_issue": {
            "title": "Data source quality and artifact integrity",
            "claim": "The observation may be caused by malformed or low-quality source data rather than market behavior.",
            "expected_edge": "Data-quality triage should either repair evidence quality or block downstream interpretation.",
            "falsification_criteria": "Source-quality checks pass while the same observation persists.",
        },
        "paper_divergence": {
            "title": "Research engine and paper parity",
            "claim": "Paper/runtime divergence may invalidate direct interpretation of the research result.",
            "expected_edge": "Parity diagnostics should isolate whether the signal survives engine differences.",
            "falsification_criteria": "Parity checks show no material difference between research and paper semantics.",
        },
        "unknown": {
            "title": "Unclassified market observation",
            "claim": "The observation requires human review before it can become an executable research idea.",
            "expected_edge": "Manual classification should turn the observation into a bounded validation question.",
            "falsification_criteria": "No clear falsifiable hypothesis can be derived from the evidence.",
        },
    }
    return templates.get(observation_type, templates["unknown"])


def _build_hypothesis(observation: dict[str, Any]) -> dict[str, Any]:
    observation_type = _bounded_str(observation.get("observation_type"), max_len=80)
    template = _template_for_type(observation_type)
    return {
        "hypothesis_id": _hypothesis_id(observation),
        "source_observation_id": _bounded_str(
            observation.get("observation_id"), max_len=160
        ),
        "title": template["title"],
        "claim": template["claim"],
        "asset_scope": _str_list(observation.get("asset_scope")) or ["unknown"],
        "timeframe_scope": _str_list(observation.get("timeframe_scope")) or ["unknown"],
        "regime_tags": _str_list(observation.get("regime_tags")),
        "expected_edge": template["expected_edge"],
        "falsification_criteria": template["falsification_criteria"],
        "validation_plan_required": True,
        "supporting_evidence_refs": _str_list(
            observation.get("supporting_evidence_refs"), max_items=24, max_len=180
        ),
        "contradicting_evidence_refs": _str_list(
            observation.get("contradicting_evidence_refs"), max_items=24, max_len=180
        ),
        "status": STATUS_PROPOSED,
        "safe_to_execute": False,
    }


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_status": {STATUS_PROPOSED: 0}}


def _counts(hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(item.get("status") or STATUS_PROPOSED) for item in hypotheses)
    out = _empty_counts()
    out["total"] = len(hypotheses)
    out["by_status"][STATUS_PROPOSED] = counter.get(STATUS_PROPOSED, 0)
    return out


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    hypotheses: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "hypotheses": hypotheses,
        "counts": _counts(hypotheses),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "hypothesis_candidates_ready_for_validation_planning"
            if hypotheses
            else "no_hypothesis_candidates_available"
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
            hypotheses=[],
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
            hypotheses=[],
            validation_warnings=[NOTE_INPUT_UNPARSEABLE],
        )

    hypotheses = [_build_hypothesis(item) for item in raw_observations]
    hypotheses.sort(key=lambda item: item["hypothesis_id"])
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_HYPOTHESES_PRESENT if hypotheses else NOTE_NO_HYPOTHESES,
        hypotheses=hypotheses,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE hypothesis candidate dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_hypothesis_candidates.",
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
        prog="reporting.qre_hypothesis_candidates",
        description="Project QRE market observations into proposed hypotheses.",
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
    "STATUS_PROPOSED",
    "collect_snapshot",
    "main",
    "write_outputs",
]
