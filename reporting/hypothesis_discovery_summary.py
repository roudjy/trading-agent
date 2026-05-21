"""Read-only summary for minimal v3.15.19 Hypothesis Discovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

from research.hypothesis_discovery import campaign_seed_proposer as proposer


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.15.19-minimal-2026-05-21"
REPORT_KIND: Final[str] = "hypothesis_discovery_summary"


def read_latest_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    p = path or proposer.ARTIFACT_LATEST
    if not p.is_file():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def collect_summary(path: Path | None = None) -> dict[str, Any]:
    snap = read_latest_snapshot(path)
    if snap is None:
        return {
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "available": False,
            "safe_to_execute": False,
            "proposal_only": True,
            "final_recommendation": "not_available",
        }
    return {
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "available": True,
        "safe_to_execute": False,
        "proposal_only": True,
        "source_module_version": snap.get("module_version"),
        "generated_at_utc": snap.get("generated_at_utc"),
        "counts": dict(snap.get("counts") or {}),
        "active_diagnostics": list(snap.get("active_diagnostics") or []),
        "score_semantics": snap.get("score_semantics"),
        "final_recommendation": snap.get("final_recommendation"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.hypothesis_discovery_summary",
        description="Read-only Hypothesis Discovery summary.",
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    _ = args.status
    print(json.dumps(collect_summary(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
