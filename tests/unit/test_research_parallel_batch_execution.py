from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from research import batch_execution as batch_execution_module
from research import run_research as run_research_module
from tests.unit.test_run_research_observability import (
    _OrderedValidationEngine,
    _patch_common_runner,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_parallel_batch_execution_merges_results_in_planned_order(monkeypatch, tmp_path: Path):
    _patch_common_runner(monkeypatch, tmp_path, _OrderedValidationEngine)
    monkeypatch.setattr(run_research_module, "BATCH_EXECUTOR_CLASS", ThreadPoolExecutor)
    monkeypatch.setattr(
        run_research_module,
        "load_research_config",
        lambda config_path="config/config.yaml": {"execution": {"max_workers": 2}},
    )

    def _factory(name_hint):
        def _build(**params):
            return SimpleNamespace(name_hint=name_hint)

        return _build

    strategies = [
        {
            "name": "zeta_strategy",
            "family": "trend",
            "strategy_family": "a_family",
            "position_structure": "outright",
            "initial_lane_support": "supported",
            "hypothesis": "zeta",
            "factory": _factory("zeta_strategy"),
            "params": {"periode": [14]},
        },
        {
            "name": "alpha_strategy",
            "family": "trend",
            "strategy_family": "z_family",
            "position_structure": "outright",
            "initial_lane_support": "supported",
            "hypothesis": "alpha",
            "factory": _factory("alpha_strategy"),
            "params": {"periode": [14]},
        },
    ]
    monkeypatch.setattr(run_research_module, "get_enabled_strategies", lambda: strategies)
    monkeypatch.setattr(batch_execution_module, "get_enabled_strategies", lambda: strategies)

    run_research_module.run_research()

    public_json = _load_json(tmp_path / "research" / "research_latest.json")
    manifest = _load_json(tmp_path / "research" / "run_manifest_latest.v1.json")
    batches = _load_json(tmp_path / "research" / "run_batches_latest.v1.json")
    with (tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert manifest["execution"] == {"max_workers": 2, "execution_mode": "process_pool"}
    assert [batch["execution_mode"] for batch in batches["batches"]] == ["process_pool", "process_pool"]
    assert [row["strategy_name"] for row in public_json["results"]] == ["alpha_strategy", "zeta_strategy"]
    assert [row["strategy_name"] for row in csv_rows] == ["alpha_strategy", "zeta_strategy"]
