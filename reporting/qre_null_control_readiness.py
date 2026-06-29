from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Final

from reporting import qre_ade018_common as common
from reporting import qre_campaign_lineage_materialization as materialization

REPORT_KIND: Final[str] = "qre_null_control_readiness"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018e-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_null_control_readiness")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_null_control_readiness.md")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_campaign_lineage_materialization/latest.json")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_OPERATOR_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
VALID_STATES: Final[tuple[str, ...]] = (
    "COMPLETE",
    "SPECIFIED_NOT_EXECUTED",
    "IMPLEMENTATION_MISSING",
    "DATA_BLOCKED",
    "NOT_APPLICABLE_WITH_REASON",
    "INSUFFICIENT_EVIDENCE",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_null_control_readiness/",
    "docs/governance/qre_null_control_readiness.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _null_rationale(behavior_family: str) -> list[str]:
    mapping = {
        "trend_continuation": ["matched_frequency_null", "sign_flipped_signal"],
        "volatility_compression_breakout": ["shuffled_signal_timing", "matched_frequency_null"],
        "cross_sectional_momentum": ["permuted_cross_sectional_ranking"],
        "mean_reversion": ["randomized_entry_timing", "cost_only_baseline"],
    }
    return mapping.get(behavior_family, ["matched_frequency_null"])


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    lineage_path: Path | None = None,
    registry_path: Path | None = None,
    operator_path: Path | None = None,
) -> dict[str, object]:
    root = repo_root or Path.cwd()
    lineage = common.read_json(root / (lineage_path or DEFAULT_LINEAGE_PATH))
    if lineage is None:
        lineage = materialization.collect_snapshot(repo_root=root)
    registry = common.read_json(root / (registry_path or DEFAULT_REGISTRY_PATH)) or {}
    operator = common.read_json(root / (operator_path or DEFAULT_OPERATOR_PATH)) or {}
    registry_by_hypothesis = common.index_by(common.rows(registry, "rows"), "source_hypothesis_id")
    operator_by_hypothesis = common.index_by(common.rows(operator, "rows"), "source_hypothesis_id")
    rows_out: list[dict[str, object]] = []
    for row in common.rows(lineage, "rows"):
        source_hypothesis_id = common.text(row.get("source_hypothesis_id"))
        registry_row = registry_by_hypothesis.get(source_hypothesis_id, {})
        operator_row = operator_by_hypothesis.get(source_hypothesis_id, {})
        behavior_family = common.text(registry_row.get("behavior_family")) or common.text(row.get("behavior_family"))
        required_controls = _null_rationale(behavior_family)
        operator_controls = operator_row.get("null_controls") if isinstance(operator_row.get("null_controls"), dict) else {}
        operator_status = common.text(operator_controls.get("status"))
        missing_control_ids = common.normalize_list(operator_controls.get("missing_control_ids"))
        materialization_state = common.text(row.get("materialization_state"))
        if operator_status == "complete":
            completeness_state = "COMPLETE"
            blocker = "none"
            next_action = "preserve_null_control_state"
        elif materialization_state in {"IDENTITY_BLOCKED", "IMPLEMENTATION_MISSING", "PRESET_MISSING"}:
            completeness_state = "IMPLEMENTATION_MISSING"
            blocker = common.text(row.get("exact_blocker")) or "campaign_lineage_prerequisite_missing"
            next_action = "establish_campaign_lineage_for_thesis"
        elif materialization_state == "INCOMPLETE":
            completeness_state = "SPECIFIED_NOT_EXECUTED"
            blocker = "null_controls_not_executed"
            next_action = "materialize_null_control_execution_contract"
        elif not required_controls:
            completeness_state = "NOT_APPLICABLE_WITH_REASON"
            blocker = "mechanistically_not_applicable"
            next_action = "preserve_null_control_state"
        else:
            completeness_state = "INSUFFICIENT_EVIDENCE"
            blocker = "null_control_evidence_missing"
            next_action = "materialize_null_control_execution_contract"
        if completeness_state not in VALID_STATES:
            raise ValueError(f"invalid null-control state: {completeness_state}")
        rows_out.append(
            {
                "stable_id": f"qrnc_{common.stable_digest({'hypothesis': source_hypothesis_id})[:16]}",
                "source_hypothesis_id": source_hypothesis_id,
                "behavior_family": behavior_family,
                "required_controls": required_controls,
                "scientific_rationale": f"{behavior_family or 'unknown_behavior'} requires null controls that preserve mechanism-relevant structure without granting authority.",
                "implementation_availability": materialization_state not in {"IDENTITY_BLOCKED", "IMPLEMENTATION_MISSING", "PRESET_MISSING"},
                "data_availability": materialization_state != "IDENTITY_BLOCKED",
                "result_availability": operator_status == "complete",
                "missing_control_ids": missing_control_ids,
                "completeness_state": completeness_state,
                "blocker": blocker,
                "next_action": next_action,
                "provenance_refs": common.dedupe(
                    common.normalize_list(row.get("provenance_refs"))
                    + common.normalize_list(registry_row.get("provenance_refs"))
                    + common.normalize_list(operator_row.get("provenance_refs"))
                ),
            }
        )
    rows_out.sort(key=lambda item: common.text(item.get("source_hypothesis_id")))
    null_identity = f"qrnc_{common.stable_digest({'rows': rows_out})[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "null_control_identity": null_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "complete_count": sum(1 for row in rows_out if row["completeness_state"] == "COMPLETE"),
            "specified_not_executed_count": sum(1 for row in rows_out if row["completeness_state"] == "SPECIFIED_NOT_EXECUTED"),
            "implementation_missing_count": sum(1 for row in rows_out if row["completeness_state"] == "IMPLEMENTATION_MISSING"),
            "exact_next_action": "complete_evidence_and_reason_record_remediation",
        },
    }


def _render_markdown(snapshot: dict[str, object]) -> str:
    lines = [
        "# QRE Null-Control Readiness",
        "",
        f"- null_control_identity: `{common.text(snapshot.get('null_control_identity'))}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if isinstance(row, dict):
            lines.append(
                f"- `{common.text(row.get('source_hypothesis_id'))}`: `{common.text(row.get('completeness_state'))}` -> `{common.text(row.get('next_action'))}`"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018e.", suffix=".tmp", dir=str(path.parent))
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


def write_outputs(snapshot: dict[str, object]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    markdown = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_MARKDOWN, markdown)
    _atomic_write(DOC_PATH, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_null_control_readiness")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
