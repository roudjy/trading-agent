from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import controlled_discovery_grid
from research import production_discovery_catalog as catalog


REPORT_KIND: Final[str] = "qre_discovery_source_identity_diagnostics"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_discovery_source_identity_diagnostics")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_discovery_source_identity_diagnostics/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_source_identity_diagnostics(*, max_candidates: int = 15) -> dict[str, Any]:
    grid_rows = controlled_discovery_grid.build_controlled_discovery_grid()
    basket = catalog.build_bounded_candidate_basket(max_candidates=max_candidates)
    basket_symbols = {str(row.get("symbol") or "") for row in basket}
    rows: list[dict[str, Any]] = []
    for row in catalog.source_identity_diagnostics():
        symbol = str(row.get("instrument_symbol") or "")
        affected_grid_rows = sum(
            1 for grid_row in grid_rows if str(grid_row.get("instrument_symbol") or "") == symbol
        )
        affected_baskets = sum(1 for basket_row in basket if str(basket_row.get("symbol") or "") == symbol)
        rows.append(
            {
                **row,
                "affected_grid_rows": affected_grid_rows,
                "affected_baskets": affected_baskets,
                "included_in_bounded_basket": symbol in basket_symbols,
            }
        )
    rows.sort(
        key=lambda row: (
            0 if str(row.get("provider_symbol_status") or "") != "verified" else 1,
            str(row.get("region") or ""),
            str(row.get("instrument_symbol") or ""),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "instrument_count": len(rows),
            "verified_count": sum(bool(row.get("is_provider_symbol_verified")) for row in rows),
            "candidate_alias_only_count": sum(bool(row.get("is_candidate_alias_only")) for row in rows),
            "basket_symbols_with_identity_blockers": sum(
                bool(row.get("included_in_bounded_basket")) and not bool(row.get("is_provider_symbol_verified"))
                for row in rows
            ),
            "operator_summary": (
                "Source identity diagnostics classify deterministic provider-symbol mappings "
                "for the discovery grid and keep ambiguous aliases blocked until explicit verification exists."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary = report.get("summary") or {}
    count_table = _table(
        ["Field", "Count"],
        [
            ["instrument count", str(summary.get("instrument_count") or 0)],
            ["verified", str(summary.get("verified_count") or 0)],
            ["candidate alias only", str(summary.get("candidate_alias_only_count") or 0)],
            [
                "basket symbols with identity blockers",
                str(summary.get("basket_symbols_with_identity_blockers") or 0),
            ],
        ],
    )
    detail_table = _table(
        [
            "Symbol",
            "Canonical symbol",
            "Candidate aliases",
            "Selected provider symbol",
            "Provider status",
            "Identity confidence",
            "Ambiguity warning",
            "Affected grid rows",
            "Affected baskets",
            "Next action",
        ],
        [
            [
                str(row.get("instrument_symbol") or ""),
                str(row.get("canonical_symbol") or ""),
                ", ".join(str(value) for value in row.get("candidate_aliases") or []) or "-",
                str(row.get("selected_provider_symbol") or "-"),
                str(row.get("provider_symbol_status") or ""),
                str(row.get("identity_confidence") or ""),
                str(row.get("ambiguity_warning") or "-"),
                str(row.get("affected_grid_rows") or 0),
                str(row.get("affected_baskets") or 0),
                str(row.get("next_action") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Discovery Source Identity Diagnostics",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Aggregate counts",
            count_table,
            "",
            "## 3. Source identity diagnostics",
            detail_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_discovery_source_identity_diagnostics: refusing write outside allowlist: {path!r}"
        )


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
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_discovery_source_identity_diagnostics",
        description="Render read-only provider symbol diagnostics for the discovery grid.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_source_identity_diagnostics(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
