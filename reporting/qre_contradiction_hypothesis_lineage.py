from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Final

from research import qre_behavior_thesis_evidence as thesis_evidence
from research import qre_behavior_thesis_registry as thesis_registry
from research import qre_contradiction_staleness_intelligence as contradiction_intelligence
from research import qre_lineage_graph_v1 as lineage_graph


REPORT_KIND: Final[str] = "qre_contradiction_hypothesis_lineage"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017s-2026-06-27"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_contradiction_hypothesis_lineage.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_contradiction_hypothesis_lineage/",
    "docs/governance/qre_contradiction_hypothesis_lineage.md",
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


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_contradiction_hypothesis_lineage: refusing write outside allowlist: {path!r}"
        )


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return out


def _build_graph_indexes(report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    nodes = {
        _text(node.get("node_id")): dict(node)
        for node in report.get("nodes", [])
        if isinstance(node, dict) and _text(node.get("node_id"))
    }
    edges_by_source: dict[str, list[dict[str, Any]]] = {}
    for edge in report.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = _text(edge.get("source"))
        if not source:
            continue
        edges_by_source.setdefault(source, []).append(dict(edge))
    return nodes, edges_by_source


def _thesis_evidence_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("thesis_id")): dict(row)
        for row in rows
        if _text(row.get("thesis_id"))
    }


def _contradiction_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        scope_key = _text(row.get("scope_key"))
        if not scope_key:
            continue
        indexed.setdefault(scope_key, []).append(dict(row))
    return indexed


