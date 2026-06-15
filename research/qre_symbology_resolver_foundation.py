"""Read-only QRE symbology resolver foundation materialization."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data import symbology_resolver
from research import production_discovery_catalog as catalog
from research.external_intelligence import source_manifest_registry


REPORT_KIND: Final[str] = "qre_symbology_resolver_foundation"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_symbology_resolver_foundation")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_symbology_resolver_foundation/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers) + []) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_symbology_resolver_foundation() -> dict[str, Any]:
    assets = [asset.to_payload() for asset in catalog.list_assets()]
    rows = [symbology_resolver.resolve_symbology_row(asset) for asset in assets]
    rows.sort(key=lambda row: str(row["instrument_symbol"]))
    status_counts = Counter(str(row["resolution_status"]) for row in rows)
    blocking_counts = Counter(reason for row in rows for reason in row["blocking_reasons"])
    openfigi_row = next(
        row
        for row in source_manifest_registry.build_source_manifest_registry()["rows"]
        if row["source_id"] == "openfigi_symbology_manifest"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "instrument_count": len(rows),
            "verified_count": sum(str(row["resolution_status"]) == "VERIFIED" for row in rows),
            "ambiguity_blocked_count": sum(bool(row["ambiguity_blocked"]) for row in rows),
            "resolution_status_counts": dict(sorted(status_counts.items())),
            "blocking_reason_counts": dict(sorted(blocking_counts.items())),
            "operator_summary": (
                "Symbology resolution remains read-only infrastructure. Canonical IDs and verified provider "
                "symbols are surfaced, while alias ambiguity blocks escalation until explicit resolution exists."
            ),
        },
        "rows": rows,
        "supporting_reports": {
            "production_discovery_catalog": {
                "schema_version": catalog.SCHEMA_VERSION,
                "module_version": catalog.MODULE_VERSION,
            },
            "openfigi_manifest": {
                "source_id": openfigi_row["source_id"],
                "source_status": openfigi_row["source_status"],
                "allowed_use": openfigi_row["allowed_use"],
                "required_quality_gates": openfigi_row["required_quality_gates"],
            },
        },
        "safety_invariants": {
            "read_only": True,
            "identity_is_infrastructure_only": True,
            "not_alpha_authority": True,
            "candidate_promotion_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    status_table = _table(
        ["Field", "Value"],
        [
            ["instrument_count", str(summary.get("instrument_count") or 0)],
            ["verified_count", str(summary.get("verified_count") or 0)],
            ["ambiguity_blocked_count", str(summary.get("ambiguity_blocked_count") or 0)],
        ],
    )
    row_table = _table(
        ["symbol", "canonical_id", "provider_symbol", "status", "blocked_by"],
        [
            [
                str(row.get("instrument_symbol") or ""),
                str(row.get("canonical_instrument_id") or ""),
                str(row.get("provider_symbol") or "-"),
                str(row.get("resolution_status") or ""),
                ",".join(str(value) for value in row.get("blocking_reasons") or []) or "none",
            ]
            for row in rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE Symbology Resolver Foundation",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Status",
            status_table,
            "",
            "## Symbol Rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_symbology_resolver_foundation: refusing write outside allowlist: {path!r}"
        )


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
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_symbology_resolver_foundation",
        description="Materialize the read-only QRE symbology resolver foundation report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_symbology_resolver_foundation()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
