from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_reason_records_v1 as reason_records
from research import qre_routing_readiness_from_basket as routing
from research import qre_sampling_readiness_from_basket as sampling


REPORT_KIND: Final[str] = "qre_failure_action_from_basket"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_failure_action_from_basket")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_failure_action_from_basket/"
_STATE_ORDER: Final[tuple[str, ...]] = ("actionable", "non_actionable")
_ACTION_ORDER: Final[tuple[str, ...]] = (
    "eligible_for_readonly_routing",
    "collect_more_evidence",
    "expand_basket_coverage",
    "require_source_readiness",
    "require_identity_resolution",
    "route_to_manual_review",
    "suppress_until_new_evidence",
    "defer_as_duplicate",
    "keep_blocked",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _bounded_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in out:
            out.append(text[:160])
    return out[:24]


def _reason_ref_index(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, list[str]]]:
    by_subject: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {
            "record_ids": [],
            "record_families": [],
            "reason_codes": [],
            "evidence_refs": [],
        }
    )
    for record in records:
        subject_id = str(record.get("subject_id") or "")
        if not subject_id:
            continue
        refs = by_subject[subject_id]
        for key, source in (
            ("record_ids", [record.get("record_id")]),
            ("record_families", [record.get("record_family")]),
            ("reason_codes", record.get("reason_codes") or []),
            ("evidence_refs", record.get("evidence_refs") or []),
        ):
            for value in _bounded_list(source):
                if value not in refs[key]:
                    refs[key].append(value)
    return dict(by_subject)


def _classification(
    *,
    row: Mapping[str, Any],
    reason_refs_present: bool,
) -> tuple[str, str, list[str], str, bool]:
    diagnosis_class = str(row.get("diagnosis_class") or "unknown_fail_closed")
    routing_state = str(row.get("routing_readiness_state") or "fail_closed")
    sampling_state = str(row.get("sampling_readiness_state") or "fail_closed")
    primary_reason = str(row.get("primary_reason_code") or row.get("diagnosis_reason_code") or "unknown")
    validation_counts = row.get("validation_evidence_status_counts")
    if not isinstance(validation_counts, Mapping):
        validation_counts = {}

    if not reason_refs_present:
        return (
            "reason_refs_missing",
            "keep_blocked",
            ["missing_reason_refs"],
            "No durable reason refs are available for this basket, so failure-action mapping fails closed.",
            False,
        )
    if diagnosis_class == "unknown_fail_closed" or routing_state == "fail_closed":
        return (
            "supporting_artifacts_missing",
            "keep_blocked",
            ["fail_closed", "supporting_artifacts_missing"],
            "Supporting artifacts are missing or fail-closed, so the basket remains blocked until evidence becomes deterministic.",
            False,
        )
    if primary_reason == "source_identity_blocked":
        return (
            "source_identity_blocked",
            "require_identity_resolution",
            ["identity_resolution_required"],
            "Source identity is blocked, so the next bounded action is to resolve canonical-to-provider symbol identity.",
            True,
        )
    if primary_reason == "source_or_cache_not_ready":
        return (
            "source_or_cache_not_ready",
            "require_source_readiness",
            ["source_or_cache_not_ready"],
            "Source quality or cache readiness is explicitly blocked; research action stays read-only until readiness improves.",
            True,
        )
    if primary_reason == "source_or_cache_coverage_missing":
        return (
            "source_or_cache_coverage_missing",
            "expand_basket_coverage",
            ["coverage_missing"],
            "The basket lacks source/cache coverage, so the next bounded action is to expand coverage rather than mutate research logic.",
            True,
        )
    if primary_reason in {"screening_evidence_missing", "oos_evidence_missing", "sampling_oos_window_unknown"}:
        return (
            primary_reason,
            "collect_more_evidence",
            ["screening_or_oos_evidence_missing"],
            "The basket is blocked by missing screening or OOS evidence, so the next bounded action is to collect more evidence.",
            True,
        )
    if primary_reason == "lineage_missing":
        return (
            "lineage_missing",
            "route_to_manual_review",
            ["lineage_review_required"],
            "Campaign or candidate lineage is incomplete, so the basket requires manual review instead of autonomous mutation.",
            True,
        )
    if routing_state == "ready" and sampling_state == "ready":
        return (
            "ready_for_readonly_research",
            "eligible_for_readonly_routing",
            ["routing_sampling_ready"],
            "The basket is routing- and sampling-ready for read-only research only; this is not a promotion or execution signal.",
            True,
        )
    if sampling_state == "blocked":
        return (
            primary_reason,
            "require_source_readiness",
            ["sampling_blocked"],
            "Sampling remains blocked by upstream readiness constraints, so the next bounded action is to restore source readiness.",
            True,
        )
    if sampling_state == "deferred":
        return (
            primary_reason,
            "collect_more_evidence",
            ["sampling_deferred"],
            "Sampling is deferred pending explicit evidence, so the next bounded action is to collect more evidence.",
            True,
        )
    if int(validation_counts.get("sufficient_oos_evidence") or 0) > 0:
        return (
            "sufficient_oos_but_not_promotable",
            "suppress_until_new_evidence",
            ["negative_result_preserved"],
            "Sufficient OOS evidence exists but remains below promotion quality gates, so the result is preserved without promotion.",
            False,
        )
    return (
        "deferred_duplicate_or_unknown",
        "defer_as_duplicate",
        ["deferred_duplicate_or_unknown"],
        "The basket is deferred without a stronger autonomous action, so it remains explicitly deferred for later operator review.",
        True,
    )