def build_contradiction_hypothesis_lineage(
    *,
    repo_root: Path | None = None,
    thesis_registry_report: dict[str, Any] | None = None,
    thesis_evidence_report: dict[str, Any] | None = None,
    lineage_graph_report: dict[str, Any] | None = None,
    contradiction_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    thesis_registry_report = thesis_registry_report or thesis_registry.build_behavior_thesis_registry(
        repo_root=root
    )
    thesis_evidence_report = thesis_evidence_report or thesis_evidence.build_behavior_thesis_evidence(
        repo_root=root
    )
    lineage_graph_report = lineage_graph_report or lineage_graph.build_qre_lineage_graph_v1(
        repo_root=root
    )
    contradiction_report = contradiction_report or contradiction_intelligence.build_contradiction_staleness_intelligence(
        repo_root=root
    )

    thesis_rows = _read_rows(thesis_registry_report, "rows")
    evidence_rows = _read_rows(thesis_evidence_report, "rows")
    graph_nodes, graph_edges_by_source = _build_graph_indexes(lineage_graph_report)
    evidence_by_thesis = _thesis_evidence_index(evidence_rows)
    contradictions_by_scope = _contradiction_index(_read_rows(contradiction_report, "contradictions"))
    stale_rows = _read_rows(contradiction_report, "stale_or_superseded")
    orphan_nodes = {
        _text(row.get("node_id")): dict(row)
        for row in ((lineage_graph_report.get("checks") or {}).get("orphan_nodes") or [])
        if isinstance(row, dict)
    }

    rows: list[dict[str, Any]] = []
    orphan_count = 0
    missing_lineage_count = 0

    for thesis_row in sorted(thesis_rows, key=lambda row: (_text(row.get("thesis_id")), _text(row.get("source_hypothesis_id")))):
        thesis_id = _text(thesis_row.get("thesis_id"))
        source_hypothesis_id = _text(thesis_row.get("source_hypothesis_id"))
        hypothesis_node_id = f"hypothesis::{source_hypothesis_id}" if source_hypothesis_id else ""
        evidence_row = evidence_by_thesis.get(thesis_id, {})
        hypothesis_node = graph_nodes.get(hypothesis_node_id, {})
        hypothesis_edges = graph_edges_by_source.get(hypothesis_node_id, [])
        campaign_ids = sorted(
            {
                _text(edge.get("target"))
                for edge in hypothesis_edges
                if _text(edge.get("relation")) == "registry_reference"
                and _text(edge.get("target")).startswith("campaign::")
            }
        )
        campaign_nodes = [graph_nodes[campaign_id] for campaign_id in campaign_ids if campaign_id in graph_nodes]
        campaign_outcomes = _dedupe([_text(node.get("outcome")) for node in campaign_nodes])
        contradiction_rows = contradictions_by_scope.get(source_hypothesis_id, []) + contradictions_by_scope.get(
            campaign_ids[0] if campaign_ids else "", []
        )
        contradiction_rows = [row for row in contradiction_rows if isinstance(row, dict)]
        item_rows = [
            dict(item)
            for item in evidence_row.get("evidence_items", [])
            if isinstance(item, dict)
        ]
        supporting_refs = _dedupe(
            [str(item.get("evidence_ref") or "") for item in item_rows if _text(item.get("stance")) == "supporting"]
        )
        contradicting_refs = _dedupe(
            [str(item.get("evidence_ref") or "") for item in item_rows if _text(item.get("stance")) == "contradicting"]
        )
        unresolved_refs = _dedupe(
            [str(item.get("evidence_ref") or "") for item in item_rows if _text(item.get("stance")) == "unresolved"]
        )

        missing_lineage_fields: list[str] = []
        source_identity_ids: list[str] = []
        data_snapshot_ids: list[str] = []
        if not source_hypothesis_id:
            missing_lineage_fields.append("source_hypothesis_id")
        if not hypothesis_node:
            missing_lineage_fields.append("hypothesis_graph_node")
        if not campaign_ids:
            missing_lineage_fields.extend(
                [
                    "campaign_identity",
                    "funnel_result",
                    "data_snapshot_identity",
                    "source_identity",
                    "policy_decision",
                    "next_action_bridge",
                ]
            )
        if campaign_ids:
            for campaign_id in campaign_ids:
                campaign_edges = graph_edges_by_source.get(campaign_id, [])
                for edge in campaign_edges:
                    if _text(edge.get("relation")) != "documented_by":
                        continue
                    target = _text(edge.get("target"))
                    if target.startswith("evidence::source_"):
                        source_identity_ids.append(target)
                    if target.startswith("evidence::historical_accounting"):
                        data_snapshot_ids.append(target)
            if not data_snapshot_ids:
                missing_lineage_fields.append("data_snapshot_identity")
            if not source_identity_ids:
                missing_lineage_fields.append("source_identity")
        stale_refs = _dedupe([_text(row.get("artifact_path")) for row in stale_rows])

        orphan_reason = _text((orphan_nodes.get(hypothesis_node_id) or {}).get("reason"))
        is_orphan = bool(orphan_reason)
        if is_orphan:
            orphan_count += 1
        if missing_lineage_fields:
            missing_lineage_count += 1

        next_action = (
            "establish_campaign_lineage_for_thesis"
            if not campaign_ids
            else _text((contradiction_report.get("summary") or {}).get("exact_next_action"))
            or "preserve_visible_lineage_context"
        )
        policy_decision = (
            "blocked_missing_campaign_lineage"
            if not campaign_ids
            else "context_only_visible_no_execution_authority"
        )
        row = {
            "stable_id": thesis_id,
            "thesis_id": thesis_id,
            "source_hypothesis_id": source_hypothesis_id,
            "behavior_family": _text(thesis_row.get("behavior_family")),
            "title": _text(thesis_row.get("title")),
            "graph_nodes": {
                "source": source_identity_ids,
                "data_snapshot": data_snapshot_ids,
                "behavior_thesis": hypothesis_node_id,
                "campaign": campaign_ids,
                "funnel_result": campaign_outcomes,
                "evidence": _dedupe(supporting_refs + contradicting_refs + unresolved_refs),
                "failure_or_survival": campaign_outcomes,
                "policy_decision": policy_decision,
                "next_action": next_action,
            },
            "supporting_evidence_refs": supporting_refs,
            "contradicting_evidence_refs": contradicting_refs,
            "unresolved_evidence_refs": unresolved_refs,
            "contradiction_rows": contradiction_rows,
            "orphan_status": {
                "is_orphan": is_orphan,
                "reason": orphan_reason or "none",
            },
            "missing_lineage_fields": _dedupe(missing_lineage_fields),
            "lineage_complete": not missing_lineage_fields,
            "lineage_layer_status": {
                "source_present": bool(source_identity_ids),
                "data_snapshot_present": bool(data_snapshot_ids),
                "behavior_thesis_present": bool(hypothesis_node),
                "campaign_present": bool(campaign_ids),
                "funnel_result_present": bool(campaign_outcomes),
                "policy_decision_present": True,
                "next_action_present": True,
            },
            "provenance_refs": _dedupe(
                [*list(thesis_row.get("provenance_refs") or [])]
                + [*list(evidence_row.get("provenance_refs") or [])]
                + [str(ref) for ref in stale_refs]
                + ["logs/qre_lineage_graph_v1/latest.json", "logs/qre_contradiction_staleness_intelligence/latest.json"]
            ),
        }
        rows.append(row)

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "thesis_count": len(rows),
            "orphan_thesis_count": orphan_count,
            "missing_lineage_count": missing_lineage_count,
            "support_visible_count": sum(1 for row in rows if row["supporting_evidence_refs"]),
            "contradiction_visible_count": sum(1 for row in rows if row["contradicting_evidence_refs"]),
            "unresolved_visible_count": sum(1 for row in rows if row["unresolved_evidence_refs"]),
            "complete_lineage_count": sum(1 for row in rows if row["lineage_complete"]),
            "graph_status": _text((lineage_graph_report.get("summary") or {}).get("graph_status")) or "missing",
            "final_recommendation": (
                "lineage_visible_with_explicit_gaps" if rows else "missing_thesis_registry"
            ),
            "operator_summary": (
                "Contradiction and hypothesis lineage stays read-only and context-only. "
                "The report binds each thesis to graph-visible lineage, supporting/contradicting/unresolved evidence, "
                "and explicit orphan or missing-lineage states without inventing absent campaign, source, or snapshot links."
            ),
        },
        "rows": rows,
        "artifact_references": {
            "thesis_registry": "logs/qre_behavior_thesis_registry/latest.json",
            "thesis_evidence": "logs/qre_behavior_thesis_evidence/latest.json",
            "lineage_graph_v1": "logs/qre_lineage_graph_v1/latest.json",
            "contradiction_staleness_intelligence": "logs/qre_contradiction_staleness_intelligence/latest.json",
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_launch_campaign": False,
            "can_authorize_execution": False,
            "can_register_strategy": False,
        },
        "safety_invariants": {
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "mutates_runtime_state": False,
            "uses_only_repository_artifacts": True,
        },
    }


