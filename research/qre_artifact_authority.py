from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_artifact_authority"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_artifact_authority")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_artifact_authority/"

AUTHORITY_KINDS: Final[tuple[str, ...]] = (
    "source_artifact",
    "generated_report",
    "context_only",
    "accepted_evidence",
    "approval_manifest",
    "generation_manifest",
    "reason_record",
    "legacy_trace",
    "test_fixture",
    "smoke_temp",
    "stdout_only",
    "rejected_artifact",
)

_CAPABILITY_MATRIX: Final[dict[str, dict[str, bool]]] = {
    "source_artifact": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "generated_report": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "context_only": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "accepted_evidence": {
        "can_clear_campaign_lineage_missing": True,
        "can_clear_no_oos_evidence": True,
        "can_clear_evidence_complete": True,
        "can_prove_current_evidence": True,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "approval_manifest": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": False,
    },
    "generation_manifest": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "reason_record": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": False,
    },
    "legacy_trace": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "test_fixture": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "smoke_temp": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": True,
        "requires_reason_records": True,
    },
    "stdout_only": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": False,
        "requires_reason_records": False,
    },
    "rejected_artifact": {
        "can_clear_campaign_lineage_missing": False,
        "can_clear_no_oos_evidence": False,
        "can_clear_evidence_complete": False,
        "can_prove_current_evidence": False,
        "can_support_context": False,
        "requires_reason_records": False,
    },
}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_path(path: str | Path | None) -> str:
    if path is None:
        return ""
    return str(path).replace("\\", "/")


def _capabilities(kind: str) -> dict[str, bool]:
    return dict(_CAPABILITY_MATRIX.get(kind, _CAPABILITY_MATRIX["rejected_artifact"]))


