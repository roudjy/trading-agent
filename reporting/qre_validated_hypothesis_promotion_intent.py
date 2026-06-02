"""Read-only QRE validated hypothesis promotion intent staging."""

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
REPORT_KIND: Final[str] = "qre_validated_hypothesis_promotion_intent"

DEFAULT_HYPOTHESES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_candidates" / "latest.json"
)
DEFAULT_RESULTS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_results" / "latest.json"
)
DEFAULT_EVIDENCE_UPDATES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_evidence_updates" / "latest.json"
)
DEFAULT_EVIDENCE_QUALITY_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_evidence_quality_gate" / "latest.json"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_validated_hypothesis_promotion_intent"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_validated_hypothesis_promotion_intent/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "actual_research_action_queue_write_forbidden",
    "development_work_queue_write_forbidden",
    "generated_seed_write_forbidden",
    "campaign_queue_mutation_forbidden",
    "strategy_or_preset_mutation_forbidden",
    "paper_shadow_live_activation_forbidden",
    "broker_risk_execution_change_forbidden",
    "codex_launch_forbidden",
    "branch_pr_automation_forbidden",
)

LANE_NAMES: Final[tuple[str, ...]] = (
    "research_action_queue_intent",
    "generated_seed_intent",
    "strategy_or_preset_intent",
    "campaign_intent",
)

NOTE_INPUT_ISSUES: Final[str] = "promotion_intent_inputs_missing_or_unparseable"


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
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _safe_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return []
    return rows


