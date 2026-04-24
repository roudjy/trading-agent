"""v3.15 unit tests: report_agent paper_layer_summary + markdown section."""

from __future__ import annotations

from research.report_agent import (
    _append_paper_layer_section,
    _paper_layer_summary,
)


def _ledger() -> dict:
    return {
        "paper_ledger_version": "v0.1",
        "paper_venues_version": "v0.1",
        "overall_event_counts": {
            "signal": 4, "order": 3, "fill": 3,
            "reject": 1, "skip": 0, "position": 3,
        },
    }


def _divergence() -> dict:
    return {
        "paper_divergence_version": "v0.1",
        "paper_venues_version": "v0.1",
        "severity_counts": {"low": 2, "medium": 1, "high": 0},
    }


def _readiness() -> dict:
    return {
        "paper_readiness_version": "v0.1",
        "counts": {
            "ready_for_paper_promotion": 1,
            "blocked": 1,
            "insufficient_evidence": 0,
        },
        "entries": [{"candidate_id": "c1"}, {"candidate_id": "c2"}],
    }


def test_paper_layer_summary_happy_path():
    summary = _paper_layer_summary(_ledger(), _divergence(), _readiness())
    assert summary is not None
    assert summary["paper_ledger_version"] == "v0.1"
    assert summary["paper_divergence_version"] == "v0.1"
    assert summary["paper_readiness_version"] == "v0.1"
    assert summary["paper_venues_version"] == "v0.1"
    assert summary["authoritative"] is False
    assert summary["diagnostic_only"] is True
    assert summary["live_eligible"] is False
    assert summary["ledger_event_counts"]["fill"] == 3
    assert summary["divergence_severity_counts"]["medium"] == 1
    assert summary["readiness_counts"]["blocked"] == 1
    assert summary["candidate_count"] == 2


def test_paper_layer_summary_missing_returns_none():
    assert _paper_layer_summary(None, None, None) is None


def test_paper_layer_summary_partial_sidecars_still_emits():
    # Only readiness present — still useful
    summary = _paper_layer_summary(None, None, _readiness())
    assert summary is not None
    assert summary["readiness_counts"]["ready_for_paper_promotion"] == 1
    assert summary["ledger_event_counts"] == {}
    assert summary["paper_ledger_version"] is None


def test_markdown_section_renders_when_summary_present():
    lines: list[str] = []
    _append_paper_layer_section(
        lines,
        _paper_layer_summary(_ledger(), _divergence(), _readiness()),
    )
    text = "\n".join(lines)
    assert "Paper Layer Summary (v3.15" in text
    assert "live_eligible=False" in text
    assert "candidate_count: 2" in text
    assert "fill=3" in text
    assert "medium=1" in text
    assert "blocked=1" in text


def test_markdown_section_is_noop_without_summary():
    lines: list[str] = []
    _append_paper_layer_section(lines, None)
    assert lines == []
