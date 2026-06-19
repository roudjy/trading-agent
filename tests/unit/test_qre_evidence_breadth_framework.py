from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from research import qre_evidence_breadth_framework as breadth


def _write_disposition_memory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_hypothesis_disposition_memory",
        "record": {
            "hypothesis_id": "trend_pullback_behavior_v1",
            "behavior_id": "trend_pullback",
            "preset_id": "trend_pullback_continuation_daily_v1",
            "timeframe": "1d",
            "accepted_lineage_refs": ["lineage-1", "lineage-2"],
            "accepted_oos_refs": [],
            "regime_refs": ["trend", "high_volatility"],
            "window_refs": ["window-1", "window-2"],
            "disposition_scope": {
                "behavior_id": "trend_pullback",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "timeframe": "1d",
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_evidence_breadth_framework_aggregates_existing_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_disposition_memory(tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json")

    monkeypatch.setattr(
        breadth,
        "build_equity_universe_catalog",
        lambda: {
            "universes": [
                {"universe_id": "nl_equities"},
                {"universe_id": "us_large_mid"},
                {"universe_id": "asia_developed_liquid"},
            ],
            "instruments": [
                {"symbol": "ASML", "asset_class": "equity", "universe_ids": ["nl_equities"]},
                {"symbol": "AAPL", "asset_class": "equity", "universe_ids": ["us_large_mid"]},
                {"symbol": "SONY", "asset_class": "equity", "universe_ids": ["asia_developed_liquid"]},
            ],
        },
    )
    monkeypatch.setattr(
        breadth.discovery_catalog,
        "list_assets",
        lambda: [
            type("A", (), {"to_payload": lambda self: {"symbol": "ASML", "region": "NL/EU", "sector": "Technology", "asset_class": "equity"}})(),
            type("A", (), {"to_payload": lambda self: {"symbol": "AAPL", "region": "US", "sector": "Technology", "asset_class": "equity"}})(),
            type("A", (), {"to_payload": lambda self: {"symbol": "SONY", "region": "Asia/proxies", "sector": "Consumer Discretionary", "asset_class": "equity"}})(),
        ],
    )
    monkeypatch.setattr(
        breadth.discovery_catalog,
        "list_presets",
        lambda: [
            type("P", (), {"to_payload": lambda self: {"preset_id": "trend_pullback_continuation_daily_v1", "behavior_family": "trend_pullback", "allowed_timeframes": ["1d"]}})(),
            type("P", (), {"to_payload": lambda self: {"preset_id": "vol_compression_breakout_4h_v1", "behavior_family": "volatility_compression_breakout", "allowed_timeframes": ["4h"]}})(),
        ],
    )
    monkeypatch.setattr(
        breadth.discovery_catalog,
        "build_bounded_candidate_basket",
        lambda max_candidates=15: [
            {"candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL"},
            {"candidate_id": "seed::vol_compression_breakout_4h_v1::SONY"},
        ],
    )
    monkeypatch.setattr(
        breadth,
        "build_real_basket_evidence_coverage",
        lambda repo_root, max_candidates: {
            "rows": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "symbol": "AAPL",
                    "region": "US",
                    "behavior_family": "trend_pullback",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "timeframes": ["1d"],
                    "evidence_completeness_status": "thin",
                    "evidence_completeness_score_pct": 40,
                    "missing_evidence_taxonomy": ["oos_evidence_missing"],
                },
                {
                    "candidate_id": "seed::vol_compression_breakout_4h_v1::SONY",
                    "symbol": "SONY",
                    "region": "Asia/proxies",
                    "behavior_family": "volatility_compression_breakout",
                    "preset_id": "vol_compression_breakout_4h_v1",
                    "hypothesis_id": "vol_compression_expansion_behavior_v1",
                    "timeframes": ["4h"],
                    "evidence_completeness_status": "partial",
                    "evidence_completeness_score_pct": 60,
                    "missing_evidence_taxonomy": ["accepted_oos_missing"],
                },
            ]
        },
    )

    left = breadth.build_evidence_breadth_framework(repo_root=tmp_path, max_candidates=5)
    right = breadth.build_evidence_breadth_framework(repo_root=tmp_path, max_candidates=5)

    assert left == right
    assert left["status"] == "ready"
    assert left["summary"]["accepted_lineage_ref_count"] == 2
    assert left["summary"]["accepted_oos_ref_count"] == 0
    assert left["summary"]["rejected_hypothesis_count"] >= 1
    assert left["breadth_priority_recommendations"]
    assert any(row["dimension"] == "region" for row in left["coverage_matrix"])
    assert any(row["dimension"] == "universe" for row in left["coverage_matrix"])
    assert any(row["dimension"] == "independent_oos_window" for row in left["coverage_matrix"])
    assert left["authority_flags"]["safe_to_execute"] is False
    assert left["safety_invariants"]["crypto_excluded_without_explicit_authorization"] is True
    assert left["deterministic_hash"].startswith("sha256:")


def test_write_outputs_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_disposition_memory(tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json")
    monkeypatch.setattr(breadth, "build_equity_universe_catalog", lambda: {"universes": [], "instruments": []})
    monkeypatch.setattr(breadth.discovery_catalog, "list_assets", lambda: [])
    monkeypatch.setattr(breadth.discovery_catalog, "list_presets", lambda: [])
    monkeypatch.setattr(breadth.discovery_catalog, "build_bounded_candidate_basket", lambda max_candidates=15: [])
    monkeypatch.setattr(breadth, "build_real_basket_evidence_coverage", lambda repo_root, max_candidates: {"rows": []})

    report = breadth.build_evidence_breadth_framework(repo_root=tmp_path, max_candidates=1)
    paths = breadth.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_evidence_breadth_framework/latest.json",
        "operator_summary": "logs/qre_evidence_breadth_framework/operator_summary.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()


def test_framework_never_includes_crypto_without_explicit_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_disposition_memory(tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json")
    monkeypatch.setattr(
        breadth,
        "build_equity_universe_catalog",
        lambda: {
            "universes": [{"universe_id": "global_ex_crypto_research_universe"}],
            "instruments": [
                {"symbol": "BTC-USD", "asset_class": "crypto", "universe_ids": ["global_ex_crypto_research_universe"]},
                {"symbol": "AAPL", "asset_class": "equity", "universe_ids": ["global_ex_crypto_research_universe"]},
            ],
        },
    )
    monkeypatch.setattr(
        breadth.discovery_catalog,
        "list_assets",
        lambda: [
            type("A", (), {"to_payload": lambda self: {"symbol": "BTC-USD", "region": "crypto", "sector": "crypto", "asset_class": "crypto"}})(),
            type("A", (), {"to_payload": lambda self: {"symbol": "AAPL", "region": "US", "sector": "Technology", "asset_class": "equity"}})(),
        ],
    )
    monkeypatch.setattr(breadth.discovery_catalog, "list_presets", lambda: [])
    monkeypatch.setattr(breadth.discovery_catalog, "build_bounded_candidate_basket", lambda max_candidates=15: [])
    monkeypatch.setattr(breadth, "build_real_basket_evidence_coverage", lambda repo_root, max_candidates: {"rows": []})

    report = breadth.build_evidence_breadth_framework(repo_root=tmp_path, max_candidates=1)

    assert all(row["scope_key"] != "BTC-USD" for row in report["coverage_matrix"])
    assert report["safety_invariants"]["crypto_excluded_without_explicit_authorization"] is True


def test_framework_source_is_read_only() -> None:
    source = Path(breadth.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "requests." not in source
