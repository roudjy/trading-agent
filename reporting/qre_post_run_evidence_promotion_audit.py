"""Read-only QRE post-run evidence and promotion audit."""

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
REPORT_KIND: Final[str] = "qre_post_run_evidence_promotion_audit"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_post_run_evidence_promotion_audit"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_post_run_evidence_promotion_audit/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DEFAULT_RESULTS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_results" / "latest.json"
)
DEFAULT_EVIDENCE_QUALITY_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_evidence_quality_gate" / "latest.json"
)
DEFAULT_PROMOTION_INTENT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_validated_hypothesis_promotion_intent" / "latest.json"
)
DEFAULT_REQUEST_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_executable_validation_request" / "latest.json"
)
DEFAULT_DRY_RUN_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_validation_request_dry_run" / "latest.json"
)

CLASS_NO_VALIDATION_RESULTS: Final[str] = "no_validation_results"
CLASS_RESULTS_INSUFFICIENT: Final[str] = "validation_results_present_but_insufficient"
CLASS_EVIDENCE_INSUFFICIENT: Final[str] = "evidence_quality_insufficient"
CLASS_PROMOTION_NOT_READY: Final[str] = "promotion_not_ready"
CLASS_PROMOTION_READY: Final[str] = "promotion_ready_for_operator_review"
CLASS_IDENTITY_BLOCKED: Final[str] = "identity_route_still_blocked"
CLASS_AUDIT_READY: Final[str] = "audit_ready_for_operator_report"


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


def _safe_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return []
    return rows


