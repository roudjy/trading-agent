"""Read-only QRE factor coverage matrix materialization."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research.data_readiness.factor_field_coverage import build_factor_field_coverage


REPORT_KIND: Final[str] = "qre_factor_coverage_matrix"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_factor_coverage_matrix")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_factor_coverage_matrix/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_qre_factor_coverage_matrix() -> dict[str, Any]:
    coverage = build_factor_field_coverage()
    summary = coverage["summary"]
    rows = coverage["rows"]
    provider_rows = coverage["provider_rows"]
    blocked_provider_count = sum(
        str(row["approval_status"]) != "APPROVED_READ_ONLY" for row in provider_rows
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "factor_field_coverage_schema_version": coverage["schema_version"],
        "summary": {
            "factor_count": summary["factor_count"],
            "provider_count": summary["provider_count"],
            "approved_provider_count": summary["approved_provider_count"],
            "quality_gated_only_provider_count": summary["quality_gated_only_provider_count"],
            "blocked_provider_count": blocked_provider_count,
            "covered_factor_count": summary["covered_count"],
            "partial_factor_count": summary["partial_count"],
            "unknown_factor_count": summary["unknown_count"],
            "missing_factor_count": summary["missing_count"],
            "operator_summary": (
                "Factor coverage remains research-only. Providers can contribute deterministic field coverage "
                "evidence, but provider presence, manifest claims, and freshness declarations do not create alpha "
                "authority or direct trade permission."
            ),
        },
        "provider_rows": provider_rows,
        "factor_rows": rows,
        "supporting_reports": {
            "factor_field_coverage": {
                "report_kind": coverage["report_kind"],
                "provider_approval_status_vocabulary": coverage["provider_approval_status_vocabulary"],
                "freshness_status_vocabulary": coverage["freshness_status_vocabulary"],
            }
        },
        "safety_invariants": {
            **coverage["safety_invariants"],
            "provider_matrix_is_report_only": True,
            "provider_is_not_alpha_authority": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    provider_rows = report.get("provider_rows") if isinstance(report.get("provider_rows"), list) else []
    factor_rows = report.get("factor_rows") if isinstance(report.get("factor_rows"), list) else []
    summary_table = _table(
        ["Field", "Value"],
        [
            ["factor_count", str(summary.get("factor_count") or 0)],
            ["provider_count", str(summary.get("provider_count") or 0)],
            ["approved_provider_count", str(summary.get("approved_provider_count") or 0)],
            ["quality_gated_only_provider_count", str(summary.get("quality_gated_only_provider_count") or 0)],
            ["blocked_provider_count", str(summary.get("blocked_provider_count") or 0)],
        ],
    )
    provider_table = _table(
        ["provider_id", "approval_status", "freshness_status", "manifest_status"],
        [
            [
                str(row.get("provider_id") or ""),
                str(row.get("approval_status") or ""),
                str(row.get("freshness_status") or ""),
                str(row.get("manifest_status") or ""),
            ]
            for row in provider_rows
            if isinstance(row, Mapping)
        ],
    )
    factor_table = _table(
        ["factor_id", "field_coverage_status", "provider_coverage_count"],
        [
            [
                str(row.get("factor_id") or ""),
                str(row.get("field_coverage_status") or ""),
                str(row.get("provider_coverage_count") or 0),
            ]
            for row in factor_rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE Factor Coverage Matrix",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            summary_table,
            "",
            "## Providers",
            provider_table,
            "",
            "## Factors",
            factor_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_factor_coverage_matrix: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_factor_coverage_matrix",
        description="Materialize the read-only QRE factor coverage matrix report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_qre_factor_coverage_matrix()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
