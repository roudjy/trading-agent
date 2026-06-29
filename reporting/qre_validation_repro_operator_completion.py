from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common
from reporting import qre_evidence_reason_record_completion as completion

REPORT_KIND: Final[str] = "qre_validation_repro_operator_completion"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018g-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_validation_repro_operator_completion")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_validation_repro_operator_completion.md")
DEFAULT_COMPLETION_PATH: Final[Path] = Path("logs/qre_evidence_reason_record_completion/latest.json")
DEFAULT_OPERATOR_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
DEFAULT_DECAY_PATH: Final[Path] = Path("logs/qre_evidence_decay/latest.json")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage/latest.json")
VALID_STATES: Final[tuple[str, ...]] = (
    "COMPLETE",
    "CONTEXT_ONLY",
    "BLOCKED",
    "MISSING",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_validation_repro_operator_completion/",
    "docs/governance/qre_validation_repro_operator_completion.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    completion_path: Path | None = None,
    operator_path: Path | None = None,
    decay_path: Path | None = None,
    lineage_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    completion_payload = common.read_json(root / (completion_path or DEFAULT_COMPLETION_PATH))
    if completion_payload is None:
        completion_payload = completion.collect_snapshot(repo_root=root)
    operator = common.read_json(root / (operator_path or DEFAULT_OPERATOR_PATH)) or {}
    decay = common.read_json(root / (decay_path or DEFAULT_DECAY_PATH)) or {}
    lineage = common.read_json(root / (lineage_path or DEFAULT_LINEAGE_PATH)) or {}

    operator_by_hypothesis = common.index_by(common.rows(operator, "rows"), "source_hypothesis_id")
    decay_by_hypothesis = common.index_by(common.rows(decay, "rows"), "thesis_id")
    lineage_by_hypothesis = common.index_by(common.rows(lineage, "rows"), "source_hypothesis_id")

    rows_out: list[dict[str, Any]] = []
    for row in common.rows(completion_payload, "rows"):
        source_hypothesis_id = common.text(row.get("source_hypothesis_id"))
        thesis_id = common.text(row.get("thesis_id"))
        operator_row = operator_by_hypothesis.get(source_hypothesis_id, {})
        decay_row = decay_by_hypothesis.get(thesis_id, {})
        lineage_row = lineage_by_hypothesis.get(source_hypothesis_id, {})
        reproducibility_raw = common.text((decay_row.get("dimension_statuses") or {}).get("reproducibility"))
        freshness_raw = common.text((decay_row.get("dimension_statuses") or {}).get("source_freshness"))
        missing_lineage = bool(common.normalize_list(lineage_row.get("missing_lineage_fields")))
        validation_state = (
            "COMPLETE"
            if common.text((operator_row.get("funnel_result") or {}).get("campaign_outcome")) and not bool(decay_row.get("decay_blocks_readiness"))
            else "CONTEXT_ONLY"
            if common.text((operator_row.get("funnel_result") or {}).get("status"))
            else "MISSING"
        )
        reproducibility_state = (
            "BLOCKED"
            if "reproducibility_unverifiable" in common.normalize_list(decay_row.get("blocking_reasons"))
            or "reproducibility_unverifiable_without_campaign" in reproducibility_raw
            else "COMPLETE"
            if reproducibility_raw in {"validation_result_present", "reproducible"}
            else "CONTEXT_ONLY"
            if reproducibility_raw
            else "MISSING"
        )
        freshness_state = (
            "BLOCKED"
            if freshness_raw.startswith("stale") or "stale_or_superseded_artifacts_visible" in common.normalize_list(decay_row.get("blocking_reasons"))
            else "COMPLETE"
            if freshness_raw in {"fresh", "bounded"}
            else "CONTEXT_ONLY"
            if freshness_raw
            else "MISSING"
        )
        operator_state = (
            "BLOCKED"
            if missing_lineage
            else "CONTEXT_ONLY"
            if operator_row and common.text(operator_row.get("next_action")) and common.normalize_list(operator_row.get("primary_reasons"))
            else "MISSING"
        )
        for field, value in {
            "validation_state": validation_state,
            "reproducibility_state": reproducibility_state,
            "freshness_state": freshness_state,
            "operator_report_completeness_state": operator_state,
        }.items():
            if value not in VALID_STATES:
                raise ValueError(f"invalid {field}: {value}")
        rows_out.append(
            {
                "stable_id": f"qrvo_{common.stable_digest({'hypothesis': source_hypothesis_id})[:16]}",
                "thesis_id": thesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "validation_state": validation_state,
                "reproducibility_state": reproducibility_state,
                "freshness_state": freshness_state,
                "operator_report_completeness_state": operator_state,
                "lineage_complete": bool(lineage_row.get("lineage_complete")),
                "exact_blocker": (
                    common.text(next(iter(common.normalize_list(lineage_row.get("missing_lineage_fields"))), ""))
                    or common.text(next(iter(common.normalize_list(decay_row.get("blocking_reasons"))), ""))
                    or "none"
                ),
                "next_action": common.text(row.get("next_action")) or common.text(operator_row.get("next_action")) or "collect_missing_evidence",
                "provenance_refs": common.dedupe(
                    common.normalize_list(row.get("provenance_refs"))
                    + common.normalize_list(operator_row.get("provenance_refs"))
                    + common.normalize_list(lineage_row.get("provenance_refs"))
                    + [common.rel(root / DEFAULT_DECAY_PATH, root)]
                ),
            }
        )

    rows_out.sort(key=lambda item: item["source_hypothesis_id"])
    validation_identity = f"qrvo_{common.stable_digest({'rows': rows_out})[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "validation_completion_identity": validation_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "validation_complete_count": sum(1 for row in rows_out if row["validation_state"] == "COMPLETE"),
            "reproducibility_complete_count": sum(1 for row in rows_out if row["reproducibility_state"] == "COMPLETE"),
            "operator_complete_count": sum(1 for row in rows_out if row["operator_report_completeness_state"] == "COMPLETE"),
            "exact_next_action": "archive_rejected_thesis_and_plan_distinct_replacement",
        },
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# QRE Validation Reproducibility And Operator Completion",
        "",
        f"- validation_completion_identity: `{common.text(snapshot.get('validation_completion_identity'))}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if isinstance(row, dict):
            lines.append(
                f"- `{common.text(row.get('source_hypothesis_id'))}`: validation `{common.text(row.get('validation_state'))}`, reproducibility `{common.text(row.get('reproducibility_state'))}`, operator `{common.text(row.get('operator_report_completeness_state'))}`"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018g.", suffix=".tmp", dir=str(path.parent))
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
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_validation_repro_operator_completion")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
