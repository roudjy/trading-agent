from __future__ import annotations

import json
from pathlib import Path

from research.equity_factors import recipe_manifest


def test_recipe_manifest_writes_expected_artifact(tmp_path: Path) -> None:
    paths = recipe_manifest.write_outputs(repo_root=tmp_path)
    assert paths["recipes"] == "artifacts/equity_factors/equity_factor_recipes_latest.v1.json"
    payload = json.loads((tmp_path / paths["recipes"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "equity_factor_recipes"
    assert payload["safety_invariants"]["research_only"] is True


def test_recipe_manifest_is_deterministic_and_safe() -> None:
    left = recipe_manifest.build_equity_factor_recipe_catalog()
    right = recipe_manifest.build_equity_factor_recipe_catalog()
    assert left == right
    assert left["summary"]["recipe_count"] >= 10
