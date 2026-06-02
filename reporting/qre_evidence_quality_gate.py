"""Read-only QRE evidence quality gate."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_evidence_quality_gate"

DEFAULT_HYPOTHESES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_candidates" / "latest.json"
)
DEFAULT_RESULTS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_results" / "latest.json"
)
DEFAULT_EVIDENCE_UPDATES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_evidence_updates" / "latest.json"
)
DEFAULT_OPERATOR_REPORT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_closed_loop_operator_report" / "latest.json"
)
DEFAULT_READINESS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_trusted_loop_readiness" / "latest.json"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_evidence_quality_gate"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_evidence_quality_gate/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

QUALITY_CLASSES: Final[tuple[str, ...]] = (
    "insufficient",
    "thin",
    "usable",
    "strong",
    "contradictory",
)

NOTE_INPUT_ISSUES: Final[str] = "evidence_quality_inputs_missing_or_unparseable"
NOTE_GATE_EVALUATED: Final[str] = "evidence_quality_gate_evaluated"


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


def _str_list(value: Any, *, max_items: int = 48, max_len: int = 220) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        text = _bounded_str(item, max_len=max_len)
        if text:
            out.append(text)
    return out


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
    field: str | None,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], dict[str, Any] | None]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return ([], meta, [f"{label}:missing_or_unparseable"], payload)
    meta["valid"] = True
    if field is None:
        return ([], meta, [], payload)
    raw_rows = payload.get(field)
    if (
        field not in payload
        or not isinstance(raw_rows, list)
        or not all(isinstance(item, dict) for item in raw_rows)
    ):
        meta["valid"] = False
        return ([], meta, [f"{label}:missing_or_unparseable"], payload)
    return (_safe_rows(payload, field), meta, [], payload)


def _index_by_hypothesis(rows: list[dict[str, Any]], id_field: str) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        hypothesis_id = _bounded_str(row.get("hypothesis_id"), max_len=160)
        if hypothesis_id:
            indexed.setdefault(hypothesis_id, []).append(row)
    for items in indexed.values():
        items.sort(key=lambda item: _bounded_str(item.get(id_field), max_len=180))
    return indexed


def _lineage_present(result: dict[str, Any] | None, update: dict[str, Any] | None) -> bool:
    for row in (result, update):
        if row is None:
            continue
        if (
            row.get("source_artifact")
            and row.get("source_report_kind")
            and (row.get("source_row_id") or row.get("source_ref"))
        ):
            return True
    return False


def _metrics(result: dict[str, Any] | None) -> dict[str, Any]:
    raw = result.get("metric_results") if result else None
    return raw if isinstance(raw, dict) else {}


def _has_trade_count(metrics: dict[str, Any]) -> bool:
    trade_keys = {
        "trade_count",
        "total_trades",
        "totaal_trades",
        "trades",
        "n_trades",
        "num_trades",
    }
    for key, value in metrics.items():
        normalized = str(key).lower()
        if normalized in trade_keys and value not in (None, "", 0):
            return True
    return False


def _has_primary_metrics(metrics: dict[str, Any]) -> bool:
    primary_names = {
        "win_rate",
        "sharpe",
        "deflated_sharpe",
        "max_drawdown",
        "return",
        "total_return",
        "expectancy",
        "profit_factor",
    }
    return any(str(key).lower() in primary_names and value not in (None, "") for key, value in metrics.items())


def _metric_completeness(metrics: dict[str, Any], trade_count_present: bool, primary_present: bool) -> str:
    if trade_count_present and primary_present:
        return "complete"
    if metrics:
        return "partial"
    return "missing"


def _refs(*rows: dict[str, Any] | None, field: str) -> list[str]:
    refs: list[str] = []
    for row in rows:
        if row is not None:
            refs.extend(_str_list(row.get(field)))
    return sorted(set(refs))


def _operator_approved_indicator_present(
    operator_payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
    update: dict[str, Any] | None,
) -> bool:
    candidates: list[Any] = []
    for row in (result, update):
        if row is not None:
            candidates.append(row.get("operator_approved_indicator_present"))
            candidates.append(row.get("operator_approved"))
    if operator_payload is not None:
        report = operator_payload.get("operator_report")
        if isinstance(report, dict):
            candidates.append(report.get("operator_approved_indicator_present"))
            candidates.append(report.get("operator_approved_for_trusted_loop"))
    return any(value is True for value in candidates)


def _repeatability_status(result: dict[str, Any] | None, update: dict[str, Any] | None) -> str:
    refs = _refs(result, update, field="repeatability_evidence_refs")
    if refs:
        return "repeatability_evidence_present"
    return "no_repeatability_evidence"


def _status(result: dict[str, Any] | None) -> str:
    if result is None:
        return "missing"
    value = _bounded_str(result.get("status"), max_len=40).lower()
    return value or "missing"


def _decision(update: dict[str, Any] | None) -> str:
    if update is None:
        return "missing"
    value = _bounded_str(update.get("evidence_decision"), max_len=80).lower()
    return value or "missing"


def _quality(
    *,
    result: dict[str, Any] | None,
    update: dict[str, Any] | None,
    source_lineage_present: bool,
    trade_count_present: bool,
    primary_metrics_present: bool,
    supporting_count: int,
    contradicting_count: int,
    repeatability_status: str,
    operator_approved_indicator_present: bool,
) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    validation_status = _status(result)
    evidence_decision = _decision(update)
    falsification_hits = _str_list(result.get("falsification_hits")) if result else []

    if result is None:
        return ("insufficient", 0, ["validation_result_missing"])
    if update is None:
        return ("insufficient", 0, ["evidence_update_missing"])
    if evidence_decision == "contradiction_detected" or (
        supporting_count > 0 and contradicting_count > 0
    ):
        return ("contradictory", 10, ["contradictory_evidence_visible"])
    if evidence_decision == "falsified" or validation_status == "failed" or falsification_hits:
        return ("contradictory", 10, ["falsified_or_failed_validation"])
    if validation_status in {"missing", ""}:
        return ("insufficient", 0, ["validation_status_missing"])
    if validation_status == "inconclusive" or evidence_decision in {"inconclusive", "needs_more_data"}:
        if source_lineage_present:
            return ("thin", 25, ["validation_inconclusive_or_needs_more_data"])
        return ("insufficient", 0, ["validation_inconclusive_without_lineage"])
    if validation_status != "passed" or evidence_decision != "supported":
        return ("insufficient", 0, ["validation_not_supported"])

    if not source_lineage_present:
        reasons.append("source_lineage_missing")
    if not primary_metrics_present:
        reasons.append("primary_metrics_missing")
    if not trade_count_present:
        reasons.append("trade_count_missing")
    if supporting_count == 0:
        reasons.append("supporting_evidence_missing")
    if reasons:
        return ("thin", 35, reasons)
    if (
        repeatability_status == "repeatability_evidence_present"
        and operator_approved_indicator_present
    ):
        return ("strong", 95, ["repeatability_and_operator_approval_indicator_present"])
    return ("usable", 75, ["supported_evidence_meets_quality_floor"])


def _build_row(
    hypothesis: dict[str, Any],
    result: dict[str, Any] | None,
    update: dict[str, Any] | None,
    operator_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    metrics = _metrics(result)
    source_lineage = _lineage_present(result, update)
    trade_count = _has_trade_count(metrics)
    primary_metrics = _has_primary_metrics(metrics)
    metric_completeness = _metric_completeness(metrics, trade_count, primary_metrics)
    supporting_refs = _refs(hypothesis, result, update, field="supporting_evidence_refs")
    contradicting_refs = _refs(hypothesis, result, update, field="contradicting_evidence_refs")
    repeatability = _repeatability_status(result, update)
    operator_indicator = _operator_approved_indicator_present(operator_payload, result, update)
    quality_class, quality_score, reasons = _quality(
        result=result,
        update=update,
        source_lineage_present=source_lineage,
        trade_count_present=trade_count,
        primary_metrics_present=primary_metrics,
        supporting_count=len(supporting_refs),
        contradicting_count=len(contradicting_refs),
        repeatability_status=repeatability,
        operator_approved_indicator_present=operator_indicator,
    )
    validation_status = _status(result)
    evidence_decision = _decision(update)
    promotion_allowed = (
        quality_class in {"usable", "strong"}
        and evidence_decision == "supported"
        and validation_status == "passed"
        and len(supporting_refs) > 0
    )
    return {
        "hypothesis_id": _bounded_str(hypothesis.get("hypothesis_id"), max_len=160),
        "evidence_update_id": _bounded_str(update.get("evidence_update_id"), max_len=160)
        if update
        else "",
        "result_id": _bounded_str(result.get("result_id"), max_len=160) if result else "",
        "evidence_decision": evidence_decision,
        "validation_status": validation_status,
        "quality_class": quality_class,
        "quality_score": quality_score,
        "source_lineage_present": source_lineage,
        "metric_completeness": metric_completeness,
        "trade_count_present": trade_count,
        "primary_metrics_present": primary_metrics,
        "supporting_evidence_count": len(supporting_refs),
        "contradicting_evidence_count": len(contradicting_refs),
        "contradiction_visible": evidence_decision == "contradiction_detected"
        or bool(contradicting_refs),
        "repeatability_status": repeatability,
        "operator_approved_indicator_present": operator_indicator,
        "quality_reasons": reasons,
        "promotion_allowed": promotion_allowed,
        "safe_to_execute": False,
    }


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(row.get("quality_class") or "insufficient") for row in rows)
    return {
        "total": len(rows),
        "by_quality_class": {name: counter.get(name, 0) for name in QUALITY_CLASSES},
        "promotion_allowed": sum(1 for row in rows if row.get("promotion_allowed") is True),
    }


def _snapshot(
    *,
    generated_at_utc: str,
    input_artifacts: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifacts": input_artifacts,
        "evidence_quality_rows": rows,
        "counts": _counts(rows),
        "validation_warnings": validation_warnings,
        "final_recommendation": (
            "evidence_quality_ready_for_operator_promotion_review"
            if any(row.get("promotion_allowed") is True for row in rows)
            else "operator_review_required_or_more_evidence_needed"
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
    operator_report_path: Path | None = None,
    readiness_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    hypotheses, meta_a, warnings_a, _payload_a = _load(
        hypotheses_path or DEFAULT_HYPOTHESES_PATH,
        expected_kind="qre_hypothesis_candidates",
        field="hypotheses",
        label="hypotheses",
    )
    results, meta_b, warnings_b, _payload_b = _load(
        validation_results_path or DEFAULT_RESULTS_PATH,
        expected_kind="qre_hypothesis_validation_results",
        field="validation_results",
        label="validation_results",
    )
    updates, meta_c, warnings_c, _payload_c = _load(
        evidence_updates_path or DEFAULT_EVIDENCE_UPDATES_PATH,
        expected_kind="qre_hypothesis_evidence_update",
        field="evidence_updates",
        label="evidence_updates",
    )
    _report_rows, meta_d, warnings_d, operator_payload = _load(
        operator_report_path or DEFAULT_OPERATOR_REPORT_PATH,
        expected_kind="qre_closed_loop_operator_report",
        field=None,
        label="operator_report",
    )
    _readiness_rows, meta_e, warnings_e, _readiness_payload = _load(
        readiness_path or DEFAULT_READINESS_PATH,
        expected_kind="qre_trusted_loop_readiness",
        field=None,
        label="readiness",
    )
    warnings = warnings_a + warnings_b + warnings_c + warnings_d + warnings_e
    input_artifacts = {
        "hypotheses": meta_a,
        "validation_results": meta_b,
        "evidence_updates": meta_c,
        "operator_report": meta_d,
        "readiness": meta_e,
    }
    if warnings:
        return _snapshot(
            generated_at_utc=generated,
            input_artifacts=input_artifacts,
            rows=[],
            validation_warnings=[NOTE_INPUT_ISSUES] + warnings,
        )

    results_by_hypothesis = _index_by_hypothesis(results, "result_id")
    updates_by_hypothesis = _index_by_hypothesis(updates, "evidence_update_id")
    rows = [
        _build_row(
            hypothesis,
            (results_by_hypothesis.get(_bounded_str(hypothesis.get("hypothesis_id"), max_len=160)) or [None])[0],
            (updates_by_hypothesis.get(_bounded_str(hypothesis.get("hypothesis_id"), max_len=160)) or [None])[0],
            operator_payload,
        )
        for hypothesis in hypotheses
    ]
    rows.sort(key=lambda row: (row["hypothesis_id"], row["result_id"], row["evidence_update_id"]))
    return _snapshot(
        generated_at_utc=generated,
        input_artifacts=input_artifacts,
        rows=rows,
        validation_warnings=[],
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE evidence quality gate dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_evidence_quality_gate.",
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
        prog="reporting.qre_evidence_quality_gate",
        description="Evaluate read-only QRE evidence quality.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--hypotheses-source", type=Path, default=None)
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--evidence-updates-source", type=Path, default=None)
    parser.add_argument("--operator-report-source", type=Path, default=None)
    parser.add_argument("--readiness-source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        hypotheses_path=args.hypotheses_source,
        validation_results_path=args.results_source,
        evidence_updates_path=args.evidence_updates_source,
        operator_report_path=args.operator_report_source,
        readiness_path=args.readiness_source,
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
    "DEFAULT_EVIDENCE_UPDATES_PATH",
    "DEFAULT_HYPOTHESES_PATH",
    "DEFAULT_OPERATOR_REPORT_PATH",
    "DEFAULT_READINESS_PATH",
    "DEFAULT_RESULTS_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "QUALITY_CLASSES",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
