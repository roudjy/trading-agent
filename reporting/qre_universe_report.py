"""Read-only operator summary for the QRE equity research front door."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Final

from research.equity_factor_manifest import DEFAULT_OUTPUT_DIR as FACTOR_ARTIFACT_DIR
from research.equity_factors.factor_catalog import build_equity_factor_catalog
from research.equity_factors.recipe_catalog import build_equity_factor_recipe_catalog
from research.equity_universe_catalog import build_equity_universe_catalog, build_equity_universe_summary
from research.equity_universe_identity import build_instrument_identity_report
from research.equity_universe_quality import build_equity_universe_quality


REPO_ROOT: Final[Path] = Path(".")
OUTPUT_DIR: Final[Path] = Path("artifacts/universe")
JSON_NAME: Final[str] = "equity_universe_operator_report_latest.json"
MD_NAME: Final[str] = "equity_universe_operator_report_latest.md"
WRITE_PREFIX: Final[str] = "artifacts/universe/"
DISCLAIMER: Final[str] = (
    "Research-only report. No buy/sell recommendations, no trade signals, no strategy registration, "
    "no paper/shadow/live activation, and no broker/risk/execution authority."
)
EXPECTED_UNIVERSE_IDS: Final[tuple[str, ...]] = (
    "nl_equities",
    "europe_large_mid",
    "europe_small_mid",
    "us_large_mid",
    "asia_developed_liquid",
    "global_developed_liquid",
    "global_ex_crypto_research_universe",
    "us_quality_liquid",
    "nordics_equities",
    "switzerland_equities",
)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_universe_report: refusing write outside allowlist: {path!r}")


def _write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _available_artifacts() -> tuple[list[str], list[str]]:
    expected = [
        "artifacts/universe/equity_universe_catalog_latest.v1.json",
        "artifacts/universe/equity_universe_summary_latest.v1.json",
        "artifacts/universe/equity_universe_quality_latest.v1.json",
        "artifacts/identity/instrument_identity_latest.v1.json",
        "artifacts/equity_factors/equity_factor_catalog_latest.v1.json",
        "artifacts/equity_factors/equity_factor_calculation_contracts_latest.v1.json",
        "artifacts/equity_factors/equity_factor_recipes_latest.v1.json",
        "artifacts/data_readiness/fundamental_readiness_latest.v1.json",
        "artifacts/hypothesis_discovery/equity_factor_hypothesis_seeds_latest.v1.json",
    ]
    available = sorted(path for path in expected if (REPO_ROOT / path).exists())
    missing = sorted(path for path in expected if path not in available)
    return available, missing


def collect_snapshot() -> dict[str, object]:
    catalog = build_equity_universe_catalog()
    summary = build_equity_universe_summary()
    quality = build_equity_universe_quality()
    identity = build_instrument_identity_report()
    factor_catalog = build_equity_factor_catalog()
    recipe_catalog = build_equity_factor_recipe_catalog()
    available_artifacts, missing_artifacts = _available_artifacts()

    quality_summary = quality["summary"]
    summary_counts = summary["summary"]
    universe_counts = summary["universe_counts"]
    country_counts = summary["country_counts"]
    exchange_counts = summary["exchange_counts"]
    currency_counts = summary["currency_counts"]
    universe_rows = {row["universe_id"]: row for row in catalog["universes"]}
    nl_instruments = sorted(
        row["symbol"] for row in catalog["instruments"] if "nl_equities" in row["universe_ids"]
    )
    asia_country_counts = {
        country: count
        for country, count in country_counts.items()
        if country in {"Japan", "Hong Kong", "Singapore", "Australia"}
    }
    sector_counts: dict[str, int] = {}
    for row in catalog["instruments"]:
        if row["country"] == "United States":
            sector = str(row["sector"])
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
    recipes_by_universe: dict[str, int] = {}
    for row in recipe_catalog["rows"]:
        for universe_id in row["target_universe_ids"]:
            recipes_by_universe[universe_id] = recipes_by_universe.get(universe_id, 0) + 1

    inventory = []
    for universe_id in sorted(universe_counts):
        inventory.append(
            {
                "universe_id": universe_id,
                "region": universe_rows[universe_id]["region"],
                "asset_class": "equity",
                "instrument_count": universe_counts[universe_id],
                "readiness": "WARN" if quality_summary["warn_instruments"] else "OK",
                "notes": "research_only",
            }
        )

    largest = [
        {
            "universe_id": row["universe_id"],
            "count": row["instrument_count"],
            "countries_covered": row["countries"],
            "primary_currencies": row["primary_currencies"],
        }
        for row in summary["largest_universes"]
    ]

    return {
        "report_kind": "qre_equity_universe_operator_report",
        "schema_version": "1.0",
        "disclaimer": DISCLAIMER,
        "summary": {
            "total_instruments": summary_counts["total_instruments"],
            "total_countries": summary_counts["total_countries"],
            "total_exchanges": summary_counts["total_exchanges"],
            "total_currencies": summary_counts["total_currencies"],
            "ok_instruments": quality_summary["ok_instruments"],
            "warn_instruments": quality_summary["warn_instruments"],
            "fail_instruments": quality_summary["fail_instruments"],
            "unknown_instruments": quality_summary["unknown_instruments"],
            "ambiguous_mappings": quality_summary["ambiguous_mappings"],
            "duplicate_canonical_ids": quality_summary["duplicate_canonical_ids"],
            "factor_definitions": factor_catalog["summary"]["factor_definition_count"],
            "factor_families": factor_catalog["summary"]["factor_family_count"],
            "recipe_count": recipe_catalog["summary"]["recipe_count"],
            "feasible_recipes": recipe_catalog["summary"]["feasible_recipe_count"],
            "blocked_recipes": recipe_catalog["summary"]["blocked_recipe_count"],
        },
        "universe_inventory": inventory,
        "required_universe_ids_present": {
            universe_id: universe_id in universe_counts for universe_id in EXPECTED_UNIVERSE_IDS
        },
        "largest_universes": largest,
        "nl_instruments": nl_instruments,
        "europe_by_country": {
            country: country_counts[country]
            for country in sorted(country_counts)
            if country in {
                "Netherlands",
                "Belgium",
                "Germany",
                "France",
                "Switzerland",
                "United Kingdom",
                "Italy",
                "Spain",
                "Denmark",
                "Sweden",
                "Norway",
                "Finland",
            }
        },
        "us_by_sector": dict(sorted(sector_counts.items())),
        "asia_by_country": dict(sorted(asia_country_counts.items())),
        "recipes_by_target_universe": dict(sorted(recipes_by_universe.items())),
        "available_artifacts": available_artifacts,
        "missing_artifacts": missing_artifacts,
        "exchange_counts": exchange_counts,
        "currency_counts": currency_counts,
        "identity_summary": identity["summary"],
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_markdown(snapshot: dict[str, object]) -> str:
    summary = snapshot["summary"]
    inventory = snapshot["universe_inventory"]
    lines = [
        "# QRE Equity Universe Summary",
        "",
        DISCLAIMER,
        "",
        "## Totals",
        f"- instruments: {summary['total_instruments']}",
        f"- countries: {summary['total_countries']}",
        f"- exchanges: {summary['total_exchanges']}",
        f"- currencies: {summary['total_currencies']}",
        f"- OK instruments: {summary['ok_instruments']}",
        f"- WARN instruments: {summary['warn_instruments']}",
        f"- FAIL instruments: {summary['fail_instruments']}",
        f"- ambiguous mappings: {summary['ambiguous_mappings']}",
        "",
        "## Universes",
    ]
    for row in inventory:
        lines.append(
            f"- {row['universe_id']}: {row['instrument_count']} ({row['readiness']}, {row['region']})"
        )
    lines.extend(
        [
            "",
            "## Factor Catalog",
            f"- factor definitions: {summary['factor_definitions']}",
            f"- factor families: {summary['factor_families']}",
            f"- recipes: {summary['recipe_count']}",
            f"- feasible recipes: {summary['feasible_recipes']}",
            f"- blocked recipes: {summary['blocked_recipes']}",
            "",
            "## NL Instruments",
            f"- {', '.join(snapshot['nl_instruments'])}",
            "",
            "## Missing Artifacts",
        ]
    )
    for path in snapshot["missing_artifacts"]:
        lines.append(f"- {path}")
    return "\n".join(lines) + "\n"


def write_outputs(*, repo_root: Path = REPO_ROOT, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / JSON_NAME
    md_path = base / MD_NAME
    for path in (json_path, md_path):
        _validate_write_target(path)
    snapshot = collect_snapshot()
    _write_text(json_path, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    _write_text(md_path, render_markdown(snapshot))
    return {
        "json": json_path.relative_to(repo_root).as_posix(),
        "markdown": md_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_universe_report",
        description="Write read-only QRE equity universe operator reports.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    snapshot = collect_snapshot()
    payload = {"report": snapshot, "markdown": render_markdown(snapshot)}
    if args.write:
        payload["_artifact_paths"] = write_outputs()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
