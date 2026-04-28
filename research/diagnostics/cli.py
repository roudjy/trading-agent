"""Read-only CLI for the observability layer.

Subcommands:

    python -m research.observability build
        Build all 5 active observability artifacts and the aggregator
        summary. Idempotent. Writes ONLY under research/observability/.

    python -m research.observability status
        Print a compact summary of the latest aggregator artifact, if
        present. Read-only.

This module imports nothing from runtime / decision modules.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .aggregator import (
    build_observability_summary,
    write_observability_summary,
)
from .artifact_health import inspect_artifact_health, write_artifact_health
from .clock import default_now_utc
from .failure_modes import build_failure_modes_artifact, write_failure_modes
from .paths import OBSERVABILITY_DIR, OBSERVABILITY_SUMMARY_PATH
from .system_integrity import (
    build_system_integrity_snapshot,
    write_system_integrity,
)
from .throughput import build_throughput_artifact, write_throughput

EXIT_OK = 0
EXIT_PARSER_ERROR = 2
EXIT_PARTIAL = 3
EXIT_FAILURE = 4


def _ensure_dir() -> None:
    OBSERVABILITY_DIR.mkdir(parents=True, exist_ok=True)


def cmd_build(now_utc: datetime | None = None) -> int:
    """Build all 5 active artifacts and the aggregator summary.

    Best-effort: a failure in one component does not abort the build.
    Returns ``EXIT_PARTIAL`` if any component raised an unexpected
    exception (which is a programming error — pure read modules
    shouldn't raise). Returns ``EXIT_OK`` on a clean build, even if
    some upstream input artifacts are missing (that's normal).
    """
    when = now_utc or default_now_utc()
    _ensure_dir()
    partial = False

    components: list[tuple[str, callable, callable]] = [
        ("artifact_health", lambda: inspect_artifact_health(now_utc=when), write_artifact_health),
        ("failure_modes", lambda: build_failure_modes_artifact(now_utc=when), write_failure_modes),
        ("throughput_metrics", lambda: build_throughput_artifact(now_utc=when), write_throughput),
        ("system_integrity", lambda: build_system_integrity_snapshot(now_utc=when), write_system_integrity),
    ]

    for name, builder, writer in components:
        try:
            payload = builder()
            writer(payload)
            print(f"[observability] wrote {name}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001  - we deliberately catch broadly
            partial = True
            print(
                f"[observability] component {name} raised: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    # Aggregator runs after the per-component writes so it picks up
    # the freshly written artifacts.
    try:
        summary = build_observability_summary(now_utc=when)
        write_observability_summary(summary)
        print("[observability] wrote observability_summary", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        partial = True
        print(
            f"[observability] aggregator raised: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

    return EXIT_PARTIAL if partial else EXIT_OK


def cmd_status() -> int:
    summary_path = OBSERVABILITY_SUMMARY_PATH
    if not summary_path.exists():
        print("no observability summary present", file=sys.stderr)
        return EXIT_OK
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"summary unreadable: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    overall = payload.get("overall_status", "unknown")
    counts = payload.get("component_status_counts", {})
    action = payload.get("recommended_next_human_action", "unknown")
    print(f"overall_status: {overall}")
    print(f"component_status_counts: {counts}")
    print(f"recommended_next_human_action: {action}")
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.observability",
        description="Read-only observability artifacts for the trading agent.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="Build all observability artifacts.")
    sub.add_parser("status", help="Print the latest observability summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_PARSER_ERROR

    if args.cmd == "build":
        return cmd_build()
    if args.cmd == "status":
        return cmd_status()
    parser.print_help(sys.stderr)
    return EXIT_PARSER_ERROR


__all__ = ["EXIT_FAILURE", "EXIT_OK", "EXIT_PARSER_ERROR", "EXIT_PARTIAL", "cmd_build", "cmd_status", "main"]
