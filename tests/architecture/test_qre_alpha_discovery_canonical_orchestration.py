from __future__ import annotations

from pathlib import Path


def test_empirical_alpha_discovery_path_references_canonical_run_research() -> None:
    src = Path("packages/qre_research/alpha_discovery/runner.py").read_text(encoding="utf-8")
    assert "research.run_research" in src
    assert "run_research(preset_override=preset_override)" in src


def test_alpha_discovery_runner_does_not_enable_step5_or_live_lanes() -> None:
    src = Path("packages/qre_research/alpha_discovery/runner.py").read_text(encoding="utf-8")
    forbidden = ("Step 5", "shadow_activation_allowed = True", "paper_activation_allowed = True", "live_activation_allowed = True")
    assert not any(token in src for token in forbidden)
