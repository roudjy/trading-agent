from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_current_basket_generation_discovery as generic_discovery


REPORT_KIND: Final[str] = "qre_bounded_aapl_nvda_current_basket_generation_discovery"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path(
    "logs/qre_bounded_aapl_nvda_current_basket_generation_discovery"
)
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_aapl_nvda_current_basket_generation_discovery/"

DEPRECATED_WRAPPER_FOR: Final[str] = generic_discovery.REPORT_KIND
APPROVAL_SCOPE_ID: Final[str] = (
    "aapl_nvda_current_basket_trend_pullback_continuation_daily_v1_daily_v1"
)

_WRAPPER_FIXTURE_REQUEST: Final[dict[str, Any]] = {
    "request_id": "deprecated-aapl-nvda-fixture",
    "symbols": ["AAPL", "NVDA"],
    "preset_id": "trend_pullback_continuation_daily_v1",
    "timeframe": "daily_v1",
    "approval_ref": "deprecated-wrapper-fixture",
    "required_artifact_types": [
        "generation_manifest",
        "structured_lineage_artifact",
        "structured_oos_artifact",
    ],
    "allowed_output_paths": [
        "logs/qre_bounded_aapl_nvda_current_basket_generation_discovery/",
        "logs/qre_bounded_current_basket_generation_discovery/",
    ],
    "forbidden_capabilities": [],
    "created_at_utc": "2026-06-17T00:00:00Z",
    "source": "deprecated_compatibility_wrapper",
}

_WRAPPER_EXACT_SCOPE_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.controlled_discovery_grid --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1",
    "python -m research.controlled_validation --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1",
)


def build_bounded_aapl_nvda_current_basket_generation_discovery(
    *, repo_root: Path = Path(".")
) -> dict[str, Any]:
    generic_report = generic_discovery.build_bounded_current_basket_generation_discovery(
        _WRAPPER_FIXTURE_REQUEST,
        repo_root=repo_root,
    )
    generic_rows = (
        generic_report.get("command_surface", {}).get("rows")
        if isinstance(generic_report.get("command_surface"), dict)
        else []
    )
    transformed_rows: list[dict[str, Any]] = []
    for row in generic_rows if isinstance(generic_rows, list) else []:
        if not isinstance(row, dict):
            continue
        command = str(row.get("command") or "")
        exact_scope_match = command in _WRAPPER_EXACT_SCOPE_COMMANDS
        disposition = str(row.get("classification") or "")
        transformed_rows.append(
            {
                "command": command,
                "module_name": row.get("module_name"),
                "module_exists": row.get("module_exists"),
                "module_has_cli_entrypoint": row.get("module_has_cli_entrypoint"),
                "exact_scope_match": exact_scope_match,
                "classification": row.get("classification"),
                "disposition": disposition,
                "reason": row.get("classification_reason"),
                "operator_approval_required": row.get("operator_approval_required"),
                "auto_run_allowed": row.get("auto_run_allowed"),
                "safe_command_available": row.get("safe_command_available"),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "deprecated_wrapper_for": DEPRECATED_WRAPPER_FOR,
        "approval_scope_id": APPROVAL_SCOPE_ID,
        "request": generic_report.get("request", {}),
        "summary": {
            "approval_scope_id": APPROVAL_SCOPE_ID,
            "safe_bounded_generation_command_found": bool(
                generic_report.get("summary", {}).get("safe_bounded_generation_command_found")
            ),
            "exact_scope_candidate_count": sum(1 for row in transformed_rows if row["exact_scope_match"]),
            "final_recommendation": str(
                generic_report.get("summary", {}).get("final_recommendation")
                or "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
            ),
            "operator_summary": (
                "Deprecated AAPL/NVDA compatibility wrapper delegates to the generic bounded "
                "current-basket discovery report."
            ),
        },
        "command_surface": {"rows": transformed_rows},
        "safety_invariants": generic_report.get("safety_invariants", {}),
        "generic_discovery_report": generic_report,
    }


def render_operator_summary(report: dict[str, Any]) -> str:
    return generic_discovery.render_operator_summary(
        report.get("generic_discovery_report", {})
        if isinstance(report, dict)
        else {}
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_aapl_nvda_current_basket_generation_discovery: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: dict[str, Any],
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
    generic_paths = generic_discovery.write_outputs(
        report.get("generic_discovery_report", {}),
        output_dir=Path("logs/qre_bounded_current_basket_generation_discovery"),
        repo_root=repo_root,
    )
    latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
        "generic_latest": generic_paths["latest"],
        "generic_operator_summary": generic_paths["operator_summary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_bounded_aapl_nvda_current_basket_generation_discovery",
        description="Build the deprecated AAPL/NVDA compatibility wrapper report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_bounded_aapl_nvda_current_basket_generation_discovery()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
