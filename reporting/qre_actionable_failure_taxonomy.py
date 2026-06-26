"""Read-only actionable failure taxonomy for ADE-QRE-017G."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-017g-2026-06-26"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_actionable_failure_taxonomy"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_actionable_failure_taxonomy"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
DOC_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "governance" / "qre_actionable_failure_taxonomy.md"
)
_WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_actionable_failure_taxonomy/",
    "docs/governance/qre_actionable_failure_taxonomy.md",
)


def _research_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _bounded(value: Any, *, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _stable_hash(payload: Mapping[str, Any]) -> str:
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in _WRITE_PREFIXES):
        raise ValueError(
            "qre_actionable_failure_taxonomy: refusing write outside allowlist: "
            f"{path!r}"
        )


def _screening_rows(
    *,
    screening_payload: Mapping[str, Any],
    screening_path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _list_of_mappings(screening_payload.get("classifications")):
        failure_class = _bounded(item.get("classification"))
        count = int(item.get("count") or 0)
        hint = _mapping(item.get("action_hint"))
        recommended_action = _bounded(hint.get("action")) or "hold_no_action_until_evidence_improves"
        reason_text = _bounded(hint.get("reason"))
        status = _bounded(item.get("status")) or "unknown"
        supported = count > 0 and failure_class not in {
            "unknown_screening_failure",
            "unsupported_failure_shape",
        }
        rows.append(
            {
                "taxonomy_id": f"screening:{failure_class or 'unknown'}",
                "source_surface": "screening_failure_attribution",
                "failure_class": failure_class or "unknown",
                "observed_count": count,
                "evidence_status": (
                    "supported"
                    if supported
                    else "insufficient_evidence"
                    if count > 0
                    else "not_observed"
                ),
                "supported": supported,
                "recommended_action": recommended_action,
                "exact_one_next_action": bool(recommended_action),
                "reason_codes": [failure_class] if failure_class else [],
                "operator_explanation": reason_text
                or "Screening attribution did not provide an actionable explanation.",
                "source_status": status,
                "evidence_refs": [_rel(screening_path)],
            }
        )
    return rows


def _basket_rows(
    *,
    basket_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "actions": [],
            "actionability_statuses": [],
            "reason_codes": [],
            "explanations": [],
            "record_ids": [],
            "evidence_refs": [],
        }
    )

    for row in _list_of_mappings(basket_report.get("rows")):
        blocker_code = _bounded(row.get("blocker_code")) or "unknown_basket_blocker"
        bucket = grouped[blocker_code]
        bucket["count"] += 1

        action = _bounded(row.get("recommended_action"))
        if action and action not in bucket["actions"]:
            bucket["actions"].append(action)

        actionability = _mapping(row.get("actionability"))
        actionability_status = _bounded(actionability.get("status"))
        if actionability_status and actionability_status not in bucket["actionability_statuses"]:
            bucket["actionability_statuses"].append(actionability_status)

        explanation = _bounded(actionability.get("operator_explanation"))
        if explanation and explanation not in bucket["explanations"]:
            bucket["explanations"].append(explanation)

        refs = _mapping(row.get("reason_record_refs"))
        for key in ("reason_codes", "record_ids", "evidence_refs"):
            values = refs.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                text = _bounded(value)
                if text and text not in bucket[key]:
                    bucket[key].append(text)

    rows: list[dict[str, Any]] = []
    for blocker_code, bucket in sorted(grouped.items()):
        actions = list(bucket["actions"])
        exact_one = len(actions) == 1
        supported = (
            exact_one
            and "actionable" in bucket["actionability_statuses"]
            and blocker_code not in {"supporting_artifacts_missing", "reason_refs_missing"}
        )
        if exact_one:
            recommended_action = actions[0]
        else:
            recommended_action = "keep_blocked"

        if exact_one:
            evidence_status = "supported" if supported else "insufficient_evidence"
        else:
            evidence_status = "inconsistent_mapping_fail_closed"

        explanation = (
            bucket["explanations"][0]
            if bucket["explanations"]
            else "Basket failure mapping did not provide an operator explanation."
        )
        if not exact_one:
            explanation = (
                "The same basket blocker class produced multiple recommended actions, "
                "so the taxonomy fails closed and keeps the blocker explicit."
            )

        reason_codes = list(bucket["reason_codes"])
        if not reason_codes:
            reason_codes = [blocker_code]
        if not exact_one and "inconsistent_mapping_fail_closed" not in reason_codes:
            reason_codes.append("inconsistent_mapping_fail_closed")

        rows.append(
            {
                "taxonomy_id": f"basket:{blocker_code}",
                "source_surface": "qre_failure_action_from_basket",
                "failure_class": blocker_code,
                "observed_count": int(bucket["count"]),
                "evidence_status": evidence_status,
                "supported": supported,
                "recommended_action": recommended_action,
                "exact_one_next_action": exact_one,
                "reason_codes": reason_codes,
                "operator_explanation": explanation,
                "source_status": (
                    "actionable"
                    if "actionable" in bucket["actionability_statuses"]
                    else "non_actionable"
                ),
                "evidence_refs": list(bucket["evidence_refs"]),
            }
        )
    return rows


def _minimal_rows(
    *,
    minimal_payload: Mapping[str, Any],
    minimal_path: Path,
) -> list[dict[str, Any]]:
    items = _list_of_mappings(minimal_payload.get("items"))
    if not items:
        return [
            {
                "taxonomy_id": "minimal:no_failure_inputs",
                "source_surface": "failure_action_mapping_minimal",
                "failure_class": "no_failure_inputs",
                "observed_count": 0,
                "evidence_status": "insufficient_evidence",
                "supported": False,
                "recommended_action": "collect_more_evidence",
                "exact_one_next_action": True,
                "reason_codes": ["no_failure_inputs"],
                "operator_explanation": (
                    "The minimal failure-action mapping artifact contains zero populated "
                    "failure rows, so the surface stays explicitly unpopulated."
                ),
                "source_status": "empty",
                "evidence_refs": [_rel(minimal_path)],
            }
        ]

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "actions": [],
            "reason_codes": [],
            "explanations": [],
        }
    )
    for item in items:
        failure_code = _bounded(item.get("failure_code")) or "unknown_failure"
        bucket = grouped[failure_code]
        bucket["count"] += 1
        action = _bounded(item.get("recommended_action"))
        if action and action not in bucket["actions"]:
            bucket["actions"].append(action)
        reason_record = _mapping(item.get("reason_record"))
        for code in reason_record.get("reason_codes") or []:
            text = _bounded(code)
            if text and text not in bucket["reason_codes"]:
                bucket["reason_codes"].append(text)
        explanation = _bounded(reason_record.get("reason_text"))
        if explanation and explanation not in bucket["explanations"]:
            bucket["explanations"].append(explanation)

    rows: list[dict[str, Any]] = []
    for failure_code, bucket in sorted(grouped.items()):
        exact_one = len(bucket["actions"]) == 1
        rows.append(
            {
                "taxonomy_id": f"minimal:{failure_code}",
                "source_surface": "failure_action_mapping_minimal",
                "failure_class": failure_code,
                "observed_count": int(bucket["count"]),
                "evidence_status": "supported" if exact_one else "inconsistent_mapping_fail_closed",
                "supported": exact_one,
                "recommended_action": bucket["actions"][0] if exact_one else "hold_no_action",
                "exact_one_next_action": exact_one,
                "reason_codes": list(bucket["reason_codes"]) or [failure_code],
                "operator_explanation": (
                    bucket["explanations"][0]
                    if bucket["explanations"]
                    else "Minimal failure-action mapping did not provide a reason record."
                ),
                "source_status": "populated",
                "evidence_refs": [_rel(minimal_path)],
            }
        )
    return rows


def collect_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
    max_candidates: int = 15,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    generated_at_utc = frozen_utc or _utcnow()
    screening_path = repo_root / "research" / "screening_failure_attribution_latest.v1.json"
    minimal_path = repo_root / "logs" / "failure_action_mapping_minimal" / "latest.json"

    screening_payload = _read_json(screening_path)
    minimal_payload = _read_json(minimal_path)
    basket_module = _research_module("research.qre_failure_action_from_basket")
    basket_report = basket_module.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    basket_report = basket_report if isinstance(basket_report, Mapping) else {}

    taxonomy_rows = [
        *_screening_rows(screening_payload=screening_payload, screening_path=screening_path),
        *_basket_rows(basket_report=basket_report),
        *_minimal_rows(minimal_payload=minimal_payload, minimal_path=minimal_path),
    ]
    taxonomy_rows.sort(key=lambda row: (str(row["source_surface"]), str(row["failure_class"])))

    exact_one_supported = [
        row for row in taxonomy_rows if row["supported"] and row["exact_one_next_action"]
    ]
    insufficient_rows = [
        row for row in taxonomy_rows if row["evidence_status"] != "supported"
    ]
    source_surface_counts = Counter(str(row["source_surface"]) for row in taxonomy_rows)
    action_counts = Counter(str(row["recommended_action"]) for row in taxonomy_rows)
    supported_surface_counts = Counter(
        str(row["source_surface"]) for row in taxonomy_rows if row["supported"]
    )
    all_supported_exactly_one = all(
        bool(row["exact_one_next_action"]) for row in taxonomy_rows if row["supported"]
    )

    snapshot_identity = {
        "snapshot_id": _stable_hash(
            {
                "generated_at_utc": generated_at_utc,
                "taxonomy_rows": taxonomy_rows,
                "max_candidates": max_candidates,
            }
        )
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "max_candidates": max_candidates,
        "source_artifacts": {
            "screening_failure_attribution": {
                "path": _rel(screening_path),
                "status": "present" if screening_payload else "missing_or_unreadable",
            },
            "failure_action_mapping_minimal": {
                "path": _rel(minimal_path),
                "status": "present" if minimal_payload else "missing_or_unreadable",
            },
            "qre_failure_action_from_basket": {
                "path": "research/qre_failure_action_from_basket.py",
                "status": "derived_runtime_snapshot",
            },
        },
        "taxonomy_rows": taxonomy_rows,
        "summary": {
            "row_count": len(taxonomy_rows),
            "supported_failure_class_count": len(
                [row for row in taxonomy_rows if row["supported"]]
            ),
            "insufficient_evidence_class_count": len(insufficient_rows),
            "exact_one_supported_action_count": len(exact_one_supported),
            "all_supported_classes_have_exactly_one_next_action": all_supported_exactly_one,
            "source_surface_counts": {
                key: int(source_surface_counts[key]) for key in sorted(source_surface_counts)
            },
            "supported_surface_counts": {
                key: int(supported_surface_counts[key])
                for key in sorted(supported_surface_counts)
            },
            "recommended_action_counts": {
                key: int(action_counts[key]) for key in sorted(action_counts)
            },
            "final_recommendation": (
                "actionable_failure_taxonomy_ready"
                if all_supported_exactly_one and any(row["supported"] for row in taxonomy_rows)
                else "actionable_failure_taxonomy_partial_with_explicit_gaps"
            ),
            "operator_summary": (
                "Actionable failure taxonomy consolidates current screening, basket, "
                "and minimal failure-action surfaces into one read-only view. "
                "Supported classes carry exactly one bounded next action; thin or "
                "empty evidence remains explicit and fails closed."
            ),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "mutates_queue": False,
            "mutates_research_outputs": False,
            "mutates_routing": False,
            "mutates_sampling": False,
            "mutates_strategy_or_registry": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "invents_failure_causes": False,
        },
        "snapshot_identity": snapshot_identity,
    }


def render_markdown(snapshot: Mapping[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    rows = _list_of_mappings(snapshot.get("taxonomy_rows"))
    lines = [
        "# QRE Actionable Failure Taxonomy",
        "",
        f"- generated_at_utc: `{_bounded(snapshot.get('generated_at_utc'))}`",
        f"- module_version: `{_bounded(snapshot.get('module_version'))}`",
        "",
        "## Summary",
        "",
        f"- {summary.get('operator_summary') or ''}",
        f"- supported failure classes: `{summary.get('supported_failure_class_count') or 0}`",
        f"- insufficient-evidence classes: `{summary.get('insufficient_evidence_class_count') or 0}`",
        f"- all supported classes have exactly one next action: `{summary.get('all_supported_classes_have_exactly_one_next_action')}`",
        f"- final recommendation: `{summary.get('final_recommendation') or ''}`",
        "",
        "## Taxonomy Rows",
        "",
        "| Surface | Failure class | Count | Evidence status | Next action | Supported |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _bounded(row.get("source_surface")),
                    _bounded(row.get("failure_class")),
                    str(int(row.get("observed_count") or 0)),
                    _bounded(row.get("evidence_status")),
                    _bounded(row.get("recommended_action")),
                    str(bool(row.get("supported"))).lower(),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path = ARTIFACT_DIR,
    doc_path: Path = DOC_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    latest = output_dir / "latest.json"
    for target in (latest, doc_path):
        _validate_write_target(target)

    json_payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(latest.parent),
        delete=False,
    ) as handle:
        handle.write(json_payload)
        tmp_json = Path(handle.name)
    os.replace(tmp_json, latest)

    markdown = render_markdown(snapshot)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(doc_path.parent),
        delete=False,
    ) as handle:
        handle.write(markdown)
        tmp_doc = Path(handle.name)
    os.replace(tmp_doc, doc_path)

    return {
        "latest": _rel(latest.relative_to(repo_root) if latest.is_relative_to(repo_root) else latest),
        "doc": _rel(doc_path.relative_to(repo_root) if doc_path.is_relative_to(repo_root) else doc_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_actionable_failure_taxonomy",
        description="Build read-only actionable failure taxonomy snapshot.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--frozen-utc")
    args = parser.parse_args(list(argv) if argv is not None else None)

    snapshot = collect_snapshot(
        max_candidates=args.max_candidates,
        frozen_utc=args.frozen_utc,
    )
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
