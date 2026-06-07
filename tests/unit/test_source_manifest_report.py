from __future__ import annotations

from pathlib import Path

from research.external_intelligence import source_manifest_report as report


def test_source_manifest_report_is_deterministic_and_contains_safety_disclaimer() -> None:
    left = report.collect_snapshot()
    right = report.collect_snapshot()
    assert left == right
    markdown = report.render_markdown(left)
    assert "No data fetched" in markdown
    assert "No provider activated" in markdown


def test_source_manifest_report_writes_markdown(tmp_path: Path) -> None:
    paths = report.write_outputs(repo_root=tmp_path)
    markdown = (tmp_path / paths["markdown"]).read_text(encoding="utf-8")
    assert "QRE Source Manifest Schema and License Policy" in markdown
    assert "quality_gated eligible providers: none" in markdown