def _load(
    path: Path, *, expected_kind: str, field: str, label: str
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return ([], meta, [f"{label}:missing_or_unparseable"])
    rows = _safe_rows(payload, field)
    if field not in payload or not isinstance(payload.get(field), list):
        return ([], meta, [f"{label}:missing_field"])
    meta["valid"] = True
    return (rows, meta, [])


def _load_payload(
    path: Path, *, expected_kind: str, label: str
) -> tuple[dict[str, Any] | None, dict[str, Any], list[str]]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return (None, meta, [f"{label}:missing_or_unparseable"])
    meta["valid"] = True
    return (payload, meta, [])


def _count(rows: list[dict[str, Any]], field: str, names: tuple[str, ...] = ()) -> dict[str, int]:
    counter = Counter(_bounded_str(row.get(field), max_len=80) or "missing" for row in rows)
    if names:
        return {name: counter.get(name, 0) for name in names}
    return dict(sorted(counter.items()))


def _ids(rows: list[dict[str, Any]], field: str) -> set[str]:
    return {
        _bounded_str(row.get(field), max_len=160)
        for row in rows
        if _bounded_str(row.get(field), max_len=160)
    }


def _route_blockers(
    request_payload: dict[str, Any] | None,
    dry_run_payload: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    req_counts = request_payload.get("counts", {}) if isinstance(request_payload, dict) else {}
    dry_counts = dry_run_payload.get("counts", {}) if isinstance(dry_run_payload, dict) else {}
    by_request = req_counts.get("by_request_status", {}) if isinstance(req_counts, dict) else {}
    by_dry = dry_counts.get("by_dry_run_status", {}) if isinstance(dry_counts, dict) else {}
    if isinstance(by_request, dict) and by_request.get("request_blocked_identity_missing", 0):
        blockers.append("identity_route_still_blocked")
    if isinstance(by_request, dict) and by_request.get("request_ready_for_operator_review", 0) == 0:
        blockers.append("no_requests_ready_for_operator_review")
    if isinstance(by_dry, dict) and by_dry.get("dry_run_ready", 0) == 0:
        blockers.append("no_dry_run_ready_requests")
    return blockers


def _backup_comparison(backup_dir: Path | None) -> dict[str, Any]:
    if backup_dir is None:
        return {"available": False, "reason": "backup_dir_not_provided"}
    if not backup_dir.exists() or not backup_dir.is_dir():
        return {"available": False, "reason": "backup_dir_missing", "backup_dir": _rel(backup_dir)}
    files = sorted(path for path in backup_dir.glob("*") if path.is_file())
    return {
        "available": True,
        "backup_dir": _rel(backup_dir),
        "snapshot_files": [_rel(path) for path in files],
        "snapshot_file_count": len(files),
    }


def _classification(
    *,
    validation_results: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    promotion_intents: list[dict[str, Any]],
    route_blockers: list[str],
) -> str:
    if "identity_route_still_blocked" in route_blockers:
        return CLASS_IDENTITY_BLOCKED
    if not validation_results:
        return CLASS_NO_VALIDATION_RESULTS
    status_counts = _count(validation_results, "status")
    if status_counts.get("passed", 0) == 0:
        return CLASS_RESULTS_INSUFFICIENT
    quality_counts = _count(evidence_rows, "quality_class")
    if quality_counts.get("usable", 0) == 0 and quality_counts.get("strong", 0) == 0:
        return CLASS_EVIDENCE_INSUFFICIENT
    intent_counts = _count(promotion_intents, "intent_status")
    if intent_counts.get("operator_review_required", 0) > 0:
        return CLASS_PROMOTION_READY
    if promotion_intents:
        return CLASS_PROMOTION_NOT_READY
    return CLASS_AUDIT_READY


def _next_action(classification: str) -> str:
    return {
        CLASS_IDENTITY_BLOCKED: "repair_explicit_executable_identity_before_regeneration",
        CLASS_NO_VALIDATION_RESULTS: "operator_must_provide_or_generate_validation_results",
        CLASS_RESULTS_INSUFFICIENT: "operator_review_required_for_insufficient_validation_results",
        CLASS_EVIDENCE_INSUFFICIENT: "collect_more_evidence_before_promotion_review",
        CLASS_PROMOTION_NOT_READY: "operator_review_or_more_evidence_required_before_promotion",
        CLASS_PROMOTION_READY: "operator_review_promotion_intents",
        CLASS_AUDIT_READY: "generate_operator_closed_loop_report",
    }.get(classification, "operator_review_required")


def collect_snapshot(
    *,
    validation_results_path: Path | None = None,
    evidence_quality_path: Path | None = None,
    promotion_intent_path: Path | None = None,
    validation_request_path: Path | None = None,
    dry_run_path: Path | None = None,
    backup_dir: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    results, meta_results, warnings_a = _load(
        validation_results_path or DEFAULT_RESULTS_PATH,
        expected_kind="qre_hypothesis_validation_results",
        field="validation_results",
        label="validation_results",
    )
    evidence, meta_evidence, warnings_b = _load(
        evidence_quality_path or DEFAULT_EVIDENCE_QUALITY_PATH,
        expected_kind="qre_evidence_quality_gate",
        field="evidence_quality_rows",
        label="evidence_quality",
    )
    promotion, meta_promotion, warnings_c = _load(
        promotion_intent_path or DEFAULT_PROMOTION_INTENT_PATH,
        expected_kind="qre_validated_hypothesis_promotion_intent",
        field="promotion_intents",
        label="promotion_intent",
    )
    request_payload, meta_request, warnings_d = _load_payload(
        validation_request_path or DEFAULT_REQUEST_PATH,
        expected_kind="qre_executable_validation_request",
        label="validation_request",
    )
    dry_payload, meta_dry, warnings_e = _load_payload(
        dry_run_path or DEFAULT_DRY_RUN_PATH,
        expected_kind="qre_validation_request_dry_run",
        label="dry_run",
    )
    route_blockers = _route_blockers(request_payload, dry_payload)
    classification = _classification(
        validation_results=results,
        evidence_rows=evidence,
        promotion_intents=promotion,
        route_blockers=route_blockers,
    )
    result_ids = _ids(results, "hypothesis_id")
    evidence_ids = _ids(evidence, "hypothesis_id")
    promotion_ids = _ids(promotion, "hypothesis_id")
    blockers = [*route_blockers]
    if not results:
        blockers.append(CLASS_NO_VALIDATION_RESULTS)
    if evidence and not (evidence_ids <= (result_ids | evidence_ids)):
        blockers.append("evidence_quality_linkage_unparseable")
    if promotion and not (promotion_ids <= (evidence_ids | result_ids)):
        blockers.append("promotion_intent_linkage_unparseable")
    audit_summary = {
        "validation_results_count": len(results),
        "validation_status_counts": _count(
            results, "status", ("passed", "failed", "inconclusive", "missing")
        ),
        "evidence_quality_rows": len(evidence),
        "quality_class_counts": _count(
            evidence,
            "quality_class",
            ("insufficient", "thin", "usable", "strong", "contradictory"),
        ),
        "promotion_intent_rows": len(promotion),
        "promotion_readiness_counts": _count(
            promotion,
            "intent_status",
            ("operator_review_required", "blocked", "not_ready"),
        ),
        "link_completeness": {
            "result_hypothesis_ids": len(result_ids),
            "evidence_hypothesis_ids": len(evidence_ids),
            "promotion_hypothesis_ids": len(promotion_ids),
            "evidence_without_result_ids": sorted(evidence_ids - result_ids)[:20],
            "promotion_without_evidence_ids": sorted(promotion_ids - evidence_ids)[:20],
        },
        "blocked_or_missing_identity_reasons": route_blockers,
        "before_after_comparison": _backup_comparison(backup_dir),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "safe_to_execute": False,
        "read_only": True,
        "input_artifacts": {
            "validation_results": meta_results,
            "evidence_quality": meta_evidence,
            "promotion_intent": meta_promotion,
            "validation_request": meta_request,
            "dry_run": meta_dry,
        },
        "final_recommendation": classification,
        "audit_summary": audit_summary,
        "blockers": sorted(set(blockers)),
        "next_action": _next_action(classification),
        "validation_warnings": warnings_a + warnings_b + warnings_c + warnings_d + warnings_e,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "launches_subprocess": False,
        "eligible_for_direct_execution": False,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE post-run audit dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_post_run_evidence_promotion_audit.",
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


def write_outputs(snapshot: dict[str, Any], *, output_path: Path | None = None) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_post_run_evidence_promotion_audit",
        description="Audit QRE validation evidence and promotion readiness after controlled regeneration.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--evidence-quality-source", type=Path, default=None)
    parser.add_argument("--promotion-intent-source", type=Path, default=None)
    parser.add_argument("--validation-request-source", type=Path, default=None)
    parser.add_argument("--dry-run-source", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        validation_results_path=args.results_source,
        evidence_quality_path=args.evidence_quality_source,
        promotion_intent_path=args.promotion_intent_source,
        validation_request_path=args.validation_request_source,
        dry_run_path=args.dry_run_source,
        backup_dir=args.backup_dir,
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
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
