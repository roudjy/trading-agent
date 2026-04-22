"""Smoke test: default daily preset dry-run via researchctl.

Invokes ``researchctl run trend_equities_4h_baseline --dry-run`` and asserts:

- exit code 0
- ``research/report_latest.md`` exists and names the preset
- ``research/report_latest.json`` exists and carries the expected preset name
- the dry-run does NOT touch ``research/strategy_matrix.csv`` or
  ``research/research_latest.json`` (frozen public contract must stay
  byte-identical during a dry-run).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "research" / "strategy_matrix.csv"
JSON_PATH = REPO_ROOT / "research" / "research_latest.json"
REPORT_MD = REPO_ROOT / "research" / "report_latest.md"
REPORT_JSON = REPO_ROOT / "research" / "report_latest.json"


def _digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_default_preset_dry_run_smoke(tmp_path: Path):
    pre_csv = _digest(CSV_PATH)
    pre_json = _digest(JSON_PATH)

    preserved_md = REPORT_MD.read_bytes() if REPORT_MD.exists() else None
    preserved_js = REPORT_JSON.read_bytes() if REPORT_JSON.exists() else None

    try:
        proc = subprocess.run(
            [sys.executable, "researchctl.py", "run",
             "trend_equities_4h_baseline", "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

        assert REPORT_MD.exists()
        md_body = REPORT_MD.read_text(encoding="utf-8")
        assert "trend_equities_4h_baseline" in md_body

        assert REPORT_JSON.exists()
        payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        assert payload["preset"] == "trend_equities_4h_baseline"
        assert payload["verdict"] == "dry_run"

        # Frozen public contract must stay untouched during a dry-run.
        assert _digest(CSV_PATH) == pre_csv
        assert _digest(JSON_PATH) == pre_json
    finally:
        # Restore whatever report was there before the smoke ran.
        if preserved_md is None:
            if REPORT_MD.exists():
                REPORT_MD.unlink()
        else:
            REPORT_MD.write_bytes(preserved_md)
        if preserved_js is None:
            if REPORT_JSON.exists():
                REPORT_JSON.unlink()
        else:
            REPORT_JSON.write_bytes(preserved_js)
