"""Read-only diagnostics for executable/QRE hypothesis identity gaps."""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import os
import tempfile
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from reporting.qre_executable_hypothesis_identity_bridge_contract import (
    BRIDGE_STATUS_EXACT,
    build_bridge_index,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_executable_hypothesis_identity_bridge_diagnostics"

DEFAULT_HYPOTHESIS_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_candidates" / "latest.json"
)
DEFAULT_PLAN_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_plans" / "latest.json"
)
DEFAULT_RUN_MANIFEST_ARTIFACT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_research_run_manifest" / "latest.json"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_executable_hypothesis_identity_bridge"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_executable_hypothesis_identity_bridge/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

SAMPLE_LIMIT: Final[int] = 20
PRESET_ROW_LIMIT: Final[int] = 100
ID_LIMIT: Final[int] = 100
WARNING_LIMIT: Final[int] = 50

PRESETS_SOURCE_PATH: Final[Path] = REPO_ROOT / "research" / "presets.py"

FINAL_RECOMMENDATION_BRIDGE_REQUIRED: Final[str] = (
    "executable_hypothesis_identity_bridge_required_before_regeneration"
)
FINAL_RECOMMENDATION_REGENERATION_LINKAGE_EXPECTED: Final[str] = (
    "runtime_regeneration_linkage_expected_for_executable_hypothesis_ids"
)
FINAL_RECOMMENDATION_BRIDGE_READY: Final[str] = (
    "executable_hypothesis_identity_bridge_ready_for_regeneration"
)
FINAL_RECOMMENDATION_INPUTS_FAILED_CLOSED: Final[str] = "inputs_failed_closed_before_regeneration"

PRIMARY_BLOCKER_EXECUTABLE_ID_MISSING: Final[str] = "executable_hypothesis_id_not_in_qre_authority"
PRIMARY_BLOCKER_QRE_AUTHORITY_UNAVAILABLE: Final[str] = "qre_authority_unavailable"
PRIMARY_BLOCKER_NO_EXECUTABLE_IDS: Final[str] = "no_executable_hypothesis_ids"
PRIMARY_BLOCKER_NONE: Final[str] = "no_primary_blocker"

