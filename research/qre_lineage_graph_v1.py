from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_evidence_complete_basket_closure as basket_closure
from research import qre_reason_record_normalization as reason_record_normalization
from research import qre_structured_lineage_artifacts as structured_lineage_artifacts
from research import qre_structured_oos_artifacts as structured_oos_artifacts


REPORT_KIND: Final[str] = "qre_lineage_graph_v1"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_lineage_graph_v1")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_lineage_graph_v1/"

SOURCE_LIFECYCLE_PATH: Final[Path] = Path("logs/qre_source_lifecycle_quality_gate/latest.json")
HISTORICAL_ACCOUNTING_PATH: Final[Path] = Path("logs/qre_historical_accounting_foundation/latest.json")
FACTOR_COVERAGE_PATH: Final[Path] = Path("logs/qre_factor_coverage_matrix/latest.json")
GRID_BRIDGE_PATH: Final[Path] = Path("logs/qre_grid_candidate_campaign_lineage_bridge/latest.json")
SOURCE_USEFULNESS_PATH: Final[Path] = Path("logs/qre_source_usefulness_ledger/latest.json")
SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")
HYPOTHESIS_CATALOG_PATH: Final[Path] = Path("research/strategy_hypothesis_catalog_latest.v1.json")
CAMPAIGN_REGISTRY_PATH: Final[Path] = Path("research/campaign_registry_latest.v1.json")
CAMPAIGN_DIGEST_PATH: Final[Path] = Path("research/campaign_digest_latest.v1.json")
STRUCTURED_LINEAGE_PATH: Final[Path] = Path("logs/qre_structured_lineage_artifacts/latest.json")
STRUCTURED_OOS_PATH: Final[Path] = Path("logs/qre_structured_oos_artifacts/latest.json")
EVIDENCE_CLOSURE_PATH: Final[Path] = Path("logs/qre_evidence_complete_basket_closure/latest.json")
REASON_RECORD_NORMALIZATION_PATH: Final[Path] = Path("logs/qre_reason_record_normalization/latest.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _canon(text: str) -> str:
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return "_".join(parts)


def _same_key(left: str, right: str) -> bool:
    left_canon = _canon(left)
    right_canon = _canon(right)
    return (
        left_canon == right_canon
        or left_canon in right_canon
        or right_canon in left_canon
        or left_canon.replace("_manifest", "") == right_canon.replace("_manifest", "")
        or right_canon.replace("_manifest", "") in left_canon
    )


def _add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    node_id = str(node["node_id"])
    if node_id in nodes:
        return
    nodes[node_id] = node


def _add_edge(edges: list[dict[str, Any]], source: str, target: str, relation: str, *, evidence_refs: Sequence[str] = ()) -> None:
    edges.append(
        {
            "edge_id": f"{source}->{target}:{relation}",
            "source": source,
            "target": target,
            "relation": relation,
            "evidence_refs": list(evidence_refs),
        }
    )


def _group_by_alias(rows: Sequence[Mapping[str, Any]], alias_field: str, targets: Sequence[str]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {target: [] for target in targets}
    for row in rows:
        raw = str(row.get(alias_field) or "")
        for target in targets:
            if _same_key(raw, target):
                grouped[target].append(row)
                break
    return grouped


def _load_reports(repo_root: Path) -> tuple[dict[str, Any], list[str]]:
    report_paths = {
        "source_lifecycle": SOURCE_LIFECYCLE_PATH,
        "historical_accounting": HISTORICAL_ACCOUNTING_PATH,
        "factor_coverage": FACTOR_COVERAGE_PATH,
        "grid_bridge": GRID_BRIDGE_PATH,
        "source_usefulness": SOURCE_USEFULNESS_PATH,
        "source_quality": SOURCE_QUALITY_PATH,
        "hypothesis_catalog": HYPOTHESIS_CATALOG_PATH,
        "campaign_registry": CAMPAIGN_REGISTRY_PATH,
        "campaign_digest": CAMPAIGN_DIGEST_PATH,
    }
    reports: dict[str, Any] = {}
    missing: list[str] = []
    for name, relpath in report_paths.items():
        payload = _read_json(repo_root / relpath)
        if payload is None:
            missing.append(relpath.as_posix())
        else:
            reports[name] = payload
    return reports, missing


def _rows_from_report(report: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    rows = report.get(key) if isinstance(report.get(key), list) else []
    return [row for row in rows if isinstance(row, Mapping)]


def _campaign_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    campaigns = report.get("campaigns")
    rows = list(campaigns.values()) if isinstance(campaigns, Mapping) else []
    return [row for row in rows if isinstance(row, Mapping)]


def _load_or_build(
    path: Path,
    *,
    repo_root: Path,
    builder: callable,
) -> dict[str, Any]:
    payload = _read_json(repo_root / path)
    if isinstance(payload, dict):
        return payload
    built = builder(repo_root=repo_root)
    return built if isinstance(built, dict) else {}


def build_qre_lineage_graph_v1(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    reports, missing_reports = _load_reports(repo_root)
    structured_lineage_report = _load_or_build(
        STRUCTURED_LINEAGE_PATH,
        repo_root=repo_root,
        builder=structured_lineage_artifacts.build_structured_lineage_artifacts,
    )
    structured_oos_report = _load_or_build(
        STRUCTURED_OOS_PATH,
        repo_root=repo_root,
        builder=structured_oos_artifacts.build_structured_oos_artifacts,
    )
    closure_report = _load_or_build(
        EVIDENCE_CLOSURE_PATH,
        repo_root=repo_root,
        builder=basket_closure.build_evidence_complete_basket_closure,
    )
    reason_record_normalization_report = _load_or_build(
        REASON_RECORD_NORMALIZATION_PATH,
        repo_root=repo_root,
        builder=reason_record_normalization.build_reason_record_normalization,
    )

    source_lifecycle_rows = _rows_from_report(reports.get("source_lifecycle", {}), "rows")
    historical_rows = _rows_from_report(reports.get("historical_accounting", {}), "rows")
    factor_rows = _rows_from_report(reports.get("factor_coverage", {}), "factor_rows")
    grid_rows = _rows_from_report(reports.get("grid_bridge", {}), "rows")
    source_usefulness_rows = _rows_from_report(reports.get("source_usefulness", {}), "rows")
    source_quality_rows = _rows_from_report(reports.get("source_quality", {}), "rows")
    hypotheses = _rows_from_report(reports.get("hypothesis_catalog", {}), "hypotheses")
    campaigns = _campaign_rows(reports.get("campaign_registry", {}))
    structured_lineage_rows = _rows_from_report(structured_lineage_report, "rows")
    structured_oos_rows = _rows_from_report(structured_oos_report, "rows")
    closure_rows = _rows_from_report(closure_report, "rows")
    normalized_reason_rows = _rows_from_report(reason_record_normalization_report, "normalized_records")
    digest = reports.get("campaign_digest", {})
    digest_by_lineage_root = (
        digest.get("compute_by_lineage_root")
        if isinstance(digest.get("compute_by_lineage_root"), Mapping)
        else {}
    )

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    orphan_nodes: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []

    source_node_ids: list[str] = []
    normalized_node_ids: list[str] = []
    factor_node_ids: list[str] = []
    hypothesis_node_ids: list[str] = []
    candidate_node_ids: list[str] = []
    campaign_node_ids: list[str] = []
    evidence_nodes: list[str] = []

    source_quality_groups = _group_by_alias(
        source_quality_rows,
        "source",
        [str(row.get("provider_id") or "") for row in source_lifecycle_rows],
    )
    historical_groups = _group_by_alias(
        historical_rows,
        "source_id",
        [str(row.get("provider_id") or "") for row in source_lifecycle_rows],
    )
    usefulness_groups = _group_by_alias(
        source_usefulness_rows,
        "source",
        [str(row.get("provider_id") or "") for row in source_lifecycle_rows],
    )

    for row in sorted(source_lifecycle_rows, key=lambda item: (str(item.get("provider_id") or ""), str(item.get("source_id") or ""))):
        provider_id = str(row.get("provider_id") or "")
        source_id = str(row.get("source_id") or "")
        source_node_id = f"source::{provider_id}"
        normalized_node_id = f"normalized::{provider_id}"
        source_node_ids.append(source_node_id)
        normalized_node_ids.append(normalized_node_id)
        _add_node(
            nodes,
            {
                "node_id": source_node_id,
                "node_type": "source",
                "lineage_layer": "source",
                "label": provider_id,
                "source_id": source_id,
                "provider_id": provider_id,
                "current_state": row.get("current_state"),
                "lifecycle_status": row.get("lifecycle_status"),
                "source_quality_ready": bool(row.get("source_quality_ready")),
            },
        )
        source_quality_group = source_quality_groups.get(provider_id, [])
        historical_group = historical_groups.get(provider_id, [])
        usefulness_group = usefulness_groups.get(provider_id, [])
        _add_node(
            nodes,
            {
                "node_id": normalized_node_id,
                "node_type": "normalized_data",
                "lineage_layer": "normalized_data",
                "label": provider_id,
                "provider_id": provider_id,
                "source_ids": [source_id],
                "source_quality_row_count": len(source_quality_group),
                "source_quality_ready_row_count": sum(
                    1 for item in source_quality_group if str(item.get("quality_status") or "") == "ready"
                ),
                "historical_accounting_row_count": len(historical_group),
                "source_usefulness_row_count": len(usefulness_group),
                "source_usefulness_state": (
                    str(usefulness_group[0].get("usefulness_state") or "")
                    if usefulness_group
                    else "unknown"
                ),
            },
        )
        _add_edge(edges, source_node_id, normalized_node_id, "normalizes_into", evidence_refs=[SOURCE_LIFECYCLE_PATH.as_posix(), SOURCE_QUALITY_PATH.as_posix()])

    factor_provider_sets: dict[str, set[str]] = {}
    for row in sorted(factor_rows, key=lambda item: str(item.get("factor_id") or "")):
        factor_id = str(row.get("factor_id") or "")
        factor_node_id = f"factor::{factor_id}"
        factor_node_ids.append(factor_node_id)
        provider_rows = [item for item in row.get("provider_rows", []) if isinstance(item, Mapping)]
        provider_ids = sorted({str(item.get("provider_id") or "") for item in provider_rows if str(item.get("provider_id") or "")})
        factor_provider_sets[factor_id] = set(provider_ids)
        _add_node(
            nodes,
            {
                "node_id": factor_node_id,
                "node_type": "factor",
                "lineage_layer": "factor",
                "label": factor_id,
                "field_coverage_status": row.get("field_coverage_status"),
                "provider_coverage_count": row.get("provider_coverage_count"),
                "coverage_block_reasons": row.get("coverage_block_reasons"),
                "supporting_provider_ids": provider_ids,
            },
        )
        for provider_id in sorted({str(item.get("provider_id") or "") for item in source_lifecycle_rows if str(item.get("provider_id") or "")}):
            normalized_node_id = f"normalized::{provider_id}"
            _add_edge(
                edges,
                normalized_node_id,
                factor_node_id,
                "layer_adjacency_context",
                evidence_refs=[FACTOR_COVERAGE_PATH.as_posix()],
            )

    for row in sorted(hypotheses, key=lambda item: str(item.get("hypothesis_id") or "")):
        hypothesis_id = str(row.get("hypothesis_id") or "")
        hypothesis_node_id = f"hypothesis::{hypothesis_id}"
        hypothesis_node_ids.append(hypothesis_node_id)
        _add_node(
            nodes,
            {
                "node_id": hypothesis_node_id,
                "node_type": "hypothesis",
                "lineage_layer": "hypothesis",
                "label": hypothesis_id,
                "status": row.get("status"),
                "strategy_family": row.get("strategy_family"),
                "feature_dependencies": list(row.get("feature_dependencies") or []),
                "baseline_reference": row.get("baseline_reference"),
            },
        )
        for factor_node_id in factor_node_ids:
            _add_edge(
                edges,
                factor_node_id,
                hypothesis_node_id,
                "layer_adjacency_context",
                evidence_refs=[FACTOR_COVERAGE_PATH.as_posix(), HYPOTHESIS_CATALOG_PATH.as_posix()],
            )

    candidate_nodes_by_id: dict[str, str] = {}
    for row in sorted(closure_rows, key=lambda item: str(item.get("candidate_id") or "")):
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            continue
        candidate_node_id = f"candidate::{candidate_id}"
        candidate_node_ids.append(candidate_node_id)
        candidate_nodes_by_id[candidate_id] = candidate_node_id
        _add_node(
            nodes,
            {
                "node_id": candidate_node_id,
                "node_type": "candidate",
                "lineage_layer": "candidate",
                "label": candidate_id,
                "symbol": row.get("symbol"),
                "preset_id": row.get("preset_id"),
                "closure_status": row.get("closure_status"),
                "exact_next_action": row.get("exact_next_action"),
            },
        )
        closure_node_id = f"evidence::candidate_closure::{candidate_id}"
        evidence_nodes.append(closure_node_id)
        _add_node(
            nodes,
            {
                "node_id": closure_node_id,
                "node_type": "evidence",
                "lineage_layer": "evidence",
                "label": f"candidate_closure::{candidate_id}",
                "report_kind": "qre_evidence_complete_basket_closure_row",
                "candidate_id": candidate_id,
                "closure_status": row.get("closure_status"),
                "reason_record_count": row.get("reason_record_count"),
            },
        )
        _add_edge(
            edges,
            candidate_node_id,
            closure_node_id,
            "documented_by",
            evidence_refs=[EVIDENCE_CLOSURE_PATH.as_posix()],
        )

    hypothesis_ids = {str(row.get("hypothesis_id") or "") for row in hypotheses}
    campaign_by_id = {str(row.get("campaign_id") or ""): row for row in campaigns}
    for row in sorted(campaigns, key=lambda item: str(item.get("campaign_id") or "")):
        campaign_id = str(row.get("campaign_id") or "")
        campaign_node_id = f"campaign::{campaign_id}"
        campaign_node_ids.append(campaign_node_id)
        hypothesis_id = str(row.get("hypothesis_id") or "")
        _add_node(
            nodes,
            {
                "node_id": campaign_node_id,
                "node_type": "campaign",
                "lineage_layer": "campaign",
                "label": campaign_id,
                "hypothesis_id": hypothesis_id,
                "state": row.get("state"),
                "outcome": row.get("outcome"),
                "lineage_root_campaign_id": row.get("lineage_root_campaign_id"),
                "meaningful_classification": row.get("meaningful_classification"),
            },
        )
        if hypothesis_id in hypothesis_ids:
            _add_edge(
                edges,
                f"hypothesis::{hypothesis_id}",
                campaign_node_id,
                "registry_reference",
                evidence_refs=[CAMPAIGN_REGISTRY_PATH.as_posix()],
            )
        else:
            contradictions.append(
                {
                    "contradiction_id": f"missing_hypothesis::{campaign_id}",
                    "kind": "missing_hypothesis_reference",
                    "campaign_id": campaign_id,
                    "hypothesis_id": hypothesis_id,
                    "detail": "Campaign references a hypothesis that is absent from the catalog.",
                }
            )

    report_evidence_specs = [
        ("source_lifecycle_quality_gate", SOURCE_LIFECYCLE_PATH, reports.get("source_lifecycle", {})),
        ("historical_accounting_foundation", HISTORICAL_ACCOUNTING_PATH, reports.get("historical_accounting", {})),
        ("factor_coverage_matrix", FACTOR_COVERAGE_PATH, reports.get("factor_coverage", {})),
        ("grid_candidate_campaign_lineage_bridge", GRID_BRIDGE_PATH, reports.get("grid_bridge", {})),
        ("source_usefulness_ledger", SOURCE_USEFULNESS_PATH, reports.get("source_usefulness", {})),
        ("source_quality_readiness", SOURCE_QUALITY_PATH, reports.get("source_quality", {})),
        ("strategy_hypothesis_catalog", HYPOTHESIS_CATALOG_PATH, reports.get("hypothesis_catalog", {})),
        ("campaign_registry", CAMPAIGN_REGISTRY_PATH, reports.get("campaign_registry", {})),
        ("structured_lineage_artifacts", STRUCTURED_LINEAGE_PATH, structured_lineage_report),
        ("structured_oos_artifacts", STRUCTURED_OOS_PATH, structured_oos_report),
        ("evidence_complete_basket_closure", EVIDENCE_CLOSURE_PATH, closure_report),
        ("reason_record_normalization", REASON_RECORD_NORMALIZATION_PATH, reason_record_normalization_report),
    ]
    for report_name, path, payload in report_evidence_specs:
        evidence_node_id = f"evidence::{report_name}"
        evidence_nodes.append(evidence_node_id)
        _add_node(
            nodes,
            {
                "node_id": evidence_node_id,
                "node_type": "evidence",
                "lineage_layer": "evidence",
                "label": report_name,
                "report_kind": str(payload.get("report_kind") or report_name),
                "path": path.as_posix(),
            },
        )

    for campaign_row in campaigns:
        campaign_id = str(campaign_row.get("campaign_id") or "")
        campaign_node_id = f"campaign::{campaign_id}"
        digest_row = digest_by_lineage_root.get(campaign_id)
        if isinstance(digest_row, Mapping):
            digest_node_id = f"evidence::campaign_digest::{campaign_id}"
            evidence_nodes.append(digest_node_id)
            _add_node(
                nodes,
                {
                    "node_id": digest_node_id,
                    "node_type": "evidence",
                    "lineage_layer": "evidence",
                    "label": f"campaign_digest::{campaign_id}",
                    "report_kind": "campaign_digest_lineage_root",
                    "lineage_root_campaign_id": campaign_id,
                    "actual_compute_seconds": digest_row.get("actual_compute_seconds"),
                    "children_count": digest_row.get("children_count"),
                    "meaningful_classifications": list(digest_row.get("meaningful_classifications") or []),
                },
            )
            _add_edge(
                edges,
                campaign_node_id,
                digest_node_id,
                "documented_by",
                evidence_refs=[CAMPAIGN_DIGEST_PATH.as_posix()],
            )
        else:
            contradictions.append(
                {
                    "contradiction_id": f"missing_digest::{campaign_id}",
                    "kind": "missing_campaign_digest_root",
                    "campaign_id": campaign_id,
                    "detail": "Campaign has no lineage-root digest evidence.",
                }
            )

        for evidence_node_id in (
            "evidence::source_lifecycle_quality_gate",
            "evidence::historical_accounting_foundation",
            "evidence::factor_coverage_matrix",
            "evidence::grid_candidate_campaign_lineage_bridge",
            "evidence::source_usefulness_ledger",
            "evidence::source_quality_readiness",
            "evidence::campaign_registry",
        ):
            _add_edge(
                edges,
                campaign_node_id,
                evidence_node_id,
                "documented_by",
                evidence_refs=[CAMPAIGN_DIGEST_PATH.as_posix(), GRID_BRIDGE_PATH.as_posix()],
            )

    for row in structured_lineage_rows:
        candidate_id = str(row.get("candidate_id") or "")
        campaign_id = str(row.get("campaign_id") or "")
        artifact_id = str(row.get("artifact_id") or "")
        if not artifact_id:
            continue
        evidence_node_id = f"evidence::structured_lineage::{artifact_id}"
        evidence_nodes.append(evidence_node_id)
        _add_node(
            nodes,
            {
                "node_id": evidence_node_id,
                "node_type": "evidence",
                "lineage_layer": "evidence",
                "label": f"structured_lineage::{artifact_id}",
                "report_kind": "qre_structured_lineage_artifacts_row",
                "candidate_id": candidate_id,
                "campaign_id": campaign_id,
                "validation_status": row.get("validation_status"),
            },
        )
        if candidate_id and candidate_id in candidate_nodes_by_id:
            _add_edge(
                edges,
                candidate_nodes_by_id[candidate_id],
                evidence_node_id,
                "documented_by",
                evidence_refs=[STRUCTURED_LINEAGE_PATH.as_posix()],
            )
        if campaign_id and campaign_id in campaign_by_id:
            _add_edge(
                edges,
                f"campaign::{campaign_id}",
                evidence_node_id,
                "documented_by",
                evidence_refs=[STRUCTURED_LINEAGE_PATH.as_posix()],
            )

    for row in structured_oos_rows:
        candidate_id = str(row.get("candidate_id") or "")
        artifact_id = str(row.get("artifact_id") or "")
        if not artifact_id:
            continue
        evidence_node_id = f"evidence::structured_oos::{artifact_id}"
        evidence_nodes.append(evidence_node_id)
        _add_node(
            nodes,
            {
                "node_id": evidence_node_id,
                "node_type": "evidence",
                "lineage_layer": "evidence",
                "label": f"structured_oos::{artifact_id}",
                "report_kind": "qre_structured_oos_artifacts_row",
                "candidate_id": candidate_id,
                "validation_status": row.get("validation_status"),
            },
        )
        if candidate_id and candidate_id in candidate_nodes_by_id:
            _add_edge(
                edges,
                candidate_nodes_by_id[candidate_id],
                evidence_node_id,
                "documented_by",
                evidence_refs=[STRUCTURED_OOS_PATH.as_posix()],
            )

    for row in normalized_reason_rows:
        candidate_id = str(row.get("subject_id") or "")
        if candidate_id not in candidate_nodes_by_id:
            continue
        reason_node_id = f"reason_record::{row.get('record_id') or candidate_id}"
        _add_node(
            nodes,
            {
                "node_id": reason_node_id,
                "node_type": "reason_record",
                "lineage_layer": "reason_record",
                "label": str(row.get("record_id") or candidate_id),
                "candidate_id": candidate_id,
                "record_family": row.get("record_family"),
                "contract_validation_status": (
                    (row.get("contract_validation") or {}).get("validation_status")
                    if isinstance(row.get("contract_validation"), Mapping)
                    else None
                ),
            },
        )
        _add_edge(
            edges,
            candidate_nodes_by_id[candidate_id],
            reason_node_id,
            "reason_recorded_by",
            evidence_refs=[REASON_RECORD_NORMALIZATION_PATH.as_posix()],
        )

    orphan_layer_counts = Counter()
    for node_id, node in nodes.items():
        layer = str(node.get("lineage_layer") or "unknown")
        if layer == "hypothesis":
            hypothesis_id = str(node.get("label") or "")
            if not any(edge["source"] == node_id and edge["target"].startswith("campaign::") for edge in edges):
                orphan_nodes.append(
                    {
                        "node_id": node_id,
                        "lineage_layer": layer,
                        "reason": "hypothesis_has_no_campaign_reference",
                    }
                )
                orphan_layer_counts[layer] += 1
        elif layer == "campaign":
            if not any(edge["source"] == node_id and edge["target"].startswith("evidence::") for edge in edges):
                orphan_nodes.append(
                    {
                        "node_id": node_id,
                        "lineage_layer": layer,
                        "reason": "campaign_has_no_evidence_reference",
                    }
                )
                orphan_layer_counts[layer] += 1
        elif layer == "candidate":
            if not any(edge["source"] == node_id for edge in edges):
                orphan_nodes.append(
                    {
                        "node_id": node_id,
                        "lineage_layer": layer,
                        "reason": "candidate_has_no_evidence_reference",
                    }
                )
                orphan_layer_counts[layer] += 1

    source_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "source")
    normalized_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "normalized_data")
    factor_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "factor")
    hypothesis_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "hypothesis")
    candidate_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "candidate")
    campaign_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "campaign")
    evidence_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "evidence")
    reason_record_count = sum(1 for node in nodes.values() if node.get("lineage_layer") == "reason_record")
    edge_counts = Counter(edge["relation"] for edge in edges)

    if missing_reports or contradictions:
        graph_status = "blocked"
    elif orphan_nodes:
        graph_status = "partial"
    else:
        graph_status = "ready"

    summary = {
        "source_count": source_count,
        "normalized_data_count": normalized_count,
        "factor_count": factor_count,
        "hypothesis_count": hypothesis_count,
        "candidate_count": candidate_count,
        "campaign_count": campaign_count,
        "evidence_count": evidence_count,
        "reason_record_count": reason_record_count,
        "evidence_complete_candidate_count": len(candidate_nodes_by_id),
        "structured_lineage_artifact_count": int(
            ((structured_lineage_report.get("summary") or {}).get("artifact_count")) or 0
        ),
        "structured_oos_artifact_count": int(
            ((structured_oos_report.get("summary") or {}).get("artifact_count")) or 0
        ),
        "normalized_reason_record_count": int(
            ((reason_record_normalization_report.get("summary") or {}).get("normalized_record_count")) or 0
        ),
        "edge_count": len(edges),
        "orphan_count": len(orphan_nodes),
        "contradiction_count": len(contradictions),
        "graph_status": graph_status,
        "orphan_layer_counts": dict(sorted(orphan_layer_counts.items())),
        "edge_relation_counts": dict(sorted(edge_counts.items())),
        "operator_summary": (
            "Deterministic lineage graph stays read-only and report-only. Layer-adjacency edges now expose source, "
            "normalized data, factor, hypothesis, candidate, campaign, reason-record, and evidence-closure surfaces "
            "without granting alpha authority or mutation permission."
        ),
    }

    nodes_list = sorted(nodes.values(), key=lambda row: (str(row.get("lineage_layer") or ""), str(row.get("node_id") or "")))
    edges.sort(key=lambda row: (str(row["source"]), str(row["target"]), str(row["relation"])))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": summary,
        "nodes": nodes_list,
        "edges": edges,
        "checks": {
            "missing_reports": sorted(missing_reports),
            "orphan_nodes": orphan_nodes,
            "contradictions": contradictions,
        },
        "supporting_reports": {
            "source_lifecycle_quality_gate": SOURCE_LIFECYCLE_PATH.as_posix(),
            "historical_accounting_foundation": HISTORICAL_ACCOUNTING_PATH.as_posix(),
            "factor_coverage_matrix": FACTOR_COVERAGE_PATH.as_posix(),
            "grid_candidate_campaign_lineage_bridge": GRID_BRIDGE_PATH.as_posix(),
            "source_usefulness_ledger": SOURCE_USEFULNESS_PATH.as_posix(),
            "source_quality_readiness": SOURCE_QUALITY_PATH.as_posix(),
            "strategy_hypothesis_catalog": HYPOTHESIS_CATALOG_PATH.as_posix(),
            "campaign_registry": CAMPAIGN_REGISTRY_PATH.as_posix(),
            "campaign_digest": CAMPAIGN_DIGEST_PATH.as_posix(),
            "structured_lineage_artifacts": STRUCTURED_LINEAGE_PATH.as_posix(),
            "structured_oos_artifacts": STRUCTURED_OOS_PATH.as_posix(),
            "evidence_complete_basket_closure": EVIDENCE_CLOSURE_PATH.as_posix(),
            "reason_record_normalization": REASON_RECORD_NORMALIZATION_PATH.as_posix(),
        },
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_runtime_state": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
            "trading_authority_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), Mapping) else {}
    orphan_rows = checks.get("orphan_nodes") if isinstance(checks.get("orphan_nodes"), list) else []
    contradiction_rows = checks.get("contradictions") if isinstance(checks.get("contradictions"), list) else []
    return "\n".join(
        [
            "# QRE Lineage Graph v1",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["graph_status", str(summary.get("graph_status") or "")],
                    ["source_count", str(summary.get("source_count") or 0)],
                    ["normalized_data_count", str(summary.get("normalized_data_count") or 0)],
                    ["factor_count", str(summary.get("factor_count") or 0)],
                    ["hypothesis_count", str(summary.get("hypothesis_count") or 0)],
                    ["candidate_count", str(summary.get("candidate_count") or 0)],
                    ["campaign_count", str(summary.get("campaign_count") or 0)],
                    ["evidence_count", str(summary.get("evidence_count") or 0)],
                    ["reason_record_count", str(summary.get("reason_record_count") or 0)],
                    ["orphan_count", str(summary.get("orphan_count") or 0)],
                    ["contradiction_count", str(summary.get("contradiction_count") or 0)],
                ],
            ),
            "",
            "## Orphans",
            _table(
                ["node_id", "layer", "reason"],
                [
                    [
                        str(row.get("node_id") or ""),
                        str(row.get("lineage_layer") or ""),
                        str(row.get("reason") or ""),
                    ]
                    for row in orphan_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
            "## Contradictions",
            _table(
                ["contradiction_id", "kind", "detail"],
                [
                    [
                        str(row.get("contradiction_id") or ""),
                        str(row.get("kind") or ""),
                        str(row.get("detail") or ""),
                    ]
                    for row in contradiction_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_lineage_graph_v1: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_summary, summary)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_lineage_graph_v1",
        description="Materialize the read-only QRE lineage graph report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_qre_lineage_graph_v1()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