def classify_artifact_authority(
    payload: Mapping[str, Any] | None,
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    normalized_path = _normalize_path(path)
    data = payload if isinstance(payload, Mapping) else {}
    explicit_kind = ""
    for key in ("authority_kind", "artifact_kind", "record_kind", "report_kind"):
        value = str(data.get(key) or "").strip()
        if value:
            explicit_kind = value
            break

    lowered_path = normalized_path.lower()
    stdout_only = bool(data.get("stdout_only")) or "stdout_tail" in json.dumps(data, sort_keys=True, default=str).lower()
    if not explicit_kind and lowered_path.endswith(".jsonl"):
        explicit_kind = "generated_report"
    if not explicit_kind and ".tmp/" in lowered_path:
        explicit_kind = "smoke_temp"
    if not explicit_kind and "tests/fixtures/" in lowered_path:
        explicit_kind = "test_fixture"
    if not explicit_kind and stdout_only:
        explicit_kind = "stdout_only"

    if not explicit_kind:
        explicit_kind = "rejected_artifact"

    if explicit_kind not in AUTHORITY_KINDS:
        explicit_kind = "rejected_artifact"

    has_source_ref = bool(data.get("source_artifact_ref") or data.get("source_artifact_path"))
    has_generation_ref = bool(data.get("generation_manifest_ref") or data.get("generation_manifest_path") or data.get("controlled_generation_id"))
    has_approval_ref = bool(data.get("approval_ref") or data.get("approval_manifest_ref") or data.get("operator_approval_id"))
    has_reason_refs = bool(data.get("reason_record_refs") or data.get("reason_record_ref") or data.get("reason_record_ids"))
    if explicit_kind == "accepted_evidence":
        if not (has_source_ref and has_generation_ref and has_approval_ref and has_reason_refs):
            return {
                "path": normalized_path,
                "authority_kind": explicit_kind,
                "validation_status": "rejected",
                "rejection_reasons": [
                    reason
                    for reason, present in (
                        ("missing_source_artifact_ref", has_source_ref),
                        ("missing_generation_manifest_ref", has_generation_ref),
                        ("missing_approval_ref", has_approval_ref),
                        ("missing_reason_record_refs", has_reason_refs),
                    )
                    if not present
                ],
                "capabilities": _capabilities("rejected_artifact"),
            }
        return {
            "path": normalized_path,
            "authority_kind": explicit_kind,
            "validation_status": "valid",
            "rejection_reasons": [],
            "capabilities": _capabilities(explicit_kind),
        }

    if explicit_kind in {"source_artifact", "generated_report", "context_only", "approval_manifest", "generation_manifest", "reason_record", "legacy_trace", "test_fixture", "smoke_temp", "stdout_only", "rejected_artifact"}:
        return {
            "path": normalized_path,
            "authority_kind": explicit_kind,
            "validation_status": "valid",
            "rejection_reasons": [],
            "capabilities": _capabilities(explicit_kind),
        }

    return {
        "path": normalized_path,
        "authority_kind": "rejected_artifact",
        "validation_status": "rejected",
        "rejection_reasons": ["unknown_authority_kind"],
        "capabilities": _capabilities("rejected_artifact"),
    }


def build_artifact_authority_snapshot(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    rows = []
    for kind in AUTHORITY_KINDS:
        caps = _capabilities(kind)
        rows.append(
            {
                "authority_kind": kind,
                "can_clear_campaign_lineage_missing": caps["can_clear_campaign_lineage_missing"],
                "can_clear_no_oos_evidence": caps["can_clear_no_oos_evidence"],
                "can_clear_evidence_complete": caps["can_clear_evidence_complete"],
                "can_prove_current_evidence": caps["can_prove_current_evidence"],
                "can_support_context": caps["can_support_context"],
                "requires_reason_records": caps["requires_reason_records"],
                "proof_scope": (
                    "accepted_current_evidence"
                    if kind == "accepted_evidence"
                    else "context_only"
                    if kind in {"source_artifact", "generated_report", "context_only", "approval_manifest", "generation_manifest", "reason_record", "legacy_trace", "test_fixture", "smoke_temp"}
                    else "no_proof"
                ),
                "authority_note": (
                    "Accepted evidence can clear evidence blockers only when complete proof refs exist."
                    if kind == "accepted_evidence"
                    else "Contextual artifact only; cannot prove current evidence."
                    if kind in {"source_artifact", "generated_report", "context_only", "legacy_trace", "test_fixture", "smoke_temp"}
                    else "Authority/support artifact, not evidence proof."
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "authority_kind_count": len(rows),
            "accepted_evidence_kind_count": sum(1 for row in rows if row["authority_kind"] == "accepted_evidence"),
            "proof_enabled_kind_count": sum(1 for row in rows if row["can_prove_current_evidence"]),
            "context_only_kind_count": sum(1 for row in rows if row["can_support_context"] and not row["can_prove_current_evidence"]),
            "final_recommendation": "artifact_authority_registry_ready",
            "operator_summary": (
                "QRE artifact authority distinguishes context, provenance, approval, and accepted evidence "
                "without letting generated reports or stdout-only traces become proof."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "accepted_evidence_required_for_blocker_clearance": True,
            "stdout_only_not_proof": True,
            "context_only_not_proof": True,
            "test_fixture_not_proof": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Artifact Authority",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["authority_kind_count", str(summary.get("authority_kind_count") or 0)],
                    ["accepted_evidence_kind_count", str(summary.get("accepted_evidence_kind_count") or 0)],
                    ["proof_enabled_kind_count", str(summary.get("proof_enabled_kind_count") or 0)],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            _table(
                ["Authority kind", "Can prove current evidence", "Can clear blockers"],
                [
                    [
                        str(row.get("authority_kind") or ""),
                        "yes" if bool(row.get("can_prove_current_evidence")) else "no",
                        "yes" if bool(row.get("can_clear_campaign_lineage_missing") or row.get("can_clear_no_oos_evidence") or row.get("can_clear_evidence_complete")) else "no",
                    ]
                    for row in rows
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_artifact_authority: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_artifact_authority",
        description="Build the QRE artifact authority report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_artifact_authority_snapshot()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