RECOMMENDED_BRIDGE_KEYS: Final[tuple[str, ...]] = (
    "executable_hypothesis_id",
    "qre_hypothesis_id",
    "source_hypothesis_id",
    "strategy_family",
    "strategy_template_id",
    "preset_name",
    "validation_plan_id",
    "run_manifest_id",
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _bounded_unique(values: list[str], *, max_items: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _bounded_str(value, max_len=160)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _read_json(path: Path) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return (False, None, f"qre_artifact_missing:{_rel(path)}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return (True, None, f"qre_artifact_malformed:{_rel(path)}")
    if not isinstance(parsed, dict):
        return (True, None, f"qre_artifact_malformed:{_rel(path)}")
    return (True, parsed, None)


def _safe_dict_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return None
    return rows


def _build_qre_validation_linkage_authority(
    *,
    hypothesis_candidates_payload: dict[str, Any] | None,
    validation_plans_payload: dict[str, Any] | None,
    run_manifest_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    hypotheses = _safe_dict_rows(hypothesis_candidates_payload, "hypotheses")
    plans = _safe_dict_rows(validation_plans_payload, "validation_plans")
    manifests = _safe_dict_rows(run_manifest_payload, "run_manifests")

    if (
        not isinstance(hypothesis_candidates_payload, dict)
        or hypothesis_candidates_payload.get("report_kind") != "qre_hypothesis_candidates"
        or hypotheses is None
    ):
        warnings.append("qre_hypothesis_authority_absent_or_unparseable")
    if (
        not isinstance(validation_plans_payload, dict)
        or validation_plans_payload.get("report_kind") != "qre_hypothesis_validation_plan"
        or plans is None
    ):
        warnings.append("qre_validation_plan_authority_absent_or_unparseable")
    if (
        not isinstance(run_manifest_payload, dict)
        or run_manifest_payload.get("report_kind") != "qre_research_run_manifest"
        or manifests is None
    ):
        warnings.append("qre_run_manifest_authority_absent_or_unparseable")

    if warnings:
        return {
            "available": False,
            "warnings": warnings,
            "by_hypothesis_id": {},
            "by_executable_hypothesis_id": {},
            "bridge_summary": {
                "exact_bridge_count": 0,
                "ambiguous_bridge_count": 0,
                "unsafe_bridge_count": 0,
            },
        }

    hypothesis_ids = {
        _bounded_str(item.get("hypothesis_id"), max_len=160)
        for item in hypotheses or []
        if _bounded_str(item.get("hypothesis_id"), max_len=160)
    }
    plans_by_hypothesis: dict[str, list[str]] = {}
    for item in plans or []:
        hypothesis_id = _bounded_str(item.get("hypothesis_id"), max_len=160)
        plan_id = _bounded_str(item.get("validation_plan_id"), max_len=160)
        if hypothesis_id in hypothesis_ids and plan_id:
            plans_by_hypothesis.setdefault(hypothesis_id, []).append(plan_id)
    for values in plans_by_hypothesis.values():
        values.sort()

    manifests_by_plan: dict[str, list[str]] = {}
    for item in manifests or []:
        plan_id = _bounded_str(item.get("target_validation_plan_id"), max_len=160)
        manifest_id = _bounded_str(item.get("run_manifest_id"), max_len=160)
        if plan_id and manifest_id:
            manifests_by_plan.setdefault(plan_id, []).append(manifest_id)
    for values in manifests_by_plan.values():
        values.sort()

    by_hypothesis_id: dict[str, dict[str, Any]] = {}
    for hypothesis_id in sorted(hypothesis_ids):
        plan_ids = plans_by_hypothesis.get(hypothesis_id, [])
        if not plan_ids:
            by_hypothesis_id[hypothesis_id] = {
                "status": "unlinked_missing_validation_plan_id",
                "warnings": ["qre_validation_plan_id_not_found_for_hypothesis"],
            }
            continue
        if len(plan_ids) != 1:
            by_hypothesis_id[hypothesis_id] = {
                "status": "unlinked_ambiguous_validation_plan_id",
                "warnings": ["qre_validation_plan_id_not_unique_for_hypothesis"],
            }
            continue

        plan_id = plan_ids[0]
        manifest_ids = manifests_by_plan.get(plan_id, [])
        if not manifest_ids:
            by_hypothesis_id[hypothesis_id] = {
                "status": "unlinked_missing_run_manifest_id",
                "validation_plan_id": plan_id,
                "warnings": ["qre_run_manifest_id_not_found_for_validation_plan"],
            }
            continue
        if len(manifest_ids) != 1:
            by_hypothesis_id[hypothesis_id] = {
                "status": "unlinked_ambiguous_run_manifest_id",
                "validation_plan_id": plan_id,
                "warnings": ["qre_run_manifest_id_not_unique_for_validation_plan"],
            }
            continue

        by_hypothesis_id[hypothesis_id] = {
            "status": "linked_exact_ids",
            "hypothesis_id": hypothesis_id,
            "validation_plan_id": plan_id,
            "run_manifest_id": manifest_ids[0],
            "warnings": [],
        }

    bridge_rows: list[dict[str, Any]] = []
    for item in hypotheses or []:
        executable_hypothesis_id = _bounded_str(item.get("executable_hypothesis_id"), max_len=160)
        qre_hypothesis_id = _bounded_str(item.get("hypothesis_id"), max_len=160)
        entry = by_hypothesis_id.get(qre_hypothesis_id)
        if not executable_hypothesis_id or not qre_hypothesis_id:
            continue
        entry = entry if isinstance(entry, dict) else {}
        bridge_rows.append(
            {
                "executable_hypothesis_id": executable_hypothesis_id,
                "qre_hypothesis_id": qre_hypothesis_id,
                "source_hypothesis_id": item.get("source_hypothesis_id"),
                "strategy_family": item.get("strategy_family"),
                "strategy_template_id": item.get("strategy_template_id"),
                "preset_name": item.get("preset_name"),
                "validation_plan_id": entry.get("validation_plan_id"),
                "run_manifest_id": entry.get("run_manifest_id"),
            }
        )
    bridge_index = build_bridge_index(
        bridge_rows,
        qre_authority={"by_hypothesis_id": by_hypothesis_id},
    )
    raw_by_executable = bridge_index.get("by_executable_hypothesis_id")
    by_executable_hypothesis_id = {
        key: value
        for key, value in (raw_by_executable.items() if isinstance(raw_by_executable, dict) else [])
        if isinstance(value, dict)
        and value.get("safe_to_bridge") is True
        and value.get("bridge_status") == BRIDGE_STATUS_EXACT
    }

    return {
        "available": True,
        "warnings": [],
        "by_hypothesis_id": by_hypothesis_id,
        "by_executable_hypothesis_id": by_executable_hypothesis_id,
        "bridge_summary": bridge_index.get(
            "bridge_summary",
            {
                "exact_bridge_count": 0,
                "ambiguous_bridge_count": 0,
                "unsafe_bridge_count": 0,
            },
        ),
    }


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _research_preset_from_call(node: ast.Call) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": True,
        "diagnostic_only": False,
        "excluded_from_daily_scheduler": False,
        "excluded_from_candidate_promotion": False,
        "status": "stable",
        "preset_class": "experimental",
        "hypothesis_id": None,
    }
    fields = dict(defaults)
    for keyword in node.keywords:
        if keyword.arg in fields or keyword.arg == "name":
            fields[str(keyword.arg)] = _literal(keyword.value)
    return fields


def _presets_from_source(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return ([], [f"presets_source_missing:{_rel(path)}"])
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ([], [f"presets_source_malformed:{_rel(path)}"])

    presets: list[dict[str, Any]] = []
    for node in tree.body:
        is_presets_assign = isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PRESETS" for target in node.targets
        )
        is_presets_ann_assign = isinstance(node, ast.AnnAssign) and (
            isinstance(node.target, ast.Name) and node.target.id == "PRESETS"
        )
        if not is_presets_assign and not is_presets_ann_assign:
            continue
        value = node.value
        if not isinstance(value, ast.Tuple):
            return ([], [f"presets_source_malformed:{_rel(path)}"])
        for item in value.elts:
            if not isinstance(item, ast.Call):
                continue
            func = item.func
            if isinstance(func, ast.Name) and func.id == "ResearchPreset":
                presets.append(_research_preset_from_call(item))
        return (presets, [])
    return ([], [f"presets_source_malformed:{_rel(path)}"])


def _load_default_presets() -> tuple[Any, list[str]]:
    return _presets_from_source(PRESETS_SOURCE_PATH)


def _get_field(preset: Any, field: str, default: Any = None) -> Any:
    if isinstance(preset, dict):
        return preset.get(field, default)
    return getattr(preset, field, default)


def _bool_field(preset: Any, field: str) -> bool:
    return bool(_get_field(preset, field, False))


def _preset_row(
    preset: Any,
    *,
    qre_by_hypothesis_id: dict[str, Any],
    qre_by_executable_hypothesis_id: dict[str, Any],
) -> dict[str, Any]:
    hypothesis_id = _bounded_str(_get_field(preset, "hypothesis_id"), max_len=160)
    direct_entry = qre_by_hypothesis_id.get(hypothesis_id) if hypothesis_id else None
    bridge_entry = qre_by_executable_hypothesis_id.get(hypothesis_id) if hypothesis_id else None
    entry = direct_entry if isinstance(direct_entry, dict) else bridge_entry
    linkage_mode = None
    if isinstance(direct_entry, dict):
        linkage_mode = "direct_qre_hypothesis_id"
    elif isinstance(bridge_entry, dict):
        linkage_mode = "executable_hypothesis_bridge"
    return {
        "preset_name": _bounded_str(_get_field(preset, "name"), max_len=160),
        "enabled": _bool_field(preset, "enabled"),
        "diagnostic_only": _bool_field(preset, "diagnostic_only"),
        "excluded_from_daily_scheduler": _bool_field(preset, "excluded_from_daily_scheduler"),
        "excluded_from_candidate_promotion": _bool_field(
            preset, "excluded_from_candidate_promotion"
        ),
        "status": _bounded_str(_get_field(preset, "status"), max_len=80),
        "preset_class": _bounded_str(_get_field(preset, "preset_class"), max_len=80),
        "hypothesis_id": hypothesis_id or None,
        "hypothesis_id_present_in_qre_authority": bool(entry),
        "qre_authority_linkage_mode": linkage_mode,
        "qre_authority_status": (
            _bounded_str(entry.get("status") or entry.get("bridge_status"), max_len=80)
            if isinstance(entry, dict)
            else None
        ),
    }


def _coerce_presets(presets: Any) -> tuple[list[Any], list[str]]:
    if presets is None:
        loaded, warnings = _load_default_presets()
        presets = loaded
    else:
        warnings = []
    if isinstance(presets, str) or not hasattr(presets, "__iter__"):
        return ([], [*warnings, "presets_unavailable_or_malformed"])
    return (list(presets), warnings)


def _authority_snapshot(
    *,
    hypothesis_artifact_path: Path,
    plan_artifact_path: Path,
    run_manifest_artifact_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    _hyp_available, hypothesis_payload, hyp_warning = _read_json(hypothesis_artifact_path)
    _plan_available, plan_payload, plan_warning = _read_json(plan_artifact_path)
    _run_available, run_payload, run_warning = _read_json(run_manifest_artifact_path)
    for warning in (hyp_warning, plan_warning, run_warning):
        if warning:
            warnings.append(warning)

    authority = _build_qre_validation_linkage_authority(
        hypothesis_candidates_payload=hypothesis_payload,
        validation_plans_payload=plan_payload,
        run_manifest_payload=run_payload,
    )
    authority_warnings = [
        _bounded_str(item, max_len=160)
        for item in authority.get("warnings", [])
        if _bounded_str(item, max_len=160)
    ]
    warnings.extend(authority_warnings)

    by_hypothesis_id_raw = authority.get("by_hypothesis_id")
    by_hypothesis_id = by_hypothesis_id_raw if isinstance(by_hypothesis_id_raw, dict) else {}
    by_executable_raw = authority.get("by_executable_hypothesis_id")
    by_executable_hypothesis_id = by_executable_raw if isinstance(by_executable_raw, dict) else {}
    status_counter: Counter[str] = Counter()
    for entry in by_hypothesis_id.values():
        if isinstance(entry, dict):
            status = _bounded_str(entry.get("status"), max_len=80) or "unknown"
        else:
            status = "malformed_authority_entry"
        status_counter[status] += 1

    qre_ids = sorted(_bounded_str(value, max_len=160) for value in by_hypothesis_id)
    qre_ids = [value for value in qre_ids if value]
    executable_ids = sorted(
        _bounded_str(value, max_len=160) for value in by_executable_hypothesis_id
    )
    executable_ids = [value for value in executable_ids if value]
    bridge_summary = authority.get("bridge_summary")
    if not isinstance(bridge_summary, dict):
        bridge_summary = {
            "exact_bridge_count": 0,
            "ambiguous_bridge_count": 0,
            "unsafe_bridge_count": 0,
        }
    snapshot = {
        "available": bool(authority.get("available")),
        "warnings": _bounded_unique(authority_warnings, max_items=WARNING_LIMIT),
        "total_hypotheses": len(by_hypothesis_id),
        "linked_exact_ids": status_counter.get("linked_exact_ids", 0),
        "executable_bridge_summary": bridge_summary,
        "sample_executable_hypothesis_ids": executable_ids[:SAMPLE_LIMIT],
        "status_counts": dict(sorted(status_counter.items())),
        "sample_qre_hypothesis_ids": qre_ids[:SAMPLE_LIMIT],
    }
    return (
        snapshot,
        by_hypothesis_id,
        by_executable_hypothesis_id,
        _bounded_unique(warnings, max_items=WARNING_LIMIT),
    )


def _presets_snapshot(
    *,
    presets: Any,
    qre_by_hypothesis_id: dict[str, Any],
    qre_by_executable_hypothesis_id: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    preset_items, warnings = _coerce_presets(presets)
    rows = [
        _preset_row(
            preset,
            qre_by_hypothesis_id=qre_by_hypothesis_id,
            qre_by_executable_hypothesis_id=qre_by_executable_hypothesis_id,
        )
        for preset in preset_items[:PRESET_ROW_LIMIT]
    ]
    executable_ids = _bounded_unique(
        [str(row["hypothesis_id"]) for row in rows if row["enabled"] and row["hypothesis_id"]],
        max_items=ID_LIMIT,
    )
    return (
        {
            "total_presets": len(preset_items),
            "enabled_presets": sum(1 for row in rows if row["enabled"]),
            "executable_presets_with_hypothesis_id": sum(
                1 for row in rows if row["enabled"] and row["hypothesis_id"]
            ),
            "executable_hypothesis_ids": executable_ids,
            "per_preset": rows,
            "per_preset_truncated": len(preset_items) > PRESET_ROW_LIMIT,
        },
        warnings,
    )


def _reason_codes(
    *,
    qre_authority: dict[str, Any],
    executable_ids: list[str],
    present_ids: list[str],
    missing_ids: list[str],
    all_statuses_linked: bool,
) -> list[str]:
    codes: list[str] = []
    if qre_authority["available"]:
        codes.append("qre_authority_available")
    else:
        codes.append("qre_authority_unavailable")
    if all_statuses_linked and qre_authority["total_hypotheses"] > 0:
        codes.append("qre_authority_all_linked_exact_ids")
    if executable_ids:
        codes.append("executable_hypothesis_ids_discovered")
    else:
        codes.append("no_executable_hypothesis_ids_discovered")
    if present_ids:
        codes.append("executable_hypothesis_id_present_in_qre_authority")
    if missing_ids:
        codes.append("executable_hypothesis_id_not_in_qre_authority")
        codes.append("runtime_regeneration_expected_unlinked_unknown_hypothesis_id")
        codes.append("deterministic_mapping_not_supported_without_explicit_bridge")
    elif executable_ids and qre_authority["available"]:
        codes.append("runtime_regeneration_expected_strict_linked_hypothesis_id")
    return codes


def _bridge_snapshot(
    *,
    qre_authority: dict[str, Any],
    executable_hypothesis_ids: list[str],
) -> dict[str, Any]:
    qre_ids = set(qre_authority["sample_qre_hypothesis_ids"])
    status_counts = qre_authority["status_counts"]
    total = qre_authority["total_hypotheses"]
    if total > len(qre_ids):
        # The sample is intentionally bounded; exact membership must use the full
        # authority map supplied by the caller via executable row annotations.
        qre_ids = set()
    present = []
    missing = []
    for hypothesis_id in executable_hypothesis_ids:
        if qre_ids and hypothesis_id in qre_ids:
            present.append(hypothesis_id)
        else:
            missing.append(hypothesis_id)
    all_statuses_linked = (
        qre_authority["available"] and total > 0 and status_counts == {"linked_exact_ids": total}
    )
    regeneration_expected = (
        qre_authority["available"] and bool(executable_hypothesis_ids) and not missing
    )
    if not qre_authority["available"]:
        primary_blocker = PRIMARY_BLOCKER_QRE_AUTHORITY_UNAVAILABLE
    elif not executable_hypothesis_ids:
        primary_blocker = PRIMARY_BLOCKER_NO_EXECUTABLE_IDS
    elif missing:
        primary_blocker = PRIMARY_BLOCKER_EXECUTABLE_ID_MISSING
    else:
        primary_blocker = PRIMARY_BLOCKER_NONE
    reason_codes = _reason_codes(
        qre_authority=qre_authority,
        executable_ids=executable_hypothesis_ids,
        present_ids=present,
        missing_ids=missing,
        all_statuses_linked=all_statuses_linked,
    )
    return {
        "executable_ids_present_in_qre_authority": present,
        "executable_ids_missing_from_qre_authority": missing,
        "executable_to_qre_authority_match_count": len(present),
        "regeneration_linkage_expected": regeneration_expected,
        "primary_blocker": primary_blocker,
        "deterministic_mapping_possible": regeneration_expected,
        "reason_codes": reason_codes,
    }


def _bridge_snapshot_from_rows(
    *,
    qre_authority: dict[str, Any],
    executable_hypothesis_ids: list[str],
    per_preset: list[dict[str, Any]],
) -> dict[str, Any]:
    present_set = {
        str(row["hypothesis_id"])
        for row in per_preset
        if row["enabled"] and row["hypothesis_id"] and row["hypothesis_id_present_in_qre_authority"]
    }
    bridge = _bridge_snapshot(
        qre_authority=qre_authority,
        executable_hypothesis_ids=executable_hypothesis_ids,
    )
    present = [item for item in executable_hypothesis_ids if item in present_set]
    missing = [item for item in executable_hypothesis_ids if item not in present_set]
    regeneration_expected = (
        qre_authority["available"] and bool(executable_hypothesis_ids) and not missing
    )
    if not qre_authority["available"]:
        primary_blocker = PRIMARY_BLOCKER_QRE_AUTHORITY_UNAVAILABLE
    elif not executable_hypothesis_ids:
        primary_blocker = PRIMARY_BLOCKER_NO_EXECUTABLE_IDS
    elif missing:
        primary_blocker = PRIMARY_BLOCKER_EXECUTABLE_ID_MISSING
    else:
        primary_blocker = PRIMARY_BLOCKER_NONE
    status_counts = qre_authority["status_counts"]
    all_statuses_linked = (
        qre_authority["available"]
        and qre_authority["total_hypotheses"] > 0
        and status_counts == {"linked_exact_ids": qre_authority["total_hypotheses"]}
    )
    bridge.update(
        {
            "executable_ids_present_in_qre_authority": present,
            "executable_ids_missing_from_qre_authority": missing,
            "executable_to_qre_authority_match_count": len(present),
            "regeneration_linkage_expected": regeneration_expected,
            "primary_blocker": primary_blocker,
            "deterministic_mapping_possible": regeneration_expected,
            "reason_codes": _reason_codes(
                qre_authority=qre_authority,
                executable_ids=executable_hypothesis_ids,
                present_ids=present,
                missing_ids=missing,
                all_statuses_linked=all_statuses_linked,
            ),
        }
    )
    return bridge


def _final_recommendation(bridge: dict[str, Any]) -> str:
    if bridge["primary_blocker"] == PRIMARY_BLOCKER_NONE:
        return FINAL_RECOMMENDATION_BRIDGE_READY
    if bridge["primary_blocker"] == PRIMARY_BLOCKER_EXECUTABLE_ID_MISSING:
        return FINAL_RECOMMENDATION_BRIDGE_REQUIRED
    return FINAL_RECOMMENDATION_INPUTS_FAILED_CLOSED


def collect_snapshot(
    *,
    hypothesis_artifact_path: Path | None = None,
    plan_artifact_path: Path | None = None,
    run_manifest_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
    presets: Any = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    (
        qre_authority,
        qre_by_hypothesis_id,
        qre_by_executable_hypothesis_id,
        authority_warnings,
    ) = _authority_snapshot(
        hypothesis_artifact_path=hypothesis_artifact_path or DEFAULT_HYPOTHESIS_ARTIFACT_PATH,
        plan_artifact_path=plan_artifact_path or DEFAULT_PLAN_ARTIFACT_PATH,
        run_manifest_artifact_path=run_manifest_artifact_path or DEFAULT_RUN_MANIFEST_ARTIFACT_PATH,
    )
    executable_presets, preset_warnings = _presets_snapshot(
        presets=presets,
        qre_by_hypothesis_id=qre_by_hypothesis_id,
        qre_by_executable_hypothesis_id=qre_by_executable_hypothesis_id,
    )
    bridge = _bridge_snapshot_from_rows(
        qre_authority=qre_authority,
        executable_hypothesis_ids=executable_presets["executable_hypothesis_ids"],
        per_preset=executable_presets["per_preset"],
    )
    validation_warnings = _bounded_unique(
        [*authority_warnings, *preset_warnings],
        max_items=WARNING_LIMIT,
    )
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "output_artifact_path": OUTPUT_ARTIFACT_RELATIVE_PATH,
        "safe_to_execute": False,
        "read_only": True,
        "final_recommendation": _final_recommendation(bridge),
        "validation_warnings": validation_warnings,
        "qre_authority": qre_authority,
        "executable_presets": executable_presets,
        "bridge": bridge,
        "recommended_bridge_keys": list(RECOMMENDED_BRIDGE_KEYS),
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


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE executable bridge diagnostics dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_executable_hypothesis_identity_bridge.",
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


def write_snapshot(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_executable_hypothesis_identity_bridge_diagnostics",
        description="Explain executable preset hypothesis IDs versus QRE generated IDs.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        write_snapshot(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "DEFAULT_HYPOTHESIS_ARTIFACT_PATH",
    "DEFAULT_PLAN_ARTIFACT_PATH",
    "DEFAULT_RUN_MANIFEST_ARTIFACT_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_snapshot",
]
