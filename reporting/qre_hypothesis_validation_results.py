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
REAL_SOURCE_REPORT_KINDS: Final[tuple[str, ...]] = (
    "screening_evidence",
    "screening_results",
    "exit_quality_diagnostics",
    "candidate_readiness",
    "qre_data_source_quality_readiness",
    "source_quality_readiness",
    "qre_research_diagnostics_loop",
    "paper_divergence",
    "trend_break_invalidation",
    "no_paper_candidate_diagnostics",
    "research_latest",
    "run_candidates",
)

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_validation_result_fixtures/latest.json"
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH
DEFAULT_HYPOTHESIS_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_candidates" / "latest.json"
)
DEFAULT_PLAN_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_plans" / "latest.json"
)
DEFAULT_RUN_MANIFEST_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_research_run_manifest" / "latest.json"
)
DEFAULT_REAL_SOURCE_ARTIFACT_PATHS: Final[tuple[Path, ...]] = (
    REPO_ROOT / "research" / "screening_evidence_latest.v1.json",
    REPO_ROOT / "research" / "paper_divergence_latest.v1.json",
    REPO_ROOT / "research" / "research_latest.json",
    REPO_ROOT / "research" / "run_candidates_latest.v1.json",
    REPO_ROOT / "logs" / "qre_data_source_quality_readiness" / "latest.json",
    REPO_ROOT / "logs" / "qre_research_diagnostics_loop" / "latest.json",
)
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_hypothesis_validation_results"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_hypothesis_validation_results/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

STATUSES: Final[tuple[str, ...]] = ("passed", "failed", "inconclusive", "missing")

NOTE_INPUT_ABSENT: Final[str] = "validation_result_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "validation_result_artifact_unparseable"
NOTE_NO_RESULTS: Final[str] = "no_validation_results_normalized"
NOTE_RESULTS_PRESENT: Final[str] = "validation_results_present"
NOTE_REAL_SOURCE_ROWS_SKIPPED: Final[str] = "real_source_rows_unlinked_skipped"
NOTE_REAL_SOURCE_ARTIFACT_UNPARSEABLE: Final[str] = "real_source_artifact_unparseable"


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
            _bounded_str(result.get("source_artifact"), max_len=240),
            _bounded_str(result.get("source_report_kind"), max_len=120),
            _bounded_str(
                result.get("source_row_id") or result.get("source_ref"),
                max_len=240,
            ),
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
        "contradicting_evidence_refs": _str_list(result.get("contradicting_evidence_refs")),
        "source_artifact": _bounded_str(result.get("source_artifact"), max_len=240),
        "source_report_kind": _bounded_str(result.get("source_report_kind"), max_len=120),
        "source_row_id": _bounded_str(result.get("source_row_id"), max_len=240),
        "source_ref": _bounded_str(result.get("source_ref"), max_len=300),
        "safe_to_execute": False,
    }


def _safe_dict_rows(payload: dict[str, Any], field: str) -> list[dict[str, Any]] | None:
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return None
    return rows


