from __future__ import annotations

from pathlib import Path


def test_providers_do_not_import_validation_or_locked_oos_views() -> None:
    src = Path("packages/qre_research/alpha_discovery/providers.py").read_text(encoding="utf-8")
    assert "validation_view" not in src
    assert "locked_oos_view" not in src
    assert "run_research(" not in src


def test_runner_materializes_discovery_validation_and_locked_oos_views() -> None:
    src = Path("packages/qre_research/alpha_discovery/runner.py").read_text(encoding="utf-8")
    assert "build_discovery_view" in src
    assert "build_validation_view" in src
    assert "build_locked_oos_view" in src
