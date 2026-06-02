"""Read-only diagnostics for QRE validation-result linkage gaps."""

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

from reporting.qre_validation_source_linkage_contract import REQUIRED_LINKAGE_FIELDS

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_validation_result_linkage_diagnostics"

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

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_validation_result_linkage_diagnostics"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_validation_result_linkage_diagnostics/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

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
CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "linkable_direct_hypothesis_id",
    "linkable_candidate_id_match",
    "linkable_validation_plan_id_match",
    "linkable_run_manifest_id_match",
    "missing_hypothesis_id",
    "missing_validation_plan_id",
    "missing_run_manifest_id",
    "source_candidate_id_not_in_hypotheses",
    "source_asset_timeframe_ambiguous",
    "unsupported_source_schema",
    "malformed_source_row",
)
LINKABLE_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {
        "linkable_direct_hypothesis_id",
        "linkable_candidate_id_match",
        "linkable_validation_plan_id_match",
        "linkable_run_manifest_id_match",
    }
)
CANDIDATE_LINK_FIELDS: Final[tuple[str, ...]] = (
    "candidate_id",
    "strategy_id",
    "asset",
    "timeframe",
    "symbol",
    "run_id",
    "plan_id",
    "hypothesis_id",
    "validation_plan_id",
    "run_manifest_id",
)
EXAMPLE_LIMIT: Final[int] = 20

NOTE_SOURCE_ABSENT: Final[str] = "real_source_artifact_absent"
NOTE_SOURCE_UNPARSEABLE: Final[str] = "real_source_artifact_unparseable"
NOTE_SOURCE_UNSUPPORTED: Final[str] = "real_source_artifact_unsupported"
NOTE_HYPOTHESIS_AUTHORITY_ABSENT: Final[str] = "hypothesis_authority_absent"
NOTE_HYPOTHESIS_AUTHORITY_UNPARSEABLE: Final[str] = "hypothesis_authority_unparseable"
NOTE_PLAN_AUTHORITY_ABSENT: Final[str] = "validation_plan_authority_absent"
NOTE_PLAN_AUTHORITY_UNPARSEABLE: Final[str] = "validation_plan_authority_unparseable"
NOTE_RUN_AUTHORITY_ABSENT: Final[str] = "run_manifest_authority_absent"
NOTE_RUN_AUTHORITY_UNPARSEABLE: Final[str] = "run_manifest_authority_unparseable"
NOTE_INPUT_ISSUES: Final[str] = "linkage_inputs_failed_closed"
NOTE_ROWS_PRESENT: Final[str] = "linkage_diagnostics_present"
NOTE_NO_ROWS: Final[str] = "no_source_rows_available"


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


