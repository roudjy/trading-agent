from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_reason_record_contract"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_reason_record_contract")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_reason_record_contract/"

REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "record_id",
    "record_kind",
    "subject_id",
    "reason_codes",
    "reason_text",
    "evidence_refs",
    "inputs_digest",
)
REQUIRED_ACCEPTED_ARTIFACT_REFS: Final[tuple[str, ...]] = (
    "source_artifact_ref",
    "generation_manifest_ref",
    "approval_manifest_ref",
)
REQUIRED_CONSUMER_REFS: Final[tuple[str, ...]] = (
    "basket_request_ref",
    "verifier_ref",
    "closure_ref",
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
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_reason_record_contract(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, Mapping) else {}
    missing_fields = [field for field in REQUIRED_FIELDS if not _text(data.get(field))]
    reason_codes = _bounded_list(data.get("reason_codes"))
    evidence_refs = _bounded_list(data.get("evidence_refs"))
    accepted_artifact_refs = {
        field: _text(data.get(field))
        for field in REQUIRED_ACCEPTED_ARTIFACT_REFS
    }
    consumer_refs = {
        field: _text(data.get(field))
        for field in REQUIRED_CONSUMER_REFS
    }
    preservation = _text(data.get("negative_evidence_preservation")) or "preserved"
    validation_reasons: list[str] = []
    if missing_fields:
        validation_reasons.append("missing_required_fields")
    if not reason_codes:
        validation_reasons.append("missing_reason_codes")
    if not evidence_refs:
        validation_reasons.append("missing_evidence_refs")
    if data.get("accepted_evidence"):
        for field, value in accepted_artifact_refs.items():
            if not value:
                validation_reasons.append(f"missing_{field}")
    if not all(consumer_refs.values()):
        validation_reasons.append("missing_consumer_refs")
    if preservation not in {"preserved", "explicitly_preserved"}:
        validation_reasons.append("negative_evidence_not_preserved")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "validation_status": "valid" if not validation_reasons else "rejected",
        "rejection_reasons": validation_reasons,
        "contract": {
            "required_fields": list(REQUIRED_FIELDS),
            "required_accepted_artifact_refs": list(REQUIRED_ACCEPTED_ARTIFACT_REFS),
            "required_consumer_refs": list(REQUIRED_CONSUMER_REFS),
            "reason_record_required_for_blockers": True,
            "accepted_evidence_required_to_clear_blockers": True,
            "context_only_not_proof": True,
            "stdout_only_not_proof": True,
            "negative_evidence_preservation_required": True,
        },
    }


def build_reason_record_contract_snapshot(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    validation_example = validate_reason_record_contract(
        {
            "record_id": "rr_contract_example",
            "record_kind": "reason_record",
            "subject_id": "basket-request-001",
            "reason_codes": ["campaign_lineage_missing"],
            "reason_text": "Campaign lineage remains missing until accepted evidence is present.",
            "evidence_refs": ["logs/qre_artifact_authority/latest.json"],
            "inputs_digest": "digest-001",
            "accepted_evidence": False,
            "basket_request_ref": "logs/qre_bounded_basket_request/latest.json",
            "verifier_ref": "logs/qre_bounded_generation_artifact_acceptance_verifier/latest.json",
            "closure_ref": "logs/qre_evidence_complete_basket_closure/latest.json",
            "negative_evidence_preservation": "preserved",
            "source_artifact_ref": "logs/qre_artifact_authority/latest.json",
            "generation_manifest_ref": "logs/qre_bounded_current_basket_generation_runner/latest.json",
            "approval_manifest_ref": "logs/qre_bounded_generation_approval_manifest/latest.json",
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "required_field_count": len(REQUIRED_FIELDS),
            "required_accepted_artifact_ref_count": len(REQUIRED_ACCEPTED_ARTIFACT_REFS),
            "required_consumer_ref_count": len(REQUIRED_CONSUMER_REFS),
            "final_recommendation": "reason_record_contract_ready",
            "operator_summary": (
                "Reason records must preserve negative evidence and link accepted artifacts "
                "to source, generation, approval, verifier, and closure references."
            ),
        },
        "contract": {
            "required_fields": list(REQUIRED_FIELDS),
            "required_accepted_artifact_refs": list(REQUIRED_ACCEPTED_ARTIFACT_REFS),
            "required_consumer_refs": list(REQUIRED_CONSUMER_REFS),
            "reason_record_required_for_blockers": True,
            "accepted_evidence_required_to_clear_blockers": True,
            "negative_evidence_preservation_required": True,
            "accepted_record_validation": validation_example,
        },
        "safety_invariants": {
            "read_only": True,
            "acceptance_requires_structured_refs": True,
            "context_only_not_proof": True,
            "stdout_only_not_proof": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    contract = report.get("contract") if isinstance(report.get("contract"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Reason Record Contract",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["required_field_count", str(summary.get("required_field_count") or 0)],
                    ["required_accepted_artifact_ref_count", str(summary.get("required_accepted_artifact_ref_count") or 0)],
                    ["required_consumer_ref_count", str(summary.get("required_consumer_ref_count") or 0)],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            _table(
                ["Contract item", "Status"],
                [
                    ["reason_record_required_for_blockers", "true" if contract.get("reason_record_required_for_blockers") else "false"],
                    ["accepted_evidence_required_to_clear_blockers", "true" if contract.get("accepted_evidence_required_to_clear_blockers") else "false"],
                    ["negative_evidence_preservation_required", "true" if contract.get("negative_evidence_preservation_required") else "false"],
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_reason_record_contract: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_reason_record_contract",
        description="Build the QRE reason record contract report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_reason_record_contract_snapshot()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