def _load_link_authorities(
    *,
    hypothesis_artifact_path: Path,
    plan_artifact_path: Path,
    run_manifest_artifact_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    hyp_available, hyp_payload = _read_json(hypothesis_artifact_path)
    plan_available, plan_payload = _read_json(plan_artifact_path)
    run_available, run_payload = _read_json(run_manifest_artifact_path)

    hypotheses: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    run_manifests: list[dict[str, Any]] = []
    if hyp_payload is not None and hyp_payload.get("report_kind") == "qre_hypothesis_candidates":
        hypotheses = _safe_dict_rows(hyp_payload, "hypotheses") or []
    elif hyp_available:
        warnings.append("hypothesis_authority_unparseable")
    else:
        warnings.append("hypothesis_authority_absent")
    if (
        plan_payload is not None
        and plan_payload.get("report_kind") == "qre_hypothesis_validation_plan"
    ):
        plans = _safe_dict_rows(plan_payload, "validation_plans") or []
    elif plan_available:
        warnings.append("validation_plan_authority_unparseable")
    else:
        warnings.append("validation_plan_authority_absent")
    if run_payload is not None and run_payload.get("report_kind") == "qre_research_run_manifest":
        run_manifests = _safe_dict_rows(run_payload, "run_manifests") or []
    elif run_available:
        warnings.append("run_manifest_authority_unparseable")
    else:
        warnings.append("run_manifest_authority_absent")

    hypothesis_ids = {
        _bounded_str(item.get("hypothesis_id"), max_len=160)
        for item in hypotheses
        if _bounded_str(item.get("hypothesis_id"), max_len=160)
    }
    plan_by_hypothesis: dict[str, str] = {}
    for item in plans:
        hypothesis_id = _bounded_str(item.get("hypothesis_id"), max_len=160)
        plan_id = _bounded_str(item.get("validation_plan_id"), max_len=160)
        if hypothesis_id and plan_id:
            plan_by_hypothesis.setdefault(hypothesis_id, plan_id)
    run_by_plan: dict[str, str] = {}
    for item in run_manifests:
        plan_id = _bounded_str(item.get("target_validation_plan_id"), max_len=160)
        run_id = _bounded_str(item.get("run_manifest_id"), max_len=160)
        if plan_id and run_id:
            run_by_plan.setdefault(plan_id, run_id)
    return (
        {
            "hypothesis_ids": hypothesis_ids,
            "plan_by_hypothesis": plan_by_hypothesis,
            "run_by_plan": run_by_plan,
        },
        warnings,
    )


def _source_report_kind(payload: dict[str, Any], path: Path) -> str:
    explicit = _bounded_str(payload.get("report_kind"), max_len=120)
    if explicit:
        return explicit
    name = path.name
    if name == "run_candidates_latest.v1.json":
        return "run_candidates"
    if isinstance(payload.get("candidates"), list):
        return "screening_evidence"
    if isinstance(payload.get("results"), list):
        return "research_latest"
    if isinstance(payload.get("per_candidate"), list) or payload.get("paper_divergence_version"):
        return "paper_divergence"
    return "unknown"


def _rows_for_source(
    payload: dict[str, Any], report_kind: str
) -> tuple[str, list[dict[str, Any]] | None]:
    if report_kind in {"screening_evidence", "run_candidates"}:
        return ("candidates", _safe_dict_rows(payload, "candidates"))
    if report_kind in {
        "screening_results",
        "exit_quality_diagnostics",
        "candidate_readiness",
        "source_quality_readiness",
        "trend_break_invalidation",
        "no_paper_candidate_diagnostics",
    }:
        for field in ("validation_results", "rows", "results", "diagnostics", "items"):
            rows = _safe_dict_rows(payload, field)
            if rows is not None:
                return (field, rows)
        return ("", None)
    if report_kind == "qre_data_source_quality_readiness":
        return ("rows", _safe_dict_rows(payload, "rows"))
    if report_kind == "qre_research_diagnostics_loop":
        return ("diagnostic_chain", _safe_dict_rows(payload, "diagnostic_chain"))
    if report_kind == "paper_divergence":
        return ("per_candidate", _safe_dict_rows(payload, "per_candidate"))
    if report_kind == "research_latest":
        return ("results", _safe_dict_rows(payload, "results"))
    return ("", None)


def _row_identity(row: dict[str, Any], *, index: int, row_field: str) -> str:
    for key in (
        "result_id",
        "candidate_id",
        "hypothesis_id",
        "subject_id",
        "path",
        "strategy_id",
    ):
        value = _bounded_str(row.get(key), max_len=220)
        if value:
            return value
    return f"{row_field}[{index}]"


def _linked_ids(
    row: dict[str, Any],
    authorities: dict[str, Any],
) -> tuple[str, str, str] | None:
    hypothesis_id = _bounded_str(row.get("hypothesis_id"), max_len=160)
    if not hypothesis_id:
        hypothesis_id = _bounded_str(row.get("target_hypothesis_id"), max_len=160)
    if hypothesis_id not in authorities["hypothesis_ids"]:
        return None
    plan_id = _bounded_str(row.get("validation_plan_id"), max_len=160)
    if not plan_id:
        plan_id = authorities["plan_by_hypothesis"].get(hypothesis_id, "")
    if not plan_id:
        return None
    run_id = _bounded_str(row.get("run_manifest_id"), max_len=160)
    if not run_id:
        run_id = authorities["run_by_plan"].get(plan_id, "")
    if not run_id:
        return None
    return (hypothesis_id, plan_id, run_id)


def _status_from_source(row: dict[str, Any], report_kind: str) -> str:
    explicit = _status(row.get("status"))
    if explicit != "missing":
        return explicit
    lowered_values = {
        _bounded_str(row.get(key), max_len=120).lower()
        for key in (
            "stage_result",
            "quality_status",
            "final_status",
            "decision",
            "verdict",
            "divergence_severity",
        )
    }
    if lowered_values & {
        "screening_reject",
        "paper_blocked",
        "blocked",
        "rejected",
        "failed",
        "high",
    }:
        return "failed"
    if lowered_values & {"passed", "ready", "screening_pass", "promotion_candidate", "low"}:
        return "passed"
    if lowered_values & {"near_pass", "needs_investigation", "medium"}:
        return "inconclusive"
    if report_kind == "qre_data_source_quality_readiness":
        return "passed" if row.get("quality_status") == "ready" else "failed"
    return "inconclusive"


def _metrics_from_source(row: dict[str, Any], report_kind: str) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if isinstance(row.get("metrics"), dict):
        raw.update(row["metrics"])
    if isinstance(row.get("metric_results"), dict):
        raw.update(row["metric_results"])
    if isinstance(row.get("summary"), dict):
        raw.update({f"summary.{key}": value for key, value in row["summary"].items()})
    for key in (
        "stage_result",
        "pass_kind",
        "screening_phase",
        "quality_status",
        "identity_confidence",
        "row_count",
        "manifest_status",
        "divergence_severity",
        "n_full_fills",
        "evidence_count",
        "failure_classification",
    ):
        if key in row:
            raw[key] = row.get(key)
    if report_kind == "paper_divergence" and isinstance(row.get("metrics_delta"), dict):
        for key, value in row["metrics_delta"].items():
            raw[f"metrics_delta.{key}"] = value
    return _metric_results(raw)


def _falsification_hits_from_source(row: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    for key in ("falsification_hits", "failure_reasons", "blocking_reasons"):
        hits.extend(_str_list(row.get(key)))
    promotion_guard = row.get("promotion_guard")
    if isinstance(promotion_guard, dict):
        hits.extend(_str_list(promotion_guard.get("blocked_by")))
    near_pass = row.get("near_pass")
    if isinstance(near_pass, dict) and near_pass.get("is_near_pass"):
        nearest = _bounded_str(near_pass.get("nearest_failed_criterion"), max_len=120)
        hits.append(nearest or "near_pass")
    if row.get("divergence_severity") == "high":
        hits.append("paper_divergence_high")
    return sorted({hit for hit in hits if hit})


def _refs_from_source(
    row: dict[str, Any],
    *,
    source_artifact: str,
    source_row_id: str,
) -> tuple[list[str], list[str]]:
    source_ref = f"{source_artifact}#{source_row_id}"
    supporting = _str_list(row.get("supporting_evidence_refs"))
    contradicting = _str_list(row.get("contradicting_evidence_refs"))
    if not supporting:
        supporting = [source_ref]
    if _falsification_hits_from_source(row) and not contradicting:
        contradicting = [source_ref]
    return (supporting, contradicting)


def _build_real_source_result(
    row: dict[str, Any],
    *,
    row_index: int,
    row_field: str,
    source_artifact: str,
    source_report_kind: str,
    authorities: dict[str, Any],
) -> dict[str, Any] | None:
    linked = _linked_ids(row, authorities)
    if linked is None:
        return None
    hypothesis_id, plan_id, run_id = linked
    source_row_id = _row_identity(row, index=row_index, row_field=row_field)
    supporting, contradicting = _refs_from_source(
        row,
        source_artifact=source_artifact,
        source_row_id=source_row_id,
    )
    result = {
        "hypothesis_id": hypothesis_id,
        "validation_plan_id": plan_id,
        "run_manifest_id": run_id,
        "status": _status_from_source(row, source_report_kind),
        "metric_results": _metrics_from_source(row, source_report_kind),
        "falsification_hits": _falsification_hits_from_source(row),
        "supporting_evidence_refs": supporting,
        "contradicting_evidence_refs": contradicting,
        "source_artifact": source_artifact,
        "source_report_kind": source_report_kind,
        "source_row_id": source_row_id,
        "source_ref": f"{source_artifact}#{source_row_id}",
    }
    return _build_result(result)


def _collect_real_source_results(
    *,
    source_artifact_paths: list[Path],
    hypothesis_artifact_path: Path,
    plan_artifact_path: Path,
    run_manifest_artifact_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    authorities, warnings = _load_link_authorities(
        hypothesis_artifact_path=hypothesis_artifact_path,
        plan_artifact_path=plan_artifact_path,
        run_manifest_artifact_path=run_manifest_artifact_path,
    )
    validation_results: list[dict[str, Any]] = []
    skipped_unlinked = 0
    for source in source_artifact_paths:
        available, payload = _read_json(source)
        if payload is None:
            if available:
                warnings.append(f"{NOTE_REAL_SOURCE_ARTIFACT_UNPARSEABLE}:{_rel(source)}")
            continue
        report_kind = _source_report_kind(payload, source)
        if report_kind not in REAL_SOURCE_REPORT_KINDS:
            warnings.append(f"real_source_artifact_unsupported:{_rel(source)}")
            continue
        row_field, rows = _rows_for_source(payload, report_kind)
        if rows is None:
            warnings.append(f"{NOTE_REAL_SOURCE_ARTIFACT_UNPARSEABLE}:{_rel(source)}")
            continue
        for index, row in enumerate(rows):
            result = _build_real_source_result(
                row,
                row_index=index,
                row_field=row_field,
                source_artifact=_rel(source),
                source_report_kind=report_kind,
                authorities=authorities,
            )
            if result is None:
                skipped_unlinked += 1
                continue
            validation_results.append(result)
    if skipped_unlinked:
        warnings.append(f"{NOTE_REAL_SOURCE_ROWS_SKIPPED}:{skipped_unlinked}")
    return (validation_results, warnings)


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
    source_artifact_paths: list[Path] | None = None,
    hypothesis_artifact_path: Path | None = None,
    plan_artifact_path: Path | None = None,
    run_manifest_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = input_artifact_path or INPUT_ARTIFACT_PATH
    available, payload = _read_json(source)
    if payload is None:
        if input_artifact_path is None:
            validation_results, validation_warnings = _collect_real_source_results(
                source_artifact_paths=list(
                    source_artifact_paths or DEFAULT_REAL_SOURCE_ARTIFACT_PATHS
                ),
                hypothesis_artifact_path=(
                    hypothesis_artifact_path or DEFAULT_HYPOTHESIS_ARTIFACT_PATH
                ),
                plan_artifact_path=plan_artifact_path or DEFAULT_PLAN_ARTIFACT_PATH,
                run_manifest_artifact_path=(
                    run_manifest_artifact_path or DEFAULT_RUN_MANIFEST_ARTIFACT_PATH
                ),
            )
            validation_results.sort(key=lambda item: item["result_id"])
            return _base_snapshot(
                generated_at_utc=generated,
                input_artifact_path=source,
                input_artifact_available=available,
                note=NOTE_RESULTS_PRESENT if validation_results else NOTE_NO_RESULTS,
                validation_results=validation_results,
                validation_warnings=validation_warnings,
            )
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
    "DEFAULT_HYPOTHESIS_ARTIFACT_PATH",
    "DEFAULT_PLAN_ARTIFACT_PATH",
    "DEFAULT_REAL_SOURCE_ARTIFACT_PATHS",
    "DEFAULT_RUN_MANIFEST_ARTIFACT_PATH",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REAL_SOURCE_REPORT_KINDS",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "STATUSES",
    "collect_snapshot",
    "main",
    "write_outputs",
]
