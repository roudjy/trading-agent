from __future__ import annotations

from pathlib import Path


ROADMAP = Path("docs/roadmap/qre_maturity_roadmap_to_100.md")


def test_qre_maturity_roadmap_document_exists() -> None:
    assert ROADMAP.is_file()


def test_qre_maturity_roadmap_is_documentation_only() -> None:
    text = ROADMAP.read_text(encoding="utf-8")

    assert "This document is the canonical roadmap" in text
    assert "active canonical roadmap for current QRE" in text
    assert "Phase 7C" in text
    assert "feat: add routing score scaffold" in text
    assert "generic, bounded, reproducible research engine" in text
    assert "AAPL/NVDA may appear only as first-batch fixture" in text
    assert "No AAPL/NVDA special-case logic belongs in core code paths." in text
    assert "bounded-request-driven and symbol-agnostic" in text
    assert "1. generic bounded basket request schema;" in text
    assert "7. evidence acceptance integration;" in text
    assert "### Step 7 - Research intelligence and candidate lifecycle" in text
    assert "### Step 8 - Shadow / paper / live deferral" in text
    assert "This document does not implement:" in text
