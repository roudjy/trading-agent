from __future__ import annotations

from pathlib import Path

from research import qre_fundamental_provider_report as report


def test_provider_report_is_deterministic_and_contains_disclaimer() -> None:
    left = report.collect_snapshot()
    right = report.collect_snapshot()
    assert left == right
    assert "No data has been fetched" in left["disclaimer"]
    assert left["summary"]["total_providers"] >= 10


def test_provider_report_writes_markdown(tmp_path: Path) -> None:
    paths = report.write_outputs(repo_root=tmp_path)
    markdown = (tmp_path / paths["markdown"]).read_text(encoding="utf-8")
    assert "QRE Fundamental Provider Candidate Registry" in markdown
    assert "No trade signals" in markdown
