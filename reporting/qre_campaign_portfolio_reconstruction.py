from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common
from reporting import qre_blocked_thesis_lineage_census as census
from reporting import qre_campaign_lineage_materialization as materialization
from reporting import qre_evidence_reason_record_completion as completion
from reporting import qre_identity_ambiguity_resolution as identity
from reporting import qre_null_control_readiness as controls
from reporting import qre_rejected_thesis_replacement_plan as replacement
from reporting import qre_validation_repro_operator_completion as validation

REPORT_KIND: Final[str] = "qre_campaign_portfolio_reconstruction"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018h-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_campaign_portfolio_reconstruction")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_campaign_portfolio_reconstruction.md")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_PORTFOLIO_PATH: Final[Path] = Path("logs/qre_campaign_portfolio_plan/latest.json")
VALID_STATUSES: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "READY_WITH_LIMITATIONS",
    "BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "EXCLUDED_REJECTED",
    "EXCLUDED_DUPLICATE",
    "EXCLUDED_DEAD_ZONE",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_campaign_portfolio_reconstruction/",
    "docs/governance/qre_campaign_portfolio_reconstruction.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
    portfolio_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry = common.read_json(root / (registry_path or DEFAULT_REGISTRY_PATH)) or {}
    old_portfolio = common.read_json(root / (portfolio_path or DEFAULT_PORTFOLIO_PATH)) or {}
    census_payload = census.collect_snapshot(repo_root=root)
    identity_payload = identity.collect_snapshot(repo_root=root)
    materialization_payload = materialization.collect_snapshot(repo_root=root)
    controls_payload = controls.collect_snapshot(repo_root=root)
    completion_payload = completion.collect_snapshot(repo_root=root)
    validation_payload = validation.collect_snapshot(repo_root=root)
    replacement_payload = replacement.collect_snapshot(repo_root=root)

    old_rows = common.rows(old_portfolio, "rows")
    old_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for row in old_rows:
        old_by_hypothesis.setdefault(common.text(row.get("source_hypothesis_id")), []).append(dict(row))
    registry_rows = common.rows(registry, "rows")
    census_by_hypothesis = common.index_by(common.rows(census_payload, "rows"), "source_hypothesis_id")
    identity_by_hypothesis = common.index_by(common.rows(identity_payload, "rows"), "source_hypothesis_id")
    materialization_by_hypothesis = common.index_by(common.rows(materialization_payload, "rows"), "source_hypothesis_id")
    controls_by_hypothesis = common.index_by(common.rows(controls_payload, "rows"), "source_hypothesis_id")
    completion_by_hypothesis = common.index_by(common.rows(completion_payload, "rows"), "source_hypothesis_id")
    validation_by_hypothesis = common.index_by(common.rows(validation_payload, "rows"), "source_hypothesis_id")

    rows_out: list[dict[str, Any]] = []
    for registry_row in sorted(registry_rows, key=lambda item: common.text(item.get("source_hypothesis_id"))):
        source_hypothesis_id = common.text(registry_row.get("source_hypothesis_id"))
        existing_rows = sorted(old_by_hypothesis.get(source_hypothesis_id, [{}]), key=lambda item: common.text(item.get("preset_name")))
        if source_hypothesis_id == "trend_pullback_v1":
            existing_rows = existing_rows[:1]
        for existing in existing_rows:
            census_row = census_by_hypothesis.get(source_hypothesis_id, {})
            identity_row = identity_by_hypothesis.get(source_hypothesis_id, {})
            materialization_row = materialization_by_hypothesis.get(source_hypothesis_id, {})
            controls_row = controls_by_hypothesis.get(source_hypothesis_id, {})
            completion_row = completion_by_hypothesis.get(source_hypothesis_id, {})
            validation_row = validation_by_hypothesis.get(source_hypothesis_id, {})
            if source_hypothesis_id == "trend_pullback_v1":
                inclusion_status = "EXCLUDED_REJECTED"
                blockers = ["historical_fail_closed_rejection_preserved", "zero_accepted_oos", "consumed_oos_windows"]
                next_action = "reject_hypothesis"
            elif common.text(materialization_row.get("materialization_state")) in {"COMPLETE"} and common.text(controls_row.get("completeness_state")) == "COMPLETE":
                inclusion_status = "READY_FOR_PREREGISTRATION"
                blockers = []
                next_action = "preserve_campaign_lineage_state"
            elif common.text(materialization_row.get("materialization_state")) in {"INCOMPLETE", "IDENTITY_BLOCKED", "PRESET_MISSING", "IMPLEMENTATION_MISSING"}:
                inclusion_status = "BLOCKED"
                blockers = [
                    common.text(materialization_row.get("exact_blocker")) or "campaign_lineage_not_materialized",
                    common.text(controls_row.get("blocker")) or "null_control_not_ready",
                ]
                next_action = common.text(materialization_row.get("next_action")) or "establish_campaign_lineage_for_thesis"
            elif common.text(completion_row.get("evidence_state")) in {"MISSING", "BLOCKED"}:
                inclusion_status = "INSUFFICIENT_EVIDENCE"
                blockers = [common.text(completion_row.get("exact_blocker")) or "evidence_missing"]
                next_action = common.text(completion_row.get("next_action")) or "collect_missing_evidence"
            else:
                inclusion_status = "READY_WITH_LIMITATIONS"
                blockers = [common.text(validation_row.get("exact_blocker"))] if common.text(validation_row.get("exact_blocker")) else []
                next_action = common.text(validation_row.get("next_action")) or "collect_missing_evidence"
            if inclusion_status not in VALID_STATUSES:
                raise ValueError(f"invalid inclusion_status: {inclusion_status}")
            rows_out.append(
                {
                    "cell_id": common.text(existing.get("cell_id")) or f"qrpr_{common.stable_digest({'hypothesis': source_hypothesis_id, 'preset': common.text(existing.get('preset_name'))})[:16]}",
                    "thesis_id": common.text(registry_row.get("thesis_id")),
                    "source_hypothesis_id": source_hypothesis_id,
                    "mechanism": common.text(registry_row.get("mechanism")),
                    "preset_name": common.text(existing.get("preset_name")),
                    "proposed_universe": existing.get("proposed_universe"),
                    "proposed_timeframe": common.text(existing.get("proposed_timeframe")),
                    "identity_status": common.text(identity_row.get("resolution_state")) or "not_visible",
                    "data_readiness": existing.get("data_readiness") or {},
                    "source_readiness": existing.get("source_readiness") or {},
                    "lineage_completeness": common.text(materialization_row.get("materialization_state")) or common.text(census_row.get("lineage_status")),
                    "evidence_completeness": common.text(completion_row.get("evidence_state")),
                    "null_control_completeness": common.text(controls_row.get("completeness_state")),
                    "expected_signal_density": existing.get("expected_signal_density") or {},
                    "minimum_sample": existing.get("minimum_sample") or {},
                    "available_train_window": existing.get("available_train_window") or {},
                    "available_validation_window": existing.get("available_validation_window") or {},
                    "available_oos_capacity": existing.get("available_oos_window") or {},
                    "costs_and_slippage_readiness": existing.get("cost_and_slippage_readiness") or {},
                    "duplicate_status": existing.get("duplicate_risk_status") or {},
                    "dead_zone_status": existing.get("dead_zone_status") or {},
                    "inclusion_status": inclusion_status,
                    "blockers": common.dedupe(blockers),
                    "next_action": next_action,
                    "provenance_refs": common.dedupe(
                        common.normalize_list(existing.get("provenance_refs"))
                        + common.normalize_list(census_row.get("provenance_refs"))
                        + common.normalize_list(identity_row.get("provenance_refs"))
                        + common.normalize_list(completion_row.get("provenance_refs"))
                        + common.normalize_list(validation_row.get("provenance_refs"))
                    ),
                }
            )

    rows_out.sort(key=lambda item: (common.text(item.get("source_hypothesis_id")), common.text(item.get("preset_name")), common.text(item.get("cell_id"))))
    status_counts = {
        status: sum(1 for row in rows_out if row["inclusion_status"] == status)
        for status in VALID_STATUSES
    }
    ready_count = status_counts["READY_FOR_PREREGISTRATION"]
    prep_identity = f"qrpr_{common.stable_digest({'rows': rows_out, 'replacement': replacement_payload.get('replacement_plan_identity')})[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "portfolio_reconstruction_identity": prep_identity,
        "rows": rows_out,
        "replacement_plan_identity": replacement_payload.get("replacement_plan_identity"),
        "preregistration_preparation": {
            "status": "blocked_no_ready_cells" if ready_count == 0 else "ready_cells_visible",
            "manifest_materialized": ready_count > 0,
            "exact_blockers": common.dedupe(
                [blocker for row in rows_out if row["inclusion_status"] != "READY_FOR_PREREGISTRATION" for blocker in common.normalize_list(row.get("blockers"))]
            )[:10],
        },
        "summary": {
            "cell_count": len(rows_out),
            "status_counts": status_counts,
            "ready_cell_count": ready_count,
            "exact_next_action": "prepare_second_campaign_only_if_ready_cells_exist",
        },
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# QRE Campaign Portfolio Reconstruction",
        "",
        f"- portfolio_reconstruction_identity: `{common.text(snapshot.get('portfolio_reconstruction_identity'))}`",
        f"- preregistration_preparation_status: `{common.text((snapshot.get('preregistration_preparation') or {}).get('status'))}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if isinstance(row, dict):
            lines.append(
                f"- `{common.text(row.get('source_hypothesis_id'))}` / `{common.text(row.get('preset_name')) or 'thesis_only'}`: `{common.text(row.get('inclusion_status'))}` -> `{common.text(row.get('next_action'))}`"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018h.", suffix=".tmp", dir=str(path.parent))
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
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_campaign_portfolio_reconstruction")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