def build_failure_action_from_basket(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    routing_report = routing.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling_report = sampling.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    record_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    routing_rows = routing_report.get("rows")
    if not isinstance(routing_rows, list):
        routing_rows = []
    sampling_rows = sampling_report.get("rows")
    if not isinstance(sampling_rows, list):
        sampling_rows = []
    record_rows = record_snapshot.get("records")
    if not isinstance(record_rows, list):
        record_rows = []

    sampling_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in sampling_rows
        if isinstance(row, Mapping)
    }
    reason_ref_index = _reason_ref_index(
        [row for row in record_rows if isinstance(row, Mapping)]
    )

    rows: list[dict[str, Any]] = []
    for routing_row in routing_rows:
        if not isinstance(routing_row, Mapping):
            continue
        subject_id = str(routing_row.get("candidate_id") or "")
        sampling_row = sampling_by_subject.get(subject_id, {})
        reason_ref = reason_ref_index.get(subject_id, {})
        blocker_code, action, actionability_reasons, explanation, is_actionable = _classification(
            row={
                **dict(routing_row),
                "sampling_readiness_state": sampling_row.get("sampling_readiness_state"),
                "validation_evidence_status_counts": routing_row.get(
                    "validation_evidence_status_counts"
                ),
            },
            reason_refs_present=bool(reason_ref.get("record_ids")),
        )
        rows.append(
            {
                "candidate_id": subject_id,
                "symbol": routing_row.get("symbol"),
                "region": routing_row.get("region"),
                "asset_class": routing_row.get("asset_class"),
                "preset_id": routing_row.get("preset_id"),
                "hypothesis_id": routing_row.get("hypothesis_id"),
                "behavior_family": routing_row.get("behavior_family"),
                "timeframes": list(routing_row.get("timeframes") or []),
                "diagnosis_class": routing_row.get("diagnosis_class"),
                "routing_readiness_state": routing_row.get("routing_readiness_state"),
                "sampling_readiness_state": sampling_row.get("sampling_readiness_state", "fail_closed"),
                "primary_reason_code": routing_row.get("primary_reason_code"),
                "blocker_code": blocker_code,
                "recommended_action": action,
                "actionability": {
                    "status": "actionable" if is_actionable else "non_actionable",
                    "is_actionable": is_actionable,
                    "reason_codes": actionability_reasons,
                    "operator_explanation": explanation,
                },
                "follow_up": (
                    "eligible_for_readonly_routing"
                    if action == "eligible_for_readonly_routing"
                    else action
                ),
                "reason_record_refs": {
                    "record_ids": list(reason_ref.get("record_ids") or []),
                    "record_families": list(reason_ref.get("record_families") or []),
                    "reason_codes": list(reason_ref.get("reason_codes") or []),
                    "evidence_refs": list(reason_ref.get("evidence_refs") or []),
                },
            }
        )

    rows.sort(
        key=lambda row: (
            _STATE_ORDER.index(str(row["actionability"]["status"])),
            _ACTION_ORDER.index(str(row["recommended_action"]))
            if str(row["recommended_action"]) in _ACTION_ORDER
            else len(_ACTION_ORDER),
            str(row["symbol"]),
            str(row["preset_id"]),
        )
    )
    counts = Counter(str(row["recommended_action"]) for row in rows)
    blocker_counts = Counter(str(row["blocker_code"]) for row in rows)
    actionable_count = sum(bool((row.get("actionability") or {}).get("is_actionable")) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "basket_source": routing_report.get("basket_source"),
        "max_candidates": max_candidates,
        "summary": {
            "basket_inventory_count": len(rows),
            "actionable_count": actionable_count,
            "non_actionable_count": len(rows) - actionable_count,
            "action_counts": dict(sorted(counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "reason_record_subject_count": len(reason_ref_index),
            "final_recommendation": (
                "actions_available_from_real_basket_evidence"
                if actionable_count > 0
                else "failure_action_from_basket_fail_closed"
            ),
            "operator_summary": (
                "Failure-to-action mapping converts real basket blockers into bounded "
                "read-only operator actions. It never mutates routing, sampling, "
                "strategies, paper, shadow, or live state."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_routing": False,
            "mutates_sampling": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "authorizes_actions": False,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket inventory", str(summary.get("basket_inventory_count") or 0)],
            ["actionable", str(summary.get("actionable_count") or 0)],
            ["non-actionable", str(summary.get("non_actionable_count") or 0)],
            ["reason-record subjects", str(summary.get("reason_record_subject_count") or 0)],
        ],
    )
    basket_table = _table(
        [
            "Symbol",
            "Preset",
            "Routing",
            "Sampling",
            "Blocker",
            "Action",
            "Actionable",
        ],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                str(row.get("routing_readiness_state") or ""),
                str(row.get("sampling_readiness_state") or ""),
                str(row.get("blocker_code") or ""),
                str(row.get("recommended_action") or ""),
                str((row.get("actionability") or {}).get("status") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Failure Action From Basket Evidence",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Actionability counts",
            count_table,
            "",
            "## 3. Basket actions",
            basket_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_failure_action_from_basket: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(payload, encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_failure_action_from_basket",
        description="Build read-only failure-to-action mapping from real basket evidence.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_failure_action_from_basket(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
