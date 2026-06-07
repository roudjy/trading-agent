from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_universe_report


def test_universe_report_is_deterministic_and_contains_required_ids() -> None:
    left = qre_universe_report.collect_snapshot()
    right = qre_universe_report.collect_snapshot()
    assert left == right
    for universe_id in (
        "nl_equities",
        "europe_large_mid",
        "europe_small_mid",
        "us_large_mid",
        "asia_developed_liquid",
        "global_developed_liquid",
        "global_ex_crypto_research_universe",
    ):
        assert left["required_universe_ids_present"][universe_id] is True
    assert "No buy/sell recommendations, no trade signals" in left["disclaimer"]


def test_universe_report_write_outputs_match_counts(tmp_path: Path) -> None:
    paths = qre_universe_report.write_outputs(repo_root=tmp_path)
    payload = json.loads((tmp_path / paths["json"]).read_text(encoding="utf-8"))
    markdown = (tmp_path / paths["markdown"]).read_text(encoding="utf-8")
    assert payload["report_kind"] == "qre_equity_universe_operator_report"
    assert payload["summary"]["recipe_count"] >= 10
    assert payload["summary"]["total_instruments"] == 158
    assert "Research-only report." in markdown
