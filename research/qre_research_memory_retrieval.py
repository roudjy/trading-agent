from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_research import research_memory


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_research_memory_retrieval"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_memory_retrieval")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_research_memory_retrieval/"

DEFAULT_ARTIFACT_PATHS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
    Path("research/campaign_registry_latest.v1.json"),
    Path("research/candidate_registry_latest.v1.json"),
    Path("research/screening_evidence_latest.v1.json"),
    Path("logs/qre_hypothesis_disposition_memory/latest.json"),
    Path("logs/qre_research_cycle_router/latest.json"),
    Path("logs/qre_evidence_breadth_framework/latest.json"),
    Path("logs/qre_source_identity_authority_normalization/latest.json"),
    Path("logs/qre_read_only_artifact_continuity/latest.json"),
    Path("logs/qre_contradiction_staleness_intelligence/latest.json"),
    Path("logs/qre_campaign_throughput_bottleneck_intelligence/latest.json"),
    Path("logs/qre_experiment_dedup_novelty_enforcement/latest.json"),
    Path("logs/qre_preregistered_multiwindow_evidence_run/latest.json"),
    Path("logs/qre_multiwindow_evidence_closure/latest.json"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _scope_signature(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hypothesis_id": _text(scope.get("hypothesis_id")),
        "behavior_id": _text(scope.get("behavior_id")),
        "preset_id": _text(scope.get("preset_id")),
        "timeframe": _text(scope.get("timeframe")),
        "universe_or_basket_scope": _text(scope.get("universe_or_basket_scope")),
        "region": _text(scope.get("region")),
    }


def _provenance(path: str, *, ref: str = "") -> dict[str, Any]:
    return {"artifact_path": path, "artifact_ref": ref or path}


def _disposition_index(disposition: Mapping[str, Any] | None) -> dict[str, Any]:
    record = disposition.get("record") if isinstance(disposition, Mapping) and isinstance(disposition.get("record"), Mapping) else {}
    scope = record.get("disposition_scope") if isinstance(record.get("disposition_scope"), Mapping) else {}
    return {
        "record": record,
        "tested_scope": _scope_signature(scope),
        "failure_classes": _unique_in_order(record.get("failure_classes") or []),
        "reason_record_refs": _unique_in_order(record.get("reason_record_refs") or []),
        "accepted_lineage_refs": _unique_in_order(record.get("accepted_lineage_refs") or []),
        "accepted_oos_refs": _unique_in_order(record.get("accepted_oos_refs") or []),
        "regime_refs": _unique_in_order(record.get("regime_refs") or []),
        "window_refs": _unique_in_order(record.get("window_refs") or []),
    }


def _breadth_rows(breadth: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows = breadth.get("coverage_matrix") if isinstance(breadth, Mapping) and isinstance(breadth.get("coverage_matrix"), list) else []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _exact_scope_already_tested(disposition_index: Mapping[str, Any]) -> dict[str, Any]:
    scope = disposition_index.get("tested_scope") if isinstance(disposition_index.get("tested_scope"), Mapping) else {}
    tested = any(_text(value) for value in scope.values())
    return {
        "query_id": "exact_scope_already_tested",
        "status": "matched" if tested else "not_found",
        "answer": bool(tested),
        "scope_signature": dict(scope),
        "provenance": [_provenance("logs/qre_hypothesis_disposition_memory/latest.json", ref="logs/qre_hypothesis_disposition_memory/latest.json#record.disposition_scope")],
    }


def _materially_similar_scope_rejected(disposition_index: Mapping[str, Any]) -> dict[str, Any]:
    record = disposition_index.get("record") if isinstance(disposition_index.get("record"), Mapping) else {}
    rejected = _text(record.get("hypothesis_disposition")) in {"not_supported", "fail_closed_rejected"}
    return {
        "query_id": "materially_similar_scope_rejected",
        "status": "matched" if rejected else "not_found",
        "answer": bool(rejected),
        "same_scope_suppressed": bool((record.get("retry_policy") or {}).get("same_scope_suppressed")),
        "failure_classes": list(disposition_index.get("failure_classes") or []),
        "provenance": [_provenance("logs/qre_hypothesis_disposition_memory/latest.json", ref="logs/qre_hypothesis_disposition_memory/latest.json#record")],
    }


def _regimes_with_no_trades(disposition_index: Mapping[str, Any], campaign: Mapping[str, Any] | None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    window_results = campaign.get("window_results") if isinstance(campaign, Mapping) and isinstance(campaign.get("window_results"), list) else []
    for index, window in enumerate(window_results):
        if not isinstance(window, Mapping):
            continue
        regime = _text(window.get("regime_label")) or f"window_{index + 1}"
        symbol_results = window.get("symbol_results") if isinstance(window.get("symbol_results"), list) else []
        oos_record_count = 0
        for result in symbol_results:
            if not isinstance(result, Mapping):
                continue
            oos_records = result.get("oos_records")
            if isinstance(oos_records, list):
                oos_record_count += len(oos_records)
        if oos_record_count == 0:
            rows.append(
                {
                    "regime_label": regime,
                    "status": "no_trades_visible",
                    "window_ref": f"logs/qre_preregistered_multiwindow_evidence_run/latest.json#window_results[{index}]",
                }
            )
    if not rows:
        rows = [
            {
                "regime_label": regime,
                "status": "context_only_no_trade_scope",
                "window_ref": "",
            }
            for regime in disposition_index.get("regime_refs", [])
        ]
    return {
        "query_id": "regimes_consistently_no_trades",
        "status": "matched" if rows else "not_found",
        "rows": rows,
        "provenance": [_provenance("logs/qre_preregistered_multiwindow_evidence_run/latest.json")],
    }


def _inadequate_sample_density_presets(breadth_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [
        {
            "preset_id": _text(row.get("scope_key")),
            "inventory_count": int(row.get("inventory_count") or 0),
            "basket_count": int(row.get("basket_count") or 0),
            "accepted_oos_count": int(row.get("accepted_oos_count") or 0),
            "blocker_reasons": list(row.get("blocker_reasons") or []),
        }
        for row in breadth_rows
        if _text(row.get("dimension")) == "preset"
        and (int(row.get("basket_count") or 0) <= 1 or int(row.get("accepted_oos_count") or 0) == 0)
    ]
    rows.sort(key=lambda row: (row["basket_count"], row["preset_id"]))
    return {
        "query_id": "presets_with_inadequate_sample_density",
        "status": "matched" if rows else "not_found",
        "rows": rows,
        "provenance": [_provenance("logs/qre_evidence_breadth_framework/latest.json", ref="logs/qre_evidence_breadth_framework/latest.json#coverage_matrix")],
    }


def _recurring_failures(
    disposition_index: Mapping[str, Any],
    breadth_rows: Sequence[Mapping[str, Any]],
    source_authority: Mapping[str, Any] | None,
) -> dict[str, Any]:
    counts = Counter(str(reason) for row in breadth_rows for reason in row.get("blocker_reasons", []))
    counts.update(str(reason) for reason in disposition_index.get("failure_classes", []))
    authority_rows = source_authority.get("rows") if isinstance(source_authority, Mapping) and isinstance(source_authority.get("rows"), list) else []
    counts.update(
        str(reason)
        for row in authority_rows
        if isinstance(row, Mapping)
        for reason in row.get("authority_reasons", [])
    )
    rows = [
        {"failure_or_blocker": key, "count": count}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "query_id": "recurring_evidence_or_source_failures",
        "status": "matched" if rows else "not_found",
        "rows": rows,
        "provenance": [
            _provenance("logs/qre_hypothesis_disposition_memory/latest.json"),
            _provenance("logs/qre_evidence_breadth_framework/latest.json"),
            _provenance("logs/qre_source_identity_authority_normalization/latest.json"),
        ],
    }


def _novel_remaining_directions(router: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = router.get("eligible_directions") if isinstance(router, Mapping) and isinstance(router.get("eligible_directions"), list) else []
    shaped = [
        {
            "direction_id": _text(row.get("direction_id")),
            "direction_type": _text(row.get("direction_type")),
            "route_status": _text(row.get("route_status")),
            "eligibility_reasons": list(row.get("eligibility_reasons") or []),
        }
        for row in rows
        if isinstance(row, Mapping)
    ]
    return {
        "query_id": "novel_remaining_research_directions",
        "status": "matched" if shaped else "not_found",
        "rows": shaped,
        "recommended_research_action": _text(router.get("recommended_research_action")) if isinstance(router, Mapping) else "",
        "provenance": [_provenance("logs/qre_research_cycle_router/latest.json")],
    }


def _contradictory_outcomes(disposition_index: Mapping[str, Any], breadth_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    contradictions: list[dict[str, Any]] = []
    for row in breadth_rows:
        if _text(row.get("dimension")) not in {"behavior", "preset", "timeframe"}:
            continue
        if int(row.get("accepted_oos_count") or 0) > 0 and int(row.get("rejected_hypothesis_count") or 0) > 0:
            contradictions.append(
                {
                    "scope_key": _text(row.get("scope_key")),
                    "dimension": _text(row.get("dimension")),
                    "reason": "accepted_and_rejected_counts_visible_together",
                }
            )
    if not contradictions and disposition_index.get("accepted_oos_refs") and disposition_index.get("failure_classes"):
        contradictions.append(
            {
                "scope_key": _text((disposition_index.get("tested_scope") or {}).get("hypothesis_id")),
                "dimension": "tested_scope",
                "reason": "accepted_oos_refs_present_while_failure_classes_persist",
            }
        )
    return {
        "query_id": "contradictory_outcomes",
        "status": "matched" if contradictions else "not_found",
        "rows": contradictions,
        "provenance": [
            _provenance("logs/qre_hypothesis_disposition_memory/latest.json"),
            _provenance("logs/qre_evidence_breadth_framework/latest.json"),
        ],
    }


def _stale_or_superseded_knowledge(artifacts: Mapping[str, Any], memory_payload: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing_artifacts = memory_payload.get("missing_artifacts") if isinstance(memory_payload.get("missing_artifacts"), list) else []
    for artifact in missing_artifacts:
        rows.append({"artifact_path": _text(artifact), "status": "missing"})
    for path, payload in artifacts.items():
        if payload is None:
            continue
        generated = _text((payload or {}).get("generated_at_utc"))
        if not generated and _text(path):
            rows.append({"artifact_path": path, "status": "missing_generated_at_utc"})
    return {
        "query_id": "stale_or_superseded_knowledge",
        "status": "matched" if rows else "not_found",
        "rows": rows,
        "provenance": [_provenance("logs/qre_research_memory/latest.json")],
    }


def build_research_memory_retrieval(
    *,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    artifact_paths: Sequence[Path] = DEFAULT_ARTIFACT_PATHS,
) -> dict[str, Any]:
    memory = research_memory.build_research_memory(
        artifact_paths=artifact_paths,
        repo_root=repo_root,
        generated_at_utc=generated_at_utc,
    )
    artifacts = {path.as_posix(): _read_json(repo_root / path) for path in artifact_paths}
    disposition_index = _disposition_index(artifacts.get("logs/qre_hypothesis_disposition_memory/latest.json"))
    breadth_rows = _breadth_rows(artifacts.get("logs/qre_evidence_breadth_framework/latest.json"))
    source_authority = artifacts.get("logs/qre_source_identity_authority_normalization/latest.json")
    router = artifacts.get("logs/qre_research_cycle_router/latest.json")
    campaign = artifacts.get("logs/qre_preregistered_multiwindow_evidence_run/latest.json")

    queries = [
        _exact_scope_already_tested(disposition_index),
        _materially_similar_scope_rejected(disposition_index),
        _regimes_with_no_trades(disposition_index, campaign),
        _inadequate_sample_density_presets(breadth_rows),
        _recurring_failures(disposition_index, breadth_rows, source_authority),
        _novel_remaining_directions(router),
        _contradictory_outcomes(disposition_index, breadth_rows),
        _stale_or_superseded_knowledge(artifacts, memory),
    ]

    summary = {
        "status": "ready" if memory.get("summary", {}).get("research_memory_ready") else "not_ready",
        "research_memory_ready": bool(memory.get("summary", {}).get("research_memory_ready")),
        "query_count": len(queries),
        "matched_query_count": sum(1 for row in queries if row.get("status") == "matched"),
        "memory_entry_count": int(memory.get("summary", {}).get("entry_count") or 0),
        "contradiction_count": len((_contradictory_outcomes(disposition_index, breadth_rows)).get("rows") or []),
        "operator_summary": (
            "Research memory retrieval unifies tested-scope, failure, breadth, and next-cycle context with explicit provenance. "
            "Retrieval remains context only and never becomes execution or promotion authority."
        ),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc or "",
        "summary": summary,
        "artifact_paths": [path.as_posix() for path in artifact_paths],
        "missing_artifacts": list(memory.get("missing_artifacts") or []),
        "queries": queries,
        "authority_boundary": {
            "retrieval_is_context_not_truth": True,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
            "can_register_strategy": False,
            "operator_review_required": True,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(
        {
            "schema_version": report["schema_version"],
            "report_kind": report["report_kind"],
            "summary": report["summary"],
            "artifact_paths": report["artifact_paths"],
            "missing_artifacts": report["missing_artifacts"],
            "queries": report["queries"],
            "authority_boundary": report["authority_boundary"],
        }
    )
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    queries = report.get("queries") if isinstance(report.get("queries"), list) else []
    lines = [
        "# QRE Research Memory Retrieval",
        "",
        f"- research_memory_ready: {summary.get('research_memory_ready', False)}",
        f"- query_count: {summary.get('query_count', 0)}",
        f"- matched_query_count: {summary.get('matched_query_count', 0)}",
        f"- contradiction_count: {summary.get('contradiction_count', 0)}",
        "",
        "## Query Status",
    ]
    for row in queries:
        if not isinstance(row, Mapping):
            continue
        lines.append(f"- {row.get('query_id')}: {row.get('status')}")
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        prog="python -m research.qre_research_memory_retrieval",
        description="Build deterministic read-only research memory retrieval integration.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)
    report = build_research_memory_retrieval(generated_at_utc=args.frozen_utc)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