def _load(
    path: Path,
    *,
    expected_kind: str,
    field: str,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return ([], meta, [f"{label}:missing_or_unparseable"])
    raw_rows = payload.get(field)
    if (
        field not in payload
        or not isinstance(raw_rows, list)
        or not all(isinstance(item, dict) for item in raw_rows)
    ):
        return ([], meta, [f"{label}:missing_or_unparseable"])
    meta["valid"] = True
    return (_safe_rows(payload, field), meta, [])


def _promotion_intent_id(row: dict[str, Any], promotion_target: str) -> str:
    seed = "|".join(
        [
            _bounded_str(row.get("hypothesis_id"), max_len=160),
            _bounded_str(row.get("evidence_update_id"), max_len=160),
            _bounded_str(row.get("result_id"), max_len=160),
            _bounded_str(row.get("quality_class"), max_len=40),
            promotion_target,
        ]
    )
    return "qre-promotion-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _lane(name: str, status: str, hypothesis_id: str) -> dict[str, Any]:
    return {
        "lane": name,
        "intent_status": status,
        "hypothesis_id": hypothesis_id,
        "operator_approval_required": True,
        "actual_writes_enabled": False,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
    }


def _intent_lanes(status: str, hypothesis_id: str) -> dict[str, dict[str, Any]]:
    return {name: _lane(name, status, hypothesis_id) for name in LANE_NAMES}


def _intent_status(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    quality_class = _bounded_str(row.get("quality_class"), max_len=40)
    evidence_decision = _bounded_str(row.get("evidence_decision"), max_len=80)
    validation_status = _bounded_str(row.get("validation_status"), max_len=80)
    allowed = row.get("promotion_allowed") is True
    if allowed and quality_class in {"usable", "strong"} and evidence_decision == "supported":
        target = (
            "development_queue_candidate"
            if quality_class == "strong"
            else "qre_research_action_proposal_intake_candidate"
        )
        return (
            "operator_review_required",
            target,
            "supported_evidence_quality_passed_manual_promotion_floor",
            "",
            "operator_review_promotion_intent",
        )
    if quality_class == "contradictory" or evidence_decision in {"falsified", "contradiction_detected"}:
        return (
            "blocked",
            "none",
            "",
            "contradictory_or_falsified_evidence",
            "preserve_negative_or_contradictory_result",
        )
    if validation_status in {"missing", ""} or evidence_decision in {"missing", ""}:
        return (
            "not_ready",
            "none",
            "",
            "missing_validation_or_evidence_update",
            "collect_validation_result_and_evidence_update",
        )
    return (
        "not_ready",
        "none",
        "",
        f"quality_class_{quality_class}_not_promotable",
        "collect_more_evidence_or_operator_review",
    )


def _build_intent(row: dict[str, Any]) -> dict[str, Any]:
    status, target, promotion_reason, blocked_reason, suggested_next_action = _intent_status(row)
    hypothesis_id = _bounded_str(row.get("hypothesis_id"), max_len=160)
    lane_status = "staged_for_operator_review" if status == "operator_review_required" else status
    return {
        "promotion_intent_id": _promotion_intent_id(row, target),
        "hypothesis_id": hypothesis_id,
        "evidence_update_id": _bounded_str(row.get("evidence_update_id"), max_len=160),
        "result_id": _bounded_str(row.get("result_id"), max_len=160),
        "quality_class": _bounded_str(row.get("quality_class"), max_len=40),
        "evidence_decision": _bounded_str(row.get("evidence_decision"), max_len=80),
        "validation_status": _bounded_str(row.get("validation_status"), max_len=80),
        "intent_status": status,
        "promotion_target": target,
        "intent_lanes": _intent_lanes(lane_status, hypothesis_id),
        "actual_writes_enabled": False,
        "operator_approval_required": True,
        "promotion_reason": promotion_reason,
        "blocked_reason": blocked_reason,
        "suggested_next_action": suggested_next_action,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "writes_development_work_queue": False,
        "writes_research_action_queue": False,
        "writes_generated_seed_jsonl": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
    }


def _counts(intents: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(item.get("intent_status") or "not_ready") for item in intents)
    return {
        "total": len(intents),
        "by_intent_status": {
            "operator_review_required": counter.get("operator_review_required", 0),
            "blocked": counter.get("blocked", 0),
            "not_ready": counter.get("not_ready", 0),
        },
        "ready_for_operator_review": counter.get("operator_review_required", 0),
    }


def _snapshot(
    *,
    generated_at_utc: str,
    input_artifacts: dict[str, dict[str, Any]],
    intents: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    ready = any(item.get("intent_status") == "operator_review_required" for item in intents)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifacts": input_artifacts,
        "promotion_intents": intents,
        "counts": _counts(intents),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "operator_review_required_for_validated_hypothesis_promotion"
            if ready
            else "no_validated_hypothesis_promotion_intent_ready"
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
    hypotheses_path: Path | None = None,
    validation_results_path: Path | None = None,
    evidence_updates_path: Path | None = None,
    evidence_quality_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    _hypotheses, meta_a, warnings_a = _load(
        hypotheses_path or DEFAULT_HYPOTHESES_PATH,
        expected_kind="qre_hypothesis_candidates",
        field="hypotheses",
        label="hypotheses",
    )
    _results, meta_b, warnings_b = _load(
        validation_results_path or DEFAULT_RESULTS_PATH,
        expected_kind="qre_hypothesis_validation_results",
        field="validation_results",
        label="validation_results",
    )
    _updates, meta_c, warnings_c = _load(
        evidence_updates_path or DEFAULT_EVIDENCE_UPDATES_PATH,
        expected_kind="qre_hypothesis_evidence_update",
        field="evidence_updates",
        label="evidence_updates",
    )
    quality_rows, meta_d, warnings_d = _load(
        evidence_quality_path or DEFAULT_EVIDENCE_QUALITY_PATH,
        expected_kind="qre_evidence_quality_gate",
        field="evidence_quality_rows",
        label="evidence_quality",
    )
    warnings = warnings_a + warnings_b + warnings_c + warnings_d
    input_artifacts = {
        "hypotheses": meta_a,
        "validation_results": meta_b,
        "evidence_updates": meta_c,
        "evidence_quality": meta_d,
    }
    if warnings:
        return _snapshot(
            generated_at_utc=generated,
            input_artifacts=input_artifacts,
            intents=[],
            validation_warnings=[NOTE_INPUT_ISSUES] + warnings,
        )
    intents = [_build_intent(row) for row in quality_rows]
    intents.sort(key=lambda item: item["promotion_intent_id"])
    return _snapshot(
        generated_at_utc=generated,
        input_artifacts=input_artifacts,
        intents=intents,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE promotion intent dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_validated_hypothesis_promotion_intent.",
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
        prog="reporting.qre_validated_hypothesis_promotion_intent",
        description="Stage read-only validated hypothesis promotion intents.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--hypotheses-source", type=Path, default=None)
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--evidence-updates-source", type=Path, default=None)
    parser.add_argument("--evidence-quality-source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        hypotheses_path=args.hypotheses_source,
        validation_results_path=args.results_source,
        evidence_updates_path=args.evidence_updates_source,
        evidence_quality_path=args.evidence_quality_source,
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
    "DEFAULT_EVIDENCE_QUALITY_PATH",
    "DEFAULT_EVIDENCE_UPDATES_PATH",
    "DEFAULT_HYPOTHESES_PATH",
    "DEFAULT_RESULTS_PATH",
    "FORBIDDEN_ACTIONS",
    "LANE_NAMES",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
