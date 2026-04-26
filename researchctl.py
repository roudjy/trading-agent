#!/usr/bin/env python3
"""researchctl — single-command research operations entrypoint (v3.10).

Subcommands:

- ``run <preset_name> [--dry-run]`` — invoke run_research with the preset.
- ``report latest`` — print the latest ``research/report_latest.md``.
- ``report history`` — list historical reports under ``research/history/``.
- ``history [--limit N]`` — recent run metadata from ``run_meta_latest.v1.json`` +
  ``research/history/`` snapshots.
- ``doctor`` — local health checks (artifact freshness, CSV header drift,
  preset validity, disk space sanity).

**Deliberate omission**: there is NO ``deploy`` subcommand. Deploy is
strictly an ops concern and lives in ``scripts/deploy.sh`` (ADR-011 §4).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

from research.presets import PRESETS, get_preset, list_presets, validate_preset
from research.report_agent import (
    REPORT_JSON_PATH,
    REPORT_MARKDOWN_PATH,
)
from research.results import ROW_SCHEMA
from research.run_meta import RUN_META_PATH, read_run_meta_sidecar


REPO_ROOT = Path(__file__).resolve().parent
RESEARCH_DIR = REPO_ROOT / "research"
STRATEGY_MATRIX_PATH = RESEARCH_DIR / "strategy_matrix.csv"
RESEARCH_HISTORY_DIR = RESEARCH_DIR / "history"


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    try:
        preset = get_preset(args.preset_name)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not preset.enabled:
        print(
            f"error: preset {preset.name!r} is disabled "
            f"(status={preset.status!r}); backlog_reason={preset.backlog_reason!r}",
            file=sys.stderr,
        )
        return 3
    issues = validate_preset(preset)
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 4

    if args.dry_run:
        card = {
            "name": preset.name,
            "status": preset.status,
            "bundle": list(preset.bundle),
            "universe": list(preset.universe),
            "timeframe": preset.timeframe,
            "screening_mode": preset.screening_mode,
            # v3.15.6: surface funnel-stage classification next to the
            # legacy gate-strictness ``screening_mode`` so operators see
            # both at a glance. Additive only; no API/frontend impact.
            "screening_phase": preset.screening_phase,
            "cost_mode": preset.cost_mode,
        }
        print(json.dumps({"dry_run": True, "preset": card}, indent=2))
        # Write a minimal placeholder report so downstream smoke tests pass.
        REPORT_MARKDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_MARKDOWN_PATH.write_text(
            f"# Research report — {preset.name}\n\n"
            f"- dry_run: true\n"
            f"- bundle: {list(preset.bundle)}\n"
            f"- verdict: **dry_run**\n",
            encoding="utf-8",
        )
        REPORT_JSON_PATH.write_text(
            json.dumps({
                "schema_version": "1.0",
                "preset": preset.name,
                "verdict": "dry_run",
                "summary": {"raw": 0, "screened": 0, "validated": 0,
                            "rejected": 0, "promoted": 0},
                "candidates": [],
                "dry_run": True,
            }, indent=2),
            encoding="utf-8",
        )
        return 0

    python_exec = sys.executable or "python"
    cmd = [python_exec, "-m", "research.run_research", "--preset", preset.name]
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    return int(proc.returncode)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> int:
    target = args.target
    if target == "latest":
        if not REPORT_MARKDOWN_PATH.exists():
            print("error: no report_latest.md found. Run a preset first.", file=sys.stderr)
            return 2
        print(REPORT_MARKDOWN_PATH.read_text(encoding="utf-8"))
        return 0
    if target == "history":
        reports = sorted(RESEARCH_HISTORY_DIR.rglob("report_*.md"))
        if not reports:
            print("no archived reports found")
            return 0
        limit = int(args.limit or 20)
        for path in reports[-limit:]:
            print(path.relative_to(REPO_ROOT).as_posix())
        return 0
    print(f"error: unknown report target {target!r}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

def cmd_history(args: argparse.Namespace) -> int:
    meta = read_run_meta_sidecar(RUN_META_PATH)
    print("== latest run meta ==")
    if meta is None:
        print("(none — no run_meta_latest.v1.json found)")
    else:
        compact = {
            "run_id": meta.get("run_id"),
            "preset_name": meta.get("preset_name"),
            "started_at_utc": meta.get("started_at_utc"),
            "completed_at_utc": meta.get("completed_at_utc"),
            "candidate_summary": meta.get("candidate_summary"),
            "diagnostic_only": meta.get("diagnostic_only"),
            "excluded_from_candidate_promotion": meta.get("excluded_from_candidate_promotion"),
        }
        print(json.dumps(compact, indent=2))
    limit = int(args.limit or 10)
    print()
    print(f"== last {limit} run-state snapshots under research/history/ ==")
    if not RESEARCH_HISTORY_DIR.exists():
        print("(research/history/ does not exist yet)")
        return 0
    runs = sorted(RESEARCH_HISTORY_DIR.iterdir(), key=lambda p: p.name)
    for path in runs[-limit:]:
        print(path.relative_to(REPO_ROOT).as_posix())
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def _header_matches_row_schema() -> tuple[bool, str]:
    if not STRATEGY_MATRIX_PATH.exists():
        return True, "strategy_matrix.csv does not exist (fresh state)"
    with STRATEGY_MATRIX_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(next(reader))
        except StopIteration:
            return True, "empty file"
    if header == ROW_SCHEMA:
        return True, "header matches ROW_SCHEMA"
    return False, (
        f"stale header detected: {header[:3]}... expected {ROW_SCHEMA[:3]}... — "
        "legacy rows from a prior schema may be present"
    )


def _check_disk_space(min_free_mb: int = 200) -> tuple[bool, str]:
    usage = shutil.disk_usage(REPO_ROOT)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < min_free_mb:
        return False, f"only {free_mb:.0f} MB free; want >= {min_free_mb} MB"
    return True, f"{free_mb:.0f} MB free"


def _check_presets_valid() -> tuple[bool, str]:
    broken: list[str] = []
    for preset in PRESETS:
        issues = validate_preset(preset)
        if issues:
            broken.append(f"{preset.name}: {issues}")
    if broken:
        return False, "; ".join(broken)
    return True, f"{len(PRESETS)} presets validate"


def _check_run_meta_adjacent() -> tuple[bool, str]:
    # Presence is not required (fresh install), but if present, it must be
    # parseable.
    if not RUN_META_PATH.exists():
        return True, "no run_meta_latest yet (fresh install)"
    payload = read_run_meta_sidecar(RUN_META_PATH)
    if payload is None:
        return False, "run_meta_latest.v1.json exists but is not parseable"
    return True, f"run_meta_latest readable; preset={payload.get('preset_name')!r}"


def cmd_doctor(_args: argparse.Namespace) -> int:
    checks = [
        ("strategy_matrix header", _header_matches_row_schema()),
        ("disk space", _check_disk_space()),
        ("presets validate", _check_presets_valid()),
        ("run_meta adjacency", _check_run_meta_adjacent()),
    ]
    ok = True
    for name, (passed, detail) in checks:
        marker = "OK  " if passed else "FAIL"
        print(f"[{marker}] {name}: {detail}")
        ok = ok and passed
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="researchctl",
        description=(
            "Single-command research operations. "
            "Deploy is NOT a researchctl subcommand — use scripts/deploy.sh."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a preset.")
    run.add_argument("preset_name", help="Preset name (see research/presets.py).")
    run.add_argument("--dry-run", action="store_true",
                     help="Skip the heavy research engine; print plan + write stub report.")
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="Report access (latest | history).")
    report.add_argument("target", choices=["latest", "history"])
    report.add_argument("--limit", type=int, default=20, help="Max rows on 'history'.")
    report.set_defaults(func=cmd_report)

    history = sub.add_parser("history", help="Show recent run metadata.")
    history.add_argument("--limit", type=int, default=10)
    history.set_defaults(func=cmd_history)

    doctor = sub.add_parser("doctor", help="Local health checks.")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
