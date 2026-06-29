from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common

REPORT_KIND: Final[str] = "qre_rejected_thesis_replacement_plan"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018i-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_rejected_thesis_replacement_plan")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_rejected_thesis_replacement_plan.md")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_OPERATOR_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
DEFAULT_INDEPENDENT_PATH: Final[Path] = Path("logs/qre_repeated_independent_oos/latest.json")
DEFAULT_CATALOG_PATH: Final[Path] = Path("research/strategy_hypothesis_catalog_latest.v1.json")
VALID_ARCHIVE_STATES: Final[tuple[str, ...]] = (
    "ARCHIVED_REJECTED",
    "ARCHIVE_BLOCKED",
)
VALID_PROPOSAL_STATES: Final[tuple[str, ...]] = (
    "PROPOSAL_ONLY",
    "NO_DISTINCT_REPLACEMENT_VISIBLE",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_rejected_thesis_replacement_plan/",
    "docs/governance/qre_rejected_thesis_replacement_plan.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
    operator_path: Path | None = None,
    independent_path: Path | None = None,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry = common.read_json(root / (registry_path or DEFAULT_REGISTRY_PATH)) or {}
    operator = common.read_json(root / (operator_path or DEFAULT_OPERATOR_PATH)) or {}
    independent = common.read_json(root / (independent_path or DEFAULT_INDEPENDENT_PATH)) or {}
    catalog = common.read_json(root / (catalog_path or DEFAULT_CATALOG_PATH)) or {}

    registry_by_hypothesis = common.index_by(common.rows(registry, "rows"), "source_hypothesis_id")
    operator_by_hypothesis = common.index_by(common.rows(operator, "rows"), "source_hypothesis_id")
    independent_by_hypothesis = common.index_by(common.rows(independent, "rows"), "source_hypothesis_id")
    catalog_rows = [dict(item) for item in (catalog.get("hypotheses") or []) if isinstance(item, dict)]

    rejected_row = operator_by_hypothesis.get("trend_pullback_v1", {})
    rejected_registry = registry_by_hypothesis.get("trend_pullback_v1", {})
    rejected_independent = independent_by_hypothesis.get("trend_pullback_v1", {})
    archive_state = "ARCHIVED_REJECTED" if common.text(rejected_row.get("final_decision")) == "REJECTED" else "ARCHIVE_BLOCKED"
    if archive_state not in VALID_ARCHIVE_STATES:
        raise ValueError(f"invalid archive_state: {archive_state}")

    replacement_catalog = next(
        (
            row for row in sorted(catalog_rows, key=lambda item: common.text(item.get("hypothesis_id")))
            if common.text(row.get("hypothesis_id")) != "trend_pullback_v1"
            and common.text(row.get("status")) == "active_discovery"
        ),
        {},
    )
    replacement_hypothesis_id = common.text(replacement_catalog.get("hypothesis_id"))
    replacement_registry = registry_by_hypothesis.get(replacement_hypothesis_id, {})
    distinct_mechanism = common.text(replacement_registry.get("behavior_family")) != common.text(rejected_registry.get("behavior_family"))
    proposal_state = "PROPOSAL_ONLY" if replacement_hypothesis_id and distinct_mechanism else "NO_DISTINCT_REPLACEMENT_VISIBLE"
    if proposal_state not in VALID_PROPOSAL_STATES:
        raise ValueError(f"invalid proposal_state: {proposal_state}")

    archive = {
        "source_hypothesis_id": "trend_pullback_v1",
        "archive_state": archive_state,
        "synthesis_state": "REJECTED_NOT_SYNTHESIS_ELIGIBLE",
        "recycle_prevention": {
            "parameter_only_clone_blocked": True,
            "threshold_tuned_resurrection_blocked": True,
            "duplicate_mechanism_family": common.text(rejected_registry.get("behavior_family")),
        },
        "consumed_oos_windows": rejected_independent.get("consumed_oos_windows") or [],
        "consumed_window_count": rejected_independent.get("consumed_window_count"),
        "independent_oos_status": common.text(rejected_independent.get("independent_oos_status")),
        "next_action": "reject_hypothesis",
        "provenance_refs": common.dedupe(
            common.normalize_list(rejected_registry.get("provenance_refs"))
            + common.normalize_list(rejected_row.get("provenance_refs"))
            + common.normalize_list(rejected_independent.get("provenance_refs"))
        ),
    }
    replacement = {
        "replacement_hypothesis_id": replacement_hypothesis_id,
        "proposal_state": proposal_state,
        "behavior_family": common.text(replacement_registry.get("behavior_family")),
        "mechanism": common.text(replacement_registry.get("mechanism")),
        "falsification_plan": common.normalize_list(replacement_registry.get("falsification_plan")),
        "data_requirements": common.normalize_list(replacement_registry.get("source_requirements")),
        "signal_density_expectation": common.text(replacement_registry.get("signal_density_expectation")),
        "null_control_plan": common.normalize_list(replacement_registry.get("null_controls")),
        "screening_plan": common.normalize_list(replacement_registry.get("screening_plan")),
        "validation_plan": common.normalize_list(replacement_registry.get("validation_plan")),
        "oos_plan": common.normalize_list(replacement_registry.get("oos_plan")),
        "supporting_context": common.normalize_list(replacement_registry.get("supporting_evidence")),
        "contradicting_context": common.normalize_list(replacement_registry.get("contradicting_evidence")),
        "campaign_ready": False,
        "next_action": "establish_campaign_lineage_for_thesis" if replacement_hypothesis_id else "requires_operator_review",
        "provenance_refs": common.dedupe(
            common.normalize_list(replacement_registry.get("provenance_refs"))
            + [common.rel(root / DEFAULT_CATALOG_PATH, root)]
        ),
    }
    replacement_identity = f"qrrp_{common.stable_digest({'archive': archive, 'replacement': replacement})[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "replacement_plan_identity": replacement_identity,
        "archive": archive,
        "replacement": replacement,
        "summary": {
            "archive_state": archive_state,
            "proposal_state": proposal_state,
            "exact_next_action": replacement["next_action"],
        },
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    archive = dict(snapshot.get("archive") or {})
    replacement = dict(snapshot.get("replacement") or {})
    return (
        "# QRE Rejected Thesis Archive And Replacement Plan\n\n"
        f"- replacement_plan_identity: `{common.text(snapshot.get('replacement_plan_identity'))}`\n"
        f"- archived: `{common.text(archive.get('source_hypothesis_id'))}` -> `{common.text(archive.get('archive_state'))}`\n"
        f"- replacement: `{common.text(replacement.get('replacement_hypothesis_id')) or 'none'}` -> `{common.text(replacement.get('proposal_state'))}`\n"
    )


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018i.", suffix=".tmp", dir=str(path.parent))
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
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_rejected_thesis_replacement_plan")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
