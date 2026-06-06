from __future__ import annotations

from research import equity_universe_identity as identity


def test_identity_report_blocks_ambiguous_rows_from_hypothesis_seed() -> None:
    report = identity.build_instrument_identity_report()
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["ADYEN"]["identity_status"] == "OK"
    assert rows["ADYEN"]["eligible_for_hypothesis_seed"] is True
    assert rows["ASMI"]["identity_status"] == "WARN"
    assert rows["ASMI"]["eligible_for_hypothesis_seed"] is False


def test_identity_report_uses_closed_status_vocabulary() -> None:
    report = identity.build_instrument_identity_report()
    assert report["status_vocabulary"] == ["OK", "WARN", "FAIL", "UNKNOWN"]
    assert report["summary"]["duplicate_canonical_ids"] == 0
    assert report["summary"]["blocked_for_hypothesis_seed"] >= 1