def render_doc(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Contradiction Hypothesis Lineage",
        "",
        f"- thesis_count: {summary.get('thesis_count', 0)}",
        f"- orphan_thesis_count: {summary.get('orphan_thesis_count', 0)}",
        f"- missing_lineage_count: {summary.get('missing_lineage_count', 0)}",
        f"- complete_lineage_count: {summary.get('complete_lineage_count', 0)}",
        f"- graph_status: {summary.get('graph_status', '')}",
        "",
        "| thesis_id | source_hypothesis_id | campaign_count | orphan | missing_lineage_fields |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("thesis_id")),
                    _text(row.get("source_hypothesis_id")),
                    str(len((row.get("graph_nodes") or {}).get("campaign") or [])),
                    str(bool((row.get("orphan_status") or {}).get("is_orphan"))),
                    ", ".join(row.get("missing_lineage_fields") or []) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "The graph is context and lineage only. Missing source, snapshot, campaign, or decision links remain explicit rather than inferred.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path.cwd()
    base = root / DEFAULT_OUTPUT_DIR
    latest = base / LATEST_NAME
    doc = root / DOC_PATH
    base.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    for path in (latest, doc):
        _validate_write_target(path)
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, latest)
    doc.write_text(render_doc(report), encoding="utf-8")
    return {
        "latest": latest.relative_to(root).as_posix(),
        "doc": doc.relative_to(root).as_posix(),
    }


def read_status(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    payload = _read_json(root / DEFAULT_OUTPUT_DIR / LATEST_NAME)
    if not payload:
        return {
            "status": "missing",
            "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
            "fails_closed": True,
        }
    return {
        "status": "ready",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_status(), indent=2, sort_keys=True))
        return 0
    report = build_contradiction_hypothesis_lineage()
    if args.write:
        print(json.dumps(write_outputs(report), indent=2, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
