from __future__ import annotations

from packages.qre_research import equity_universe_quality as quality


def test_quality_report_flags_ambiguity_and_has_closed_statuses() -> None:
    report = quality.build_equity_universe_quality()
    statuses = {row["status"] for row in report["rows"]}
    assert statuses <= {"OK", "WARN", "FAIL", "UNKNOWN"}
    assert report["summary"]["ambiguous_mappings"] >= 1
    assert report["summary"]["ok_instruments"] > 0


def test_quality_report_no_duplicate_canonical_ids() -> None:
    report = quality.build_equity_universe_quality()
    assert report["summary"]["duplicate_canonical_ids"] == 0
    assert report["summary"]["duplicate_symbols"] == 0