def _str_list(value: Any, *, max_items: int = 16, max_len: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        text = _bounded_str(item, max_len=max_len)
        if text:
            out.append(text)
    return out


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


def _rows_for_source(payload: dict[str, Any], report_kind: str) -> tuple[str, list[Any] | None]:
    if report_kind in {"screening_evidence", "run_candidates"}:
        rows = payload.get("candidates")
        return ("candidates", rows if isinstance(rows, list) else None)
    if report_kind in {
        "screening_results",
        "exit_quality_diagnostics",
        "candidate_readiness",
        "source_quality_readiness",
        "trend_break_invalidation",
        "no_paper_candidate_diagnostics",
    }:
        for field in ("validation_results", "rows", "results", "diagnostics", "items"):
            rows = payload.get(field)
            if isinstance(rows, list):
                return (field, rows)
        return ("", None)
    if report_kind == "qre_data_source_quality_readiness":
        rows = payload.get("rows")
        return ("rows", rows if isinstance(rows, list) else None)
    if report_kind == "qre_research_diagnostics_loop":
        rows = payload.get("diagnostic_chain")
        return ("diagnostic_chain", rows if isinstance(rows, list) else None)
    if report_kind == "paper_divergence":
        rows = payload.get("per_candidate")
        return ("per_candidate", rows if isinstance(rows, list) else None)
    if report_kind == "research_latest":
        rows = payload.get("results")
        return ("results", rows if isinstance(rows, list) else None)
    for field in (
        "validation_results",
        "rows",
        "results",
        "candidates",
        "diagnostics",
        "items",
        "per_candidate",
        "diagnostic_chain",
    ):
        rows = payload.get(field)
        if isinstance(rows, list):
            return (field, rows)
    return ("", None)


def _candidate_field_values(row: dict[str, Any]) -> dict[str, str]:
    timeframe = _bounded_str(row.get("timeframe"), max_len=80) or _bounded_str(
        row.get("interval"), max_len=80
    )
    plan_id = _bounded_str(row.get("plan_id"), max_len=160)
    validation_plan_id = _bounded_str(row.get("validation_plan_id"), max_len=160)
    run_id = _bounded_str(row.get("run_id"), max_len=160)
    run_manifest_id = _bounded_str(row.get("run_manifest_id"), max_len=160)
    values = {
        "candidate_id": _bounded_str(row.get("candidate_id"), max_len=220),
        "strategy_id": _bounded_str(row.get("strategy_id"), max_len=160),
        "asset": _bounded_str(row.get("asset"), max_len=100),
        "timeframe": timeframe,
        "symbol": _bounded_str(row.get("symbol"), max_len=100),
        "run_id": run_id,
        "plan_id": plan_id,
        "hypothesis_id": _bounded_str(row.get("hypothesis_id"), max_len=160),
        "validation_plan_id": validation_plan_id or plan_id,
        "run_manifest_id": run_manifest_id or run_id,
    }
    return {key: values[key] for key in CANDIDATE_LINK_FIELDS if values[key]}


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


def _supporting_ref_source_ids(hypothesis: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for ref in _str_list(hypothesis.get("supporting_evidence_refs"), max_items=64, max_len=320):
        _, marker, suffix = ref.partition("#")
        if marker and suffix:
            out.add(suffix)
    return out


def _read_authorities(
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
    manifests: list[dict[str, Any]] = []
    if hyp_payload is not None and hyp_payload.get("report_kind") == "qre_hypothesis_candidates":
        raw = hyp_payload.get("hypotheses")
        if isinstance(raw, list) and all(isinstance(item, dict) for item in raw):
            hypotheses = raw
        else:
            warnings.append(NOTE_HYPOTHESIS_AUTHORITY_UNPARSEABLE)
    elif hyp_available:
        warnings.append(NOTE_HYPOTHESIS_AUTHORITY_UNPARSEABLE)
    else:
        warnings.append(NOTE_HYPOTHESIS_AUTHORITY_ABSENT)

    if (
        plan_payload is not None
        and plan_payload.get("report_kind") == "qre_hypothesis_validation_plan"
    ):
        raw = plan_payload.get("validation_plans")
        if isinstance(raw, list) and all(isinstance(item, dict) for item in raw):
            plans = raw
        else:
            warnings.append(NOTE_PLAN_AUTHORITY_UNPARSEABLE)
    elif plan_available:
        warnings.append(NOTE_PLAN_AUTHORITY_UNPARSEABLE)
    else:
        warnings.append(NOTE_PLAN_AUTHORITY_ABSENT)

    if run_payload is not None and run_payload.get("report_kind") == "qre_research_run_manifest":
        raw = run_payload.get("run_manifests")
        if isinstance(raw, list) and all(isinstance(item, dict) for item in raw):
            manifests = raw
        else:
            warnings.append(NOTE_RUN_AUTHORITY_UNPARSEABLE)
    elif run_available:
        warnings.append(NOTE_RUN_AUTHORITY_UNPARSEABLE)
    else:
        warnings.append(NOTE_RUN_AUTHORITY_ABSENT)

    hypothesis_by_id: dict[str, dict[str, Any]] = {}
    hypothesis_by_source_id: dict[str, str] = {}
    for item in hypotheses:
        hypothesis_id = _bounded_str(item.get("hypothesis_id"), max_len=160)
        if not hypothesis_id:
            continue
        hypothesis_by_id[hypothesis_id] = item
        source_ids = {
            _bounded_str(item.get("candidate_id"), max_len=220),
            _bounded_str(item.get("source_candidate_id"), max_len=220),
            _bounded_str(item.get("source_observation_id"), max_len=220),
        }
        source_ids.update(_supporting_ref_source_ids(item))
        for source_id in sorted(value for value in source_ids if value):
            hypothesis_by_source_id.setdefault(source_id, hypothesis_id)

    plan_by_id: dict[str, dict[str, Any]] = {}
    plans_by_hypothesis: dict[str, list[str]] = {}
    for item in plans:
        plan_id = _bounded_str(item.get("validation_plan_id"), max_len=160)
        hypothesis_id = _bounded_str(item.get("hypothesis_id"), max_len=160)
        if not plan_id:
            continue
        plan_by_id[plan_id] = item
        if hypothesis_id:
            plans_by_hypothesis.setdefault(hypothesis_id, []).append(plan_id)
    for values in plans_by_hypothesis.values():
        values.sort()

    manifest_by_id: dict[str, dict[str, Any]] = {}
    manifests_by_plan: dict[str, list[str]] = {}
    for item in manifests:
        manifest_id = _bounded_str(item.get("run_manifest_id"), max_len=160)
        plan_id = _bounded_str(item.get("target_validation_plan_id"), max_len=160)
        if not manifest_id:
            continue
        manifest_by_id[manifest_id] = item
        if plan_id:
            manifests_by_plan.setdefault(plan_id, []).append(manifest_id)
    for values in manifests_by_plan.values():
        values.sort()

    return (
        {
            "hypothesis_by_id": hypothesis_by_id,
            "hypothesis_by_source_id": hypothesis_by_source_id,
            "plan_by_id": plan_by_id,
            "plans_by_hypothesis": plans_by_hypothesis,
            "manifest_by_id": manifest_by_id,
            "manifests_by_plan": manifests_by_plan,
        },
        warnings,
    )


def _single(values: list[str]) -> str:
    return values[0] if len(values) == 1 else ""


def _resolve_linkage(
    fields: dict[str, str],
    authorities: dict[str, Any],
) -> tuple[dict[str, str], list[str]]:
    classifications: list[str] = []
    resolved: dict[str, str] = {}

    hypothesis_id = fields.get("hypothesis_id", "")
    if hypothesis_id and hypothesis_id in authorities["hypothesis_by_id"]:
        resolved["hypothesis_id"] = hypothesis_id
        classifications.append("linkable_direct_hypothesis_id")

    candidate_id = fields.get("candidate_id", "")
    if candidate_id:
        candidate_hypothesis_id = authorities["hypothesis_by_source_id"].get(candidate_id, "")
        if candidate_hypothesis_id:
            resolved.setdefault("hypothesis_id", candidate_hypothesis_id)
            classifications.append("linkable_candidate_id_match")
        elif "linkable_direct_hypothesis_id" not in classifications:
            classifications.append("source_candidate_id_not_in_hypotheses")

    plan_id = fields.get("validation_plan_id", "")
    if plan_id and plan_id in authorities["plan_by_id"]:
        plan = authorities["plan_by_id"][plan_id]
        classifications.append("linkable_validation_plan_id_match")
        resolved["validation_plan_id"] = plan_id
        resolved.setdefault("hypothesis_id", _bounded_str(plan.get("hypothesis_id"), max_len=160))

    run_id = fields.get("run_manifest_id", "")
    if run_id and run_id in authorities["manifest_by_id"]:
        manifest = authorities["manifest_by_id"][run_id]
        classifications.append("linkable_run_manifest_id_match")
        resolved["run_manifest_id"] = run_id
        resolved.setdefault(
            "validation_plan_id",
            _bounded_str(manifest.get("target_validation_plan_id"), max_len=160),
        )
        resolved.setdefault(
            "hypothesis_id",
            _bounded_str(manifest.get("target_hypothesis_id"), max_len=160),
        )

    if "hypothesis_id" in resolved and "validation_plan_id" not in resolved:
        derived_plan = _single(
            authorities["plans_by_hypothesis"].get(resolved["hypothesis_id"], [])
        )
        if derived_plan:
            resolved["validation_plan_id"] = derived_plan
            if "linkable_validation_plan_id_match" not in classifications:
                classifications.append("linkable_validation_plan_id_match")

    if "validation_plan_id" in resolved and "run_manifest_id" not in resolved:
        derived_run = _single(
            authorities["manifests_by_plan"].get(resolved["validation_plan_id"], [])
        )
        if derived_run:
            resolved["run_manifest_id"] = derived_run
            if "linkable_run_manifest_id_match" not in classifications:
                classifications.append("linkable_run_manifest_id_match")

    if not fields.get("hypothesis_id"):
        classifications.append("missing_hypothesis_id")
    if not fields.get("validation_plan_id"):
        classifications.append("missing_validation_plan_id")
    if not fields.get("run_manifest_id"):
        classifications.append("missing_run_manifest_id")

    only_asset_timeframe = (
        not fields.get("candidate_id")
        and not fields.get("hypothesis_id")
        and not fields.get("validation_plan_id")
        and not fields.get("run_manifest_id")
        and (fields.get("asset") or fields.get("symbol"))
        and fields.get("timeframe")
    )
    if only_asset_timeframe:
        classifications = [item for item in classifications if item not in LINKABLE_CLASSIFICATIONS]
        classifications.append("source_asset_timeframe_ambiguous")
        resolved = {}

    ordered = [item for item in CLASSIFICATIONS if item in set(classifications)]
    return (resolved, ordered)


def _primary_classification(classifications: list[str]) -> str:
    for name in (
        "malformed_source_row",
        "unsupported_source_schema",
        "linkable_direct_hypothesis_id",
        "linkable_candidate_id_match",
        "linkable_validation_plan_id_match",
        "linkable_run_manifest_id_match",
        "source_candidate_id_not_in_hypotheses",
        "source_asset_timeframe_ambiguous",
        "missing_hypothesis_id",
        "missing_validation_plan_id",
        "missing_run_manifest_id",
    ):
        if name in classifications:
            return name
    return "unsupported_source_schema"


def _example(
    *,
    source_artifact: str,
    source_report_kind: str,
    row_field: str,
    row_index: int,
    row_identity: str,
    classifications: list[str],
    fields: dict[str, str],
    resolved: dict[str, str],
    skipped_unlinked: bool,
) -> dict[str, Any]:
    return {
        "source_artifact": source_artifact,
        "source_report_kind": source_report_kind,
        "row_ref": f"{row_field}[{row_index}]",
        "source_row_id": _bounded_str(row_identity, max_len=220),
        "classifications": classifications,
        "candidate_link_fields": fields,
        "resolved_linkage": resolved,
        "skipped_unlinked": skipped_unlinked,
    }


def _diagnose_row(
    row: Any,
    *,
    row_index: int,
    row_field: str,
    source_artifact: str,
    source_report_kind: str,
    supported_schema: bool,
    authorities: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(row, dict):
        classifications = ["malformed_source_row"]
        return _example(
            source_artifact=source_artifact,
            source_report_kind=source_report_kind,
            row_field=row_field or "rows",
            row_index=row_index,
            row_identity=f"{row_field or 'rows'}[{row_index}]",
            classifications=classifications,
            fields={},
            resolved={},
            skipped_unlinked=True,
        )

    fields = _candidate_field_values(row)
    row_identity = _row_identity(row, index=row_index, row_field=row_field or "rows")
    if not supported_schema:
        classifications = ["unsupported_source_schema"]
        return _example(
            source_artifact=source_artifact,
            source_report_kind=source_report_kind,
            row_field=row_field or "rows",
            row_index=row_index,
            row_identity=row_identity,
            classifications=classifications,
            fields=fields,
            resolved={},
            skipped_unlinked=True,
        )

    resolved, classifications = _resolve_linkage(fields, authorities)
    complete = all(
        resolved.get(key) for key in ("hypothesis_id", "validation_plan_id", "run_manifest_id")
    )
    return _example(
        source_artifact=source_artifact,
        source_report_kind=source_report_kind,
        row_field=row_field or "rows",
        row_index=row_index,
        row_identity=row_identity,
        classifications=classifications,
        fields=fields,
        resolved=resolved if complete else resolved,
        skipped_unlinked=not complete,
    )


def _empty_counts() -> dict[str, Any]:
    return {
        "total_source_rows": 0,
        "skipped_unlinked_total": 0,
        "linkage_complete_total": 0,
        "by_source_artifact": {},
        "by_source_report_kind": {},
        "by_classification": {name: 0 for name in CLASSIFICATIONS},
        "by_primary_classification": {name: 0 for name in CLASSIFICATIONS},
    }


def _counts(
    examples: list[dict[str, Any]], all_row_diagnostics: list[dict[str, Any]]
) -> dict[str, Any]:
    out = _empty_counts()
    out["total_source_rows"] = len(all_row_diagnostics)
    out["skipped_unlinked_total"] = sum(
        1 for item in all_row_diagnostics if item["skipped_unlinked"]
    )
    out["linkage_complete_total"] = out["total_source_rows"] - out["skipped_unlinked_total"]
    out["by_source_artifact"] = dict(
        sorted(Counter(item["source_artifact"] for item in all_row_diagnostics).items())
    )
    out["by_source_report_kind"] = dict(
        sorted(Counter(item["source_report_kind"] for item in all_row_diagnostics).items())
    )
    class_counter: Counter[str] = Counter()
    primary_counter: Counter[str] = Counter()
    for item in all_row_diagnostics:
        class_counter.update(item["classifications"])
        primary_counter[_primary_classification(item["classifications"])] += 1
    out["by_classification"] = {name: class_counter.get(name, 0) for name in CLASSIFICATIONS}
    out["by_primary_classification"] = {
        name: primary_counter.get(name, 0) for name in CLASSIFICATIONS
    }
    if len(examples) > EXAMPLE_LIMIT:
        raise ValueError("internal error: diagnostic examples exceeded bound")
    return out


def _collect_row_diagnostics(
    *,
    source_artifact_paths: list[Path],
    authorities: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], dict[str, dict[str, Any]]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    source_artifacts: dict[str, dict[str, Any]] = {}
    for source in source_artifact_paths:
        source_rel = _rel(source)
        available, payload = _read_json(source)
        if payload is None:
            if available:
                warnings.append(f"{NOTE_SOURCE_UNPARSEABLE}:{source_rel}")
                status = "unparseable"
            else:
                warnings.append(f"{NOTE_SOURCE_ABSENT}:{source_rel}")
                status = "absent"
            source_artifacts[source_rel] = {
                "available": available,
                "status": status,
                "source_report_kind": "unknown",
                "row_count": 0,
            }
            continue

        report_kind = _source_report_kind(payload, source)
        row_field, source_rows = _rows_for_source(payload, report_kind)
        supported_schema = report_kind in REAL_SOURCE_REPORT_KINDS
        if not supported_schema:
            warnings.append(f"{NOTE_SOURCE_UNSUPPORTED}:{source_rel}")
        if source_rows is None:
            warnings.append(f"{NOTE_SOURCE_UNPARSEABLE}:{source_rel}")
            source_artifacts[source_rel] = {
                "available": True,
                "status": "unparseable",
                "source_report_kind": report_kind,
                "row_count": 0,
            }
            continue

        source_artifacts[source_rel] = {
            "available": True,
            "status": "read",
            "source_report_kind": report_kind,
            "row_field": row_field,
            "row_count": len(source_rows),
        }
        for index, row in enumerate(source_rows):
            rows.append(
                _diagnose_row(
                    row,
                    row_index=index,
                    row_field=row_field,
                    source_artifact=source_rel,
                    source_report_kind=report_kind,
                    supported_schema=supported_schema,
                    authorities=authorities,
                )
            )
    rows.sort(
        key=lambda item: (
            item["source_artifact"],
            item["source_report_kind"],
            item["row_ref"],
            item["source_row_id"],
        )
    )
    return (rows, warnings, source_artifacts)


def _deterministic_mapping_assessment(
    *,
    counts: dict[str, Any],
    validation_warnings: list[str],
) -> dict[str, Any]:
    if validation_warnings and counts["skipped_unlinked_total"]:
        return {
            "deterministic_mapping_possible": False,
            "explanation": (
                "No. One or more source/reference artifacts are absent, malformed, or "
                "unsupported, and at least one source row lacks complete deterministic "
                "linkage to hypothesis_id, validation_plan_id, and run_manifest_id."
            ),
        }
    if validation_warnings:
        return {
            "deterministic_mapping_possible": False,
            "explanation": (
                "No. One or more source/reference artifacts are absent, malformed, or "
                "unsupported, so the diagnostic fails closed."
            ),
        }
    if counts["total_source_rows"] == 0:
        return {
            "deterministic_mapping_possible": False,
            "explanation": "No. No source rows are available to map.",
        }
    if counts["skipped_unlinked_total"]:
        return {
            "deterministic_mapping_possible": False,
            "explanation": (
                "No. At least one source row lacks a complete deterministic linkage to "
                "hypothesis_id, validation_plan_id, and run_manifest_id."
            ),
        }
    return {
        "deterministic_mapping_possible": True,
        "explanation": (
            "Yes. Every supported source row resolves through explicit hypothesis, "
            "candidate, validation-plan, or run-manifest linkage keys."
        ),
    }


def _recommended_linkage_keys() -> list[dict[str, Any]]:
    targets = {
        "hypothesis_id": {
            "target_artifact": "logs/qre_hypothesis_candidates/latest.json",
            "target_field": "hypotheses[].hypothesis_id",
            "requirement": "stable exact identifier",
        },
        "validation_plan_id": {
            "target_artifact": "logs/qre_hypothesis_validation_plans/latest.json",
            "target_field": "validation_plans[].validation_plan_id",
            "requirement": "stable exact validation plan identifier",
        },
        "run_manifest_id": {
            "target_artifact": "logs/qre_research_run_manifest/latest.json",
            "target_field": "run_manifests[].run_manifest_id",
            "requirement": "stable exact operator-gated run manifest identifier",
        },
        "source_artifact": {
            "target_artifact": "source artifact path",
            "target_field": "source_artifact",
            "requirement": "stable exact source artifact identifier",
        },
        "source_report_kind": {
            "target_artifact": "source artifact payload",
            "target_field": "report_kind",
            "requirement": "stable exact source report kind",
        },
        "source_row_id": {
            "target_artifact": "source artifact row",
            "target_field": "source_row_id",
            "requirement": "stable exact source row identifier",
        },
    }
    return [{"source_field": field, **targets[field]} for field in REQUIRED_LINKAGE_FIELDS]


def collect_snapshot(
    *,
    source_artifact_paths: list[Path] | None = None,
    hypothesis_artifact_path: Path | None = None,
    plan_artifact_path: Path | None = None,
    run_manifest_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    authorities, authority_warnings = _read_authorities(
        hypothesis_artifact_path=hypothesis_artifact_path or DEFAULT_HYPOTHESIS_ARTIFACT_PATH,
        plan_artifact_path=plan_artifact_path or DEFAULT_PLAN_ARTIFACT_PATH,
        run_manifest_artifact_path=run_manifest_artifact_path or DEFAULT_RUN_MANIFEST_ARTIFACT_PATH,
    )
    row_diagnostics, source_warnings, source_artifacts = _collect_row_diagnostics(
        source_artifact_paths=list(source_artifact_paths or DEFAULT_REAL_SOURCE_ARTIFACT_PATHS),
        authorities=authorities,
    )
    examples = [
        item
        for item in row_diagnostics
        if item["skipped_unlinked"] or not set(item["classifications"]) <= LINKABLE_CLASSIFICATIONS
    ][:EXAMPLE_LIMIT]
    counts = _counts(examples, row_diagnostics)
    validation_warnings = sorted(set(authority_warnings + source_warnings))
    assessment = _deterministic_mapping_assessment(
        counts=counts,
        validation_warnings=validation_warnings,
    )
    note = (
        NOTE_INPUT_ISSUES
        if validation_warnings
        else NOTE_ROWS_PRESENT
        if row_diagnostics
        else NOTE_NO_ROWS
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "output_artifact_path": OUTPUT_ARTIFACT_RELATIVE_PATH,
        "note": note,
        "read_only": True,
        "source_artifacts": source_artifacts,
        "reference_artifacts": {
            "hypotheses": _rel(hypothesis_artifact_path or DEFAULT_HYPOTHESIS_ARTIFACT_PATH),
            "validation_plans": _rel(plan_artifact_path or DEFAULT_PLAN_ARTIFACT_PATH),
            "run_manifests": _rel(run_manifest_artifact_path or DEFAULT_RUN_MANIFEST_ARTIFACT_PATH),
        },
        "candidate_link_fields_inspected": list(CANDIDATE_LINK_FIELDS),
        "counts": counts,
        "skipped_examples": examples,
        "recommended_linkage_keys": _recommended_linkage_keys(),
        "deterministic_mapping_possible": assessment["deterministic_mapping_possible"],
        "deterministic_mapping_explanation": assessment["explanation"],
        "validation_warnings": validation_warnings,
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


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE validation linkage diagnostics dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_validation_result_linkage_diagnostics.",
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
        prog="reporting.qre_validation_result_linkage_diagnostics",
        description="Explain why QRE validation-result source rows are unlinked.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "CLASSIFICATIONS",
    "DEFAULT_HYPOTHESIS_ARTIFACT_PATH",
    "DEFAULT_PLAN_ARTIFACT_PATH",
    "DEFAULT_REAL_SOURCE_ARTIFACT_PATHS",
    "DEFAULT_RUN_MANIFEST_ARTIFACT_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
