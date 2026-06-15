"""Read-only SEC and OpenFIGI manifest hardening report."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research.external_intelligence.source_license_policy import evaluate_license_policy
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


REPORT_KIND: Final[str] = "qre_sec_openfigi_manifest_hardening"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_sec_openfigi_manifest_hardening")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_sec_openfigi_manifest_hardening/"
TARGET_SOURCE_IDS: Final[tuple[str, str]] = (
    "openfigi_symbology_manifest",
    "sec_companyfacts_manifest",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _row(manifest: Mapping[str, Any]) -> dict[str, Any]:
    license_policy = evaluate_license_policy(manifest)
    source_id = str(manifest["source_id"])
    readiness_input_kind = (
        "identity_manifest_input_only"
        if source_id == "openfigi_symbology_manifest"
        else "fundamental_manifest_input_only"
    )
    return {
        "source_id": source_id,
        "provider_id": str(manifest["provider_id"]),
        "source_type": str(manifest["source_type"]),
        "source_status": str(manifest["source_status"]),
        "manifest_status": str(manifest["manifest_status"]),
        "license_terms_status": str(manifest["license_terms_status"]),
        "license_policy_status": str(license_policy["license_policy_status"]),
        "allowed_use": list(manifest["allowed_use"]),
        "forbidden_use": list(manifest["forbidden_use"]),
        "required_quality_gates": list(manifest["required_quality_gates"]),
        "activation_requirements": list(manifest["activation_requirements"]),
        "manifest_block_reasons": list(manifest["manifest_block_reasons"]),
        "license_block_reasons": list(license_policy["block_reasons"]),
        "license_warnings": list(license_policy["warnings"]),
        "quality_gated_readiness_input": True,
        "quality_gated_unlock_allowed": bool(license_policy["allowed_for_quality_gate"]),
        "active_read_only_unlock_allowed": bool(license_policy["allowed_for_active_read_only"]),
        "readiness_input_kind": readiness_input_kind,
        "alpha_authority": False,
        "operator_explanation": (
            f"{source_id} is a deterministic readiness input only. "
            "Its manifest, license policy, and required gates can inform source quality review, "
            "but it does not unlock alpha authority, direct trade use, or provider activation."
        ),
    }


def build_sec_openfigi_manifest_hardening() -> dict[str, Any]:
    snapshot = build_source_manifest_registry()
    manifest_by_id = {str(row["source_id"]): row for row in snapshot["rows"]}
    rows = [_row(manifest_by_id[source_id]) for source_id in TARGET_SOURCE_IDS]
    rows.sort(key=lambda row: row["source_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "source_count": len(rows),
            "quality_gated_readiness_input_count": sum(
                bool(row["quality_gated_readiness_input"]) for row in rows
            ),
            "quality_gated_unlock_allowed_count": sum(
                bool(row["quality_gated_unlock_allowed"]) for row in rows
            ),
            "active_read_only_unlock_allowed_count": sum(
                bool(row["active_read_only_unlock_allowed"]) for row in rows
            ),
            "operator_summary": (
                "SEC Company Facts and OpenFIGI are explicit readiness inputs only. "
                "License review, allowed/forbidden use, and readiness gates remain fail-closed, "
                "and neither manifest can certify alpha or activate a provider."
            ),
        },
        "rows": rows,
        "supporting_reports": {
            "source_manifest_registry": {
                "report_kind": snapshot["report_kind"],
                "quality_gated_eligible_providers": snapshot["summary"][
                    "quality_gated_eligible_providers"
                ],
                "active_read_only_eligible_providers": snapshot["summary"][
                    "active_read_only_eligible_providers"
                ],
            }
        },
        "safety_invariants": {
            "read_only": True,
            "readiness_input_only": True,
            "alpha_authority_forbidden": True,
            "provider_activation_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary_table = _table(
        ["Field", "Value"],
        [
            ["source_count", str(summary.get("source_count") or 0)],
            ["quality_gated_readiness_input_count", str(summary.get("quality_gated_readiness_input_count") or 0)],
            ["quality_gated_unlock_allowed_count", str(summary.get("quality_gated_unlock_allowed_count") or 0)],
            ["active_read_only_unlock_allowed_count", str(summary.get("active_read_only_unlock_allowed_count") or 0)],
        ],
    )
    source_table = _table(
        [
            "source_id",
            "license_policy_status",
            "quality_input",
            "quality_unlock",
            "active_unlock",
        ],
        [
            [
                str(row.get("source_id") or ""),
                str(row.get("license_policy_status") or ""),
                str(row.get("quality_gated_readiness_input") or False),
                str(row.get("quality_gated_unlock_allowed") or False),
                str(row.get("active_read_only_unlock_allowed") or False),
            ]
            for row in rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE SEC and OpenFIGI Manifest Hardening",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            summary_table,
            "",
            "## Source Rows",
            source_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_sec_openfigi_manifest_hardening: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
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
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_sec_openfigi_manifest_hardening",
        description="Materialize the read-only SEC/OpenFIGI manifest hardening report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_sec_openfigi_manifest_hardening()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
