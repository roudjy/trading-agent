from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common

REPORT_KIND: Final[str] = "qre_blocked_thesis_lineage_census"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018b-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_blocked_thesis_lineage_census")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_blocked_thesis_lineage_census.md")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage/latest.json")
DEFAULT_OPERATOR_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
DEFAULT_IDENTITY_PATH: Final[Path] = Path("logs/qre_source_identity_authority_normalization/latest.json")
DEFAULT_CACHE_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
DEFAULT_CAMPAIGN_METADATA_PATH: Final[Path] = Path("research/strategy_campaign_metadata_latest.v1.json")
DEFAULT_TEMPLATES_PATH: Final[Path] = Path("research/campaign_templates_latest.v1.json")
DEFAULT_PRESETS_PATH: Final[Path] = Path("research/presets.py")
DEFAULT_GENERATED_REGISTRY_PATH: Final[Path] = Path("generated_research/registry/generated_strategy_registry.v1.json")
DEFAULT_GENERATED_PRESETS_PATH: Final[Path] = Path("generated_research/presets/generated_research_presets.v1.json")
DEFAULT_GENERATED_LINEAGE_PATH: Final[Path] = Path("generated_research/lineage/generated_campaign_lineage.v1.json")
VALID_LINEAGE_STATUSES: Final[tuple[str, ...]] = (
    "LINEAGE_COMPLETE",
    "LINEAGE_PARTIAL",
    "LINEAGE_MISSING",
    "IDENTITY_BLOCKED",
    "IMPLEMENTATION_MISSING",
    "PRESET_MISSING",
    "DATA_BLOCKED",
    "CONTROL_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_blocked_thesis_lineage_census/",
    "docs/governance/qre_blocked_thesis_lineage_census.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return None


def _build_scope_index(identity_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in common.rows(identity_report, "rows"):
        behavior_id = common.text(row.get("behavior_id"))
        if behavior_id:
            indexed.setdefault(behavior_id, []).append(dict(row))
    return indexed


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
    lineage_path: Path | None = None,
    operator_path: Path | None = None,
    identity_path: Path | None = None,
    cache_path: Path | None = None,
    campaign_metadata_path: Path | None = None,
    templates_path: Path | None = None,
    presets_path: Path | None = None,
    generated_registry_path: Path | None = None,
    generated_presets_path: Path | None = None,
    generated_lineage_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry = common.read_json(root / (registry_path or DEFAULT_REGISTRY_PATH)) or {}
    lineage = common.read_json(root / (lineage_path or DEFAULT_LINEAGE_PATH)) or {}
    operator = common.read_json(root / (operator_path or DEFAULT_OPERATOR_PATH)) or {}
    identity = common.read_json(root / (identity_path or DEFAULT_IDENTITY_PATH)) or {}
    cache = common.read_json(root / (cache_path or DEFAULT_CACHE_PATH)) or {}
    campaign_metadata = common.read_json(root / (campaign_metadata_path or DEFAULT_CAMPAIGN_METADATA_PATH)) or {}
    templates = common.read_json(root / (templates_path or DEFAULT_TEMPLATES_PATH)) or {}
    presets = common.parse_preset_catalog(_read_text(root / (presets_path or DEFAULT_PRESETS_PATH)))
    generated_registry = common.read_json(root / (generated_registry_path or DEFAULT_GENERATED_REGISTRY_PATH)) or {}
    generated_presets = common.read_json(root / (generated_presets_path or DEFAULT_GENERATED_PRESETS_PATH)) or {}
    generated_lineage = common.read_json(root / (generated_lineage_path or DEFAULT_GENERATED_LINEAGE_PATH)) or {}

    registry_rows = common.rows(registry, "rows")
    if not registry_rows:
        registry_rows = []
        for row in common.read_markdown_table_rows(root / DOC_PATH.parent / "qre_behavior_thesis_registry.md"):
            source_hypothesis_id = common.text(row.get("source_hypothesis_id"))
            registry_rows.append(
                {
                    "thesis_id": common.text(row.get("thesis_id")),
                    "source_hypothesis_id": source_hypothesis_id,
                    "behavior_family": common.text(row.get("behavior_family")),
                    "mechanism": source_hypothesis_id,
                    "universe": "",
                    "screening_plan": "",
                    "validation_plan": "",
                    "oos_plan": "",
                    "null_controls": [],
                    "provenance_refs": ["docs/governance/qre_behavior_thesis_registry.md"],
                }
            )
    operator_rows = common.rows(operator, "rows")
    if not operator_rows:
        blocked_or_rejected = common.read_markdown_table_rows(root / DOC_PATH.parent / "qre_operator_decision_report.md")
        title_to_hypothesis = {
            "Trend Continuation: atr_adaptive_trend_v0": "atr_adaptive_trend_v0",
            "Index Regime Filter: regime_diagnostics_v1": "regime_diagnostics_v1",
            "Trend Continuation: multi_asset_trend_sleeve_v0": "multi_asset_trend_sleeve_v0",
            "Relative Strength: cross_sectional_momentum_v0": "cross_sectional_momentum_v0",
            "Mean Reversion: dynamic_pairs_v0": "dynamic_pairs_v0",
            "Pullback Continuation: trend_pullback_v1": "trend_pullback_v1",
            "Volatility Compression Breakout: volatility_compression_breakout_v0": "volatility_compression_breakout_v0",
        }
        operator_rows = [
            {
                "source_hypothesis_id": title_to_hypothesis.get(common.text(row.get("Thesis")), ""),
                "final_decision": common.text(row.get("Decision")),
                "next_action": common.text(row.get("Next action")),
                "primary_reasons": common.text(row.get("Primary reasons")).split("; "),
                "provenance_refs": ["docs/governance/qre_operator_decision_report.md"],
            }
            for row in blocked_or_rejected
            if title_to_hypothesis.get(common.text(row.get("Thesis")), "")
        ]
    lineage_by_hypothesis = common.index_by(common.rows(lineage, "rows"), "source_hypothesis_id")
    operator_by_hypothesis = common.index_by(operator_rows, "source_hypothesis_id")
    identity_by_behavior = _build_scope_index(identity)
    coverage_rows = common.rows(cache, "coverage")
    metadata_hypotheses = campaign_metadata.get("hypotheses")
    metadata_by_hypothesis = dict(metadata_hypotheses) if isinstance(metadata_hypotheses, dict) else {}
    template_rows = templates.get("templates")
    template_rows = [dict(row) for row in template_rows if isinstance(row, dict)] if isinstance(template_rows, list) else []
    generated_registry_by_hypothesis = common.index_by(common.rows(generated_registry, "rows"), "source_hypothesis_id")
    generated_lineage_by_hypothesis = common.index_by(common.rows(generated_lineage, "rows"), "source_hypothesis_id")
    preset_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for row in presets:
        hypothesis_id = common.text(row.get("hypothesis_id"))
        if hypothesis_id:
            preset_by_hypothesis.setdefault(hypothesis_id, []).append(dict(row))
    generated_preset_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for row in common.rows(generated_presets, "rows"):
        hypothesis_id = common.text(row.get("source_hypothesis_id"))
        if hypothesis_id:
            generated_preset_by_hypothesis.setdefault(hypothesis_id, []).append(dict(row))

    rows_out: list[dict[str, Any]] = []
    for registry_row in sorted(registry_rows, key=lambda item: common.text(item.get("source_hypothesis_id"))):
        source_hypothesis_id = common.text(registry_row.get("source_hypothesis_id"))
        operator_row = operator_by_hypothesis.get(source_hypothesis_id, {})
        final_decision = common.text(operator_row.get("final_decision"))
        if final_decision and final_decision not in {"BLOCKED", "REJECTED"}:
            continue
        lineage_row = lineage_by_hypothesis.get(source_hypothesis_id, {})
        behavior_family = common.text(registry_row.get("behavior_family"))
        identity_rows: list[dict[str, Any]] = []
        for key in common.behavior_keys(behavior_family):
            identity_rows.extend(identity_by_behavior.get(key, []))
        identity_rows.sort(key=lambda item: (common.text(item.get("symbol")), common.text(item.get("provider_symbol"))))
        preset_rows = sorted(
            preset_by_hypothesis.get(source_hypothesis_id, []),
            key=lambda row: common.text(row.get("name")),
        )
        template_candidates = sorted(
            [
                row for row in template_rows
                if common.text(row.get("preset_name")) in {common.text(item.get("name")) for item in preset_rows}
            ],
            key=lambda row: (common.text(row.get("campaign_type")), common.text(row.get("preset_name"))),
        )
        generated_registry_row = generated_registry_by_hypothesis.get(source_hypothesis_id, {})
        generated_lineage_row = generated_lineage_by_hypothesis.get(source_hypothesis_id, {})
        generated_preset_rows = sorted(
            generated_preset_by_hypothesis.get(source_hypothesis_id, []),
            key=lambda row: common.text(row.get("preset_name")),
        )
        metadata_row = dict(metadata_by_hypothesis.get(source_hypothesis_id) or {})
        eligible_campaign_types = common.normalize_list(metadata_row.get("eligible_campaign_types"))
        missing_lineage_fields = common.normalize_list(lineage_row.get("missing_lineage_fields"))
        identity_blocked = any(
            common.text(item.get("authority_status")).startswith("blocked_")
            or common.text(item.get("resolution_status")) in {"AMBIGUOUS_BLOCKED", "CONFLICTING"}
            for item in identity_rows
        )
        data_coverage_ready = any(bool(row.get("ready")) for row in coverage_rows)
        generated_strategy_identity = common.text(generated_registry_row.get("generated_strategy_id"))
        generated_campaign_identity = common.text(generated_lineage_row.get("campaign_specification_identity"))
        has_any_preset = bool(preset_rows or generated_preset_rows)
        if generated_strategy_identity and not has_any_preset:
            lineage_status = "PRESET_MISSING"
            exact_blocker = "generated_strategy_registered_but_preset_missing"
            next_action = "generate_bounded_research_preset"
        elif not eligible_campaign_types and not generated_strategy_identity:
            lineage_status = "IMPLEMENTATION_MISSING"
            exact_blocker = "campaign_metadata_missing_or_ineligible"
            next_action = "establish_campaign_lineage_for_thesis"
        elif not has_any_preset:
            lineage_status = "PRESET_MISSING"
            exact_blocker = "preset_identity_missing"
            next_action = "establish_campaign_lineage_for_thesis"
        elif identity_blocked:
            lineage_status = "IDENTITY_BLOCKED"
            exact_blocker = "identity_authority_blocked"
            next_action = "resolve_identity_ambiguity_for_thesis"
        elif not data_coverage_ready:
            lineage_status = "DATA_BLOCKED"
            exact_blocker = "cache_coverage_missing"
            next_action = "materialize_qre_data_readiness_for_scope"
        elif generated_campaign_identity:
            lineage_status = "LINEAGE_COMPLETE"
            exact_blocker = "none"
            next_action = "preserve_lineage_state"
        elif missing_lineage_fields:
            lineage_status = "LINEAGE_PARTIAL"
            exact_blocker = "campaign_lineage_not_materialized"
            next_action = "materialize_campaign_lineage_for_thesis"
        else:
            lineage_status = "LINEAGE_COMPLETE"
            exact_blocker = "none"
            next_action = "preserve_lineage_state"
        strategy_identity = generated_strategy_identity or (source_hypothesis_id if eligible_campaign_types else "")
        preset_identity = (
            common.text(generated_preset_rows[0].get("preset_name"))
            if generated_preset_rows
            else common.text(preset_rows[0].get("name")) if preset_rows else ""
        )
        representative_identity = identity_rows[0] if identity_rows else {}
        row = {
            "stable_id": f"qrlc_{common.stable_digest({'hypothesis': source_hypothesis_id})[:16]}",
            "thesis_id": common.text(registry_row.get("thesis_id")),
            "source_hypothesis_id": source_hypothesis_id,
            "behavior_family": behavior_family,
            "mechanism": common.text(registry_row.get("mechanism")),
            "strategy_implementation_identity": strategy_identity,
            "preset_identity": preset_identity,
            "universe": common.text(registry_row.get("universe")),
            "timeframe": (
                common.text(generated_preset_rows[0].get("timeframe"))
                if generated_preset_rows
                else common.text(preset_rows[0].get("timeframe")) if preset_rows else ""
            ),
            "source_identity": common.text(representative_identity.get("provider_symbol")) if representative_identity else "",
            "instrument_identity": common.text(representative_identity.get("symbol")) if representative_identity else "",
            "dataset_identity": common.text(representative_identity.get("source_quality_status")) if representative_identity else "",
            "snapshot_identity": "",
            "campaign_identity": generated_campaign_identity or (common.text((lineage_row.get("graph_nodes") or {}).get("campaign")[0]) if isinstance((lineage_row.get("graph_nodes") or {}).get("campaign"), list) and (lineage_row.get("graph_nodes") or {}).get("campaign") else ""),
            "screening_plan": common.text(registry_row.get("screening_plan")) or "blocked:screening_plan_not_materialized",
            "validation_plan": common.text(registry_row.get("validation_plan")) or "blocked:validation_plan_not_materialized",
            "oos_plan": common.text(registry_row.get("oos_plan")) or "blocked:oos_plan_not_materialized",
            "null_controls": common.normalize_list(registry_row.get("null_controls")),
            "reason_records": common.normalize_list(operator_row.get("primary_reasons")),
            "supporting_evidence": common.normalize_list(lineage_row.get("supporting_evidence_refs")),
            "contradicting_evidence": common.normalize_list(lineage_row.get("contradicting_evidence_refs")),
            "existing_lineage_links": common.normalize_list((lineage_row.get("graph_nodes") or {}).get("campaign")) + common.normalize_list(generated_campaign_identity),
            "missing_lineage_links": missing_lineage_fields,
            "lineage_status": lineage_status,
            "exact_blocker": exact_blocker,
            "next_action": next_action,
            "eligible_campaign_types": eligible_campaign_types,
            "template_ids": [common.text(row.get("template_id")) for row in template_candidates],
            "provenance_refs": common.dedupe(
                common.normalize_list(registry_row.get("provenance_refs"))
                + common.normalize_list(lineage_row.get("provenance_refs"))
                + common.normalize_list(operator_row.get("provenance_refs"))
                + [
                    common.rel(root / DEFAULT_IDENTITY_PATH, root),
                    common.rel(root / DEFAULT_CACHE_PATH, root),
                    common.rel(root / DEFAULT_CAMPAIGN_METADATA_PATH, root),
                    common.rel(root / DEFAULT_TEMPLATES_PATH, root),
                    common.rel(root / DEFAULT_PRESETS_PATH, root),
                    common.rel(root / (generated_registry_path or DEFAULT_GENERATED_REGISTRY_PATH), root),
                    common.rel(root / (generated_presets_path or DEFAULT_GENERATED_PRESETS_PATH), root),
                    common.rel(root / (generated_lineage_path or DEFAULT_GENERATED_LINEAGE_PATH), root),
                ]
            ),
        }
        if row["lineage_status"] not in VALID_LINEAGE_STATUSES:
            raise ValueError(f"invalid lineage status: {row['lineage_status']}")
        rows_out.append(row)

    rows_out.sort(key=lambda item: item["source_hypothesis_id"])
    identity_blocked_count = sum(1 for row in rows_out if row["lineage_status"] == "IDENTITY_BLOCKED")
    partial_count = sum(1 for row in rows_out if row["lineage_status"] == "LINEAGE_PARTIAL")
    complete_count = sum(1 for row in rows_out if row["lineage_status"] == "LINEAGE_COMPLETE")
    snapshot_core = {
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "lineage_complete_count": complete_count,
            "lineage_partial_count": partial_count,
            "identity_blocked_count": identity_blocked_count,
        },
    }
    census_identity = f"qrlc_{common.stable_digest(snapshot_core)[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "lineage_census_identity": census_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "lineage_complete_count": complete_count,
            "lineage_partial_count": partial_count,
            "identity_blocked_count": identity_blocked_count,
            "exact_next_action": "resolve_identity_and_campaign_lineage_for_blocked_theses",
        },
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# QRE Blocked-Thesis Lineage Census",
        "",
        f"- lineage_census_identity: `{common.text(snapshot.get('lineage_census_identity'))}`",
        f"- thesis_count: `{snapshot.get('summary', {}).get('thesis_count', 0)}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{common.text(row.get('source_hypothesis_id'))}`: `{common.text(row.get('lineage_status'))}` -> `{common.text(row.get('next_action'))}`"
        )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018b.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    markdown = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_MARKDOWN, markdown)
    _atomic_write(DOC_PATH, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_blocked_thesis_lineage_census")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
