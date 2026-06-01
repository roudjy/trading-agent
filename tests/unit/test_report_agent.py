"""Unit tests for the v3.10 post-run report agent."""

from __future__ import annotations

import json
from pathlib import Path

from research.presets import get_preset
from research.report_agent import (
    REPORT_JSON_PATH,
    REPORT_MARKDOWN_PATH,
    VERDICT_CANDIDATES_NO_PROMOTION,
    VERDICT_NIETS_BRUIKBAARS,
    VERDICT_PROMOTED,
    _build_trend_pullback_exit_impact,
    _build_trend_pullback_exit_quality,
    build_report_payload,
    classify_verdict,
    generate_post_run_report,
    render_markdown,
    suggest_next_experiment,
)
from research.run_meta import (
    build_candidate_summary,
    build_run_meta_payload,
    write_run_meta_sidecar,
)


def _write_research_latest(path: Path, rows: list[dict]):
    payload = {
        "generated_at_utc": "2026-04-22T06:00:00+00:00",
        "count": len(rows),
        "summary": {
            "success": sum(1 for r in rows if r.get("success")),
            "failed": sum(1 for r in rows if not r.get("success")),
            "goedgekeurd": sum(1 for r in rows if r.get("goedgekeurd")),
        },
        "results": rows,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_meta(path: Path, preset_name: str = "trend_equities_4h_baseline", **kw):
    preset = get_preset(preset_name)
    payload = build_run_meta_payload(
        run_id=kw.get("run_id", "run-1"),
        preset=preset,
        started_at_utc=kw.get("started_at_utc", "2026-04-22T06:00:00+00:00"),
        completed_at_utc=kw.get("completed_at_utc", "2026-04-22T06:30:00+00:00"),
        git_revision=kw.get("git_revision", "abc"),
        config_hash=kw.get("config_hash", "hash"),
        candidate_summary=kw.get("candidate_summary") or build_candidate_summary(),
        top_rejection_reasons=kw.get("top_rejection_reasons") or [],
        artifact_paths={},
    )
    write_run_meta_sidecar(payload, path=path)


def test_empty_run_produces_niets_bruikbaars_verdict(tmp_path: Path):
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(research_path, rows=[])
    _write_meta(meta_path)

    report = build_report_payload(
        run_id="run-1",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    assert report["verdict"] == VERDICT_NIETS_BRUIKBAARS
    assert report["summary"]["raw"] == 0


def test_candidates_but_no_promotion(tmp_path: Path):
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(
        research_path,
        rows=[
            {"strategy_name": "sma_crossover", "asset": "NVDA", "interval": "4h",
             "success": True, "goedgekeurd": False, "reden": "deflated_sharpe_fail"},
            {"strategy_name": "breakout_momentum", "asset": "NVDA", "interval": "4h",
             "success": True, "goedgekeurd": False, "reden": "deflated_sharpe_fail"},
        ],
    )
    _write_meta(
        meta_path,
        candidate_summary=build_candidate_summary(raw=2, screened=2, validated=2, rejected=2, promoted=0),
        top_rejection_reasons=[{"reason": "deflated_sharpe_fail", "count": 2}],
    )

    report = build_report_payload(
        run_id="run-2",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    assert report["verdict"] == VERDICT_CANDIDATES_NO_PROMOTION
    assert report["top_rejection_reasons"][0]["count"] == 2
    assert report["summary"]["promoted"] == 0


def test_promoted_candidate_verdict(tmp_path: Path):
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(
        research_path,
        rows=[
            {"strategy_name": "sma_crossover", "asset": "NVDA", "interval": "4h",
             "success": True, "goedgekeurd": True, "sharpe": 1.5, "win_rate": 0.6},
        ],
    )
    _write_meta(
        meta_path,
        candidate_summary=build_candidate_summary(raw=1, screened=1, validated=1, rejected=0, promoted=1),
    )

    report = build_report_payload(
        run_id="run-3",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    assert report["verdict"] == VERDICT_PROMOTED
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["strategy_name"] == "sma_crossover"


def test_render_markdown_contains_required_sections():
    md = render_markdown({
        "run_id": "run-4",
        "generated_at_utc": "2026-04-22T06:45:00+00:00",
        "preset": "trend_equities_4h_baseline",
        "verdict": VERDICT_PROMOTED,
        "summary": {"raw": 1, "screened": 1, "validated": 1, "rejected": 0, "promoted": 1},
        "candidates": [{"strategy_name": "sma_crossover", "asset": "NVDA",
                        "interval": "4h", "sharpe": 1.5, "win_rate": 0.6}],
        "top_rejection_reasons": [],
        "top_rejection_reasons_by_layer": {"screening_layer": [], "promotion_layer": []},
        "per_candidate_diagnostics": [],
        "join_stats": {},
        "red_flags": [],
        "regime_diagnostics": {},
        "statistical_diagnostics": {},
        "next_experiment": "Hercheck OOS",
    })
    assert "# Research report" in md
    # v3.11 narrative section titles
    assert "## Hypothese" in md
    assert "## Samenvatting" in md
    assert "## Wat werkte" in md
    assert "## Wat werkte niet" in md
    assert "## Waarom" in md
    assert "## Volgende stap" in md


def test_generate_post_run_report_writes_both_artifacts(tmp_path: Path):
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    md_path = tmp_path / "report_latest.md"
    js_path = tmp_path / "report_latest.json"
    _write_research_latest(research_path, rows=[])
    _write_meta(meta_path)

    report = generate_post_run_report(
        run_id="run-5",
        research_latest_path=research_path,
        run_meta_path=meta_path,
        markdown_path=md_path,
        json_path=js_path,
    )
    assert md_path.exists()
    assert js_path.exists()
    assert report["verdict"] == VERDICT_NIETS_BRUIKBAARS
    restored = json.loads(js_path.read_text(encoding="utf-8"))
    assert restored == report


def test_classify_verdict_prefers_promoted_over_screened():
    assert classify_verdict({"promoted": 1, "screened": 5}, None) == VERDICT_PROMOTED
    assert classify_verdict({"promoted": 0, "screened": 5}, None) == VERDICT_CANDIDATES_NO_PROMOTION
    assert classify_verdict({"promoted": 0, "screened": 0, "validated": 0}, None) == VERDICT_NIETS_BRUIKBAARS


def test_suggest_next_experiment_covers_known_shapes():
    assert "universe" in suggest_next_experiment({"raw": 0}, [], None).lower()
    prompt = suggest_next_experiment(
        {"raw": 1, "promoted": 1},
        [{"strategy_name": "sma_crossover"}],
        None,
    )
    assert "OOS" in prompt or "walk-forward" in prompt
    assert "regime" in suggest_next_experiment(
        {"promoted": 0, "validated": 1, "screened": 1, "raw": 1}, [], None,
    ).lower()


def test_default_report_paths_live_inside_research_folder():
    assert Path("research/report_latest.md") == REPORT_MARKDOWN_PATH
    assert Path("research/report_latest.json") == REPORT_JSON_PATH


# ---------------------------------------------------------------------------
# v3.11 report schema additions
# ---------------------------------------------------------------------------


def test_report_schema_version_is_v11():
    from research.report_agent import REPORT_SCHEMA_VERSION

    assert REPORT_SCHEMA_VERSION == "1.1"


def test_summary_carries_screening_and_promotion_split(tmp_path: Path, monkeypatch):
    # v3.11: build_report_payload reads sidecars (candidate_registry,
    # run_filter_summary, defensibility, regime, cost_sensitivity) from
    # relative "research/*.v1.json" paths. Isolate the test by pointing
    # CWD at tmp_path so stray local sidecars from an earlier run don't
    # pollute the assertion.
    monkeypatch.chdir(tmp_path)
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(
        research_path,
        rows=[
            {"strategy_name": "sma_crossover", "asset": "NVDA", "interval": "4h",
             "success": True, "goedgekeurd": False, "reden": ""},
            {"strategy_name": "breakout_momentum", "asset": "NVDA", "interval": "4h",
             "success": True, "goedgekeurd": True, "reden": ""},
        ],
    )
    _write_meta(meta_path)

    report = build_report_payload(
        run_id="run-split-test",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    summary = report["summary"]
    # v3.10 keys still there
    assert "raw" in summary
    assert "promoted" in summary
    # v3.11 additive split
    assert isinstance(summary["screening"], dict)
    assert set(summary["screening"].keys()) >= {
        "raw", "eligible", "screening_passed", "screening_rejected"
    }
    assert isinstance(summary["promotion"], dict)
    assert set(summary["promotion"].keys()) >= {
        "evaluated", "promoted", "needs_investigation", "rejected_promotion"
    }


def test_top_rejection_reasons_by_layer_split(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate sidecar lookups — see comment above
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(
        research_path,
        rows=[
            {"strategy_name": "rsi", "asset": "BTC-USD", "interval": "1h",
             "success": False, "reden": "screening_criteria_not_met"},
            {"strategy_name": "rsi", "asset": "ETH-USD", "interval": "1h",
             "success": False, "reden": "screening_criteria_not_met"},
        ],
    )
    _write_meta(meta_path)

    report = build_report_payload(
        run_id="run-rejections",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    by_layer = report["top_rejection_reasons_by_layer"]
    assert set(by_layer.keys()) == {"screening_layer", "promotion_layer"}
    # Screening reasons derived from rows.reden when filter summary
    # sidecar is absent
    assert by_layer["screening_layer"]
    assert by_layer["screening_layer"][0]["reason"] == "screening_criteria_not_met"
    # promotion layer is empty without candidate_registry
    assert by_layer["promotion_layer"] == []


def test_per_candidate_diagnostics_and_join_stats(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate sidecar lookups — see comment above
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(
        research_path,
        rows=[
            {"strategy_name": "sma_crossover", "asset": "NVDA", "interval": "4h",
             "params_json": "{}", "success": True, "goedgekeurd": True,
             "sharpe": 1.5, "win_rate": 0.55, "reden": ""},
            {"strategy_name": "sma_crossover", "asset": "AMD", "interval": "4h",
             "params_json": "{}", "success": False,
             "reden": "screening_criteria_not_met"},
        ],
    )
    _write_meta(meta_path)

    report = build_report_payload(
        run_id="run-diagnostics",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    per_candidate = report["per_candidate_diagnostics"]
    assert len(per_candidate) == 2
    verdicts = {entry["verdict"] for entry in per_candidate}
    assert verdicts <= {
        "promoted",
        "needs_investigation",
        "rejected_promotion",
        "rejected_screening",
    }
    # Promoted row flips to 'promoted'; screened-out flips to
    # 'rejected_screening'
    assert any(e["verdict"] == "promoted" for e in per_candidate)
    assert any(e["verdict"] == "rejected_screening" for e in per_candidate)

    join_stats = report["join_stats"]
    assert join_stats["total_rows"] == 2
    # No candidate_registry sidecar in tmp_path => all unmatched
    assert join_stats["unmatched_candidate_registry"] == 2


def test_markdown_shows_hypothesis_and_waarom_sections(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate sidecar lookups — see comment above
    research_path = tmp_path / "research_latest.json"
    meta_path = tmp_path / "run_meta.json"
    _write_research_latest(
        research_path,
        rows=[
            {"strategy_name": "sma_crossover", "asset": "NVDA", "interval": "4h",
             "params_json": "{}", "success": True, "goedgekeurd": True,
             "sharpe": 1.5, "win_rate": 0.6, "reden": ""},
        ],
    )
    _write_meta(meta_path)

    from research.report_agent import build_report_payload, render_markdown

    report = build_report_payload(
        run_id="run-md",
        research_latest_path=research_path,
        run_meta_path=meta_path,
    )
    md = render_markdown(report)
    assert "## Hypothese" in md
    assert "## Wat werkte" in md
    assert "## Wat werkte niet" in md
    assert "## Waarom" in md
    assert "## Volgende stap" in md


def test_next_experiment_is_layer_aware_on_statistical_promotion_failures():
    report_like = {
        "raw": 10, "promoted": 0, "validated": 0, "screened": 0,
    }
    # dominant promotion-layer statistical failures
    reasons_by_layer = {
        "screening_layer": [],
        "promotion_layer": [
            {"reason": "psr_below_threshold", "count": 4},
            {"reason": "bootstrap_sharpe_ci_includes_zero", "count": 2},
        ],
    }
    msg = suggest_next_experiment(
        report_like,
        [],
        None,
        rejection_reasons_by_layer=reasons_by_layer,
    )
    assert "PSR" in msg or "statistische" in msg.lower()


def test_next_experiment_is_layer_aware_on_drawdown_failure():
    reasons_by_layer = {
        "screening_layer": [],
        "promotion_layer": [
            {"reason": "drawdown_above_limit", "count": 5},
        ],
    }
    msg = suggest_next_experiment(
        {"raw": 5, "promoted": 0},
        [],
        None,
        rejection_reasons_by_layer=reasons_by_layer,
    )
    assert "drawdown" in msg.lower() or "risk" in msg.lower()


def test_next_experiment_steers_to_hypothesis_when_screening_dominant():
    reasons_by_layer = {
        "screening_layer": [
            {"reason": "screening_criteria_not_met", "count": 30},
        ],
        "promotion_layer": [],
    }
    msg = suggest_next_experiment(
        {"raw": 30, "promoted": 0},
        [],
        None,
        rejection_reasons_by_layer=reasons_by_layer,
    )
    assert "hypothese" in msg.lower() or "family" in msg.lower()


def test_trend_pullback_exit_impact_carries_boundary_proximity_evidence():
    rows = _build_trend_pullback_exit_impact(
        {
            "candidates": [
                {
                    "asset": "TEST",
                    "interval": "1d",
                    "decision": "promoted_to_validation",
                    "sample_diagnostics_summary": {"best_sample_index": 0},
                    "sample_diagnostics": [
                        {
                            "trend_pullback_exit_reason_summary": {
                                "exit_reason_counts": {
                                    "trend_break": 1,
                                    "window_end": 1,
                                },
                                "exit_reason_pnl_summary": {
                                    "trend_break": {
                                        "total_pnl": -0.05,
                                        "avg_pnl": -0.05,
                                        "largest_loss": -0.05,
                                    },
                                    "window_end": {
                                        "total_pnl": 0.01,
                                        "avg_pnl": 0.01,
                                    },
                                },
                                "signal_change_unknown_subcategory_pnl_summary": {
                                    "signal_change_ambiguous_transition": {
                                        "total_pnl": -0.02,
                                        "avg_pnl": -0.02,
                                    },
                                },
                                "realized_pnl_impact": {
                                    "by_exit_reason": {
                                        "trend_break": {
                                            "trade_count": 1,
                                            "total_pnl": -0.05,
                                            "avg_pnl": -0.05,
                                            "largest_loss": -0.05,
                                        },
                                        "window_end": {
                                            "trade_count": 1,
                                            "total_pnl": 0.01,
                                            "avg_pnl": 0.01,
                                        },
                                    },
                                    "by_unknown_subcategory": {
                                        "signal_change_ambiguous_transition": {
                                            "trade_count": 1,
                                            "total_pnl": -0.02,
                                            "avg_pnl": -0.02,
                                        },
                                    },
                                    "by_boundary_proximity_bucket": {
                                        "near_window_end_1_bar": {
                                            "trade_count": 1,
                                            "total_pnl": -0.05,
                                        },
                                        "window_end": {
                                            "trade_count": 1,
                                            "total_pnl": 0.01,
                                        },
                                    },
                                    "by_asset": {
                                        "TEST": {
                                            "trade_count": 2,
                                            "total_pnl": -0.04,
                                        },
                                    },
                                    "by_fold_index": {
                                        "0": {
                                            "trade_count": 2,
                                            "total_pnl": -0.04,
                                        },
                                    },
                                },
                                "boundary_proximity_summary": {
                                    "bucket_counts": {
                                        "window_end": 1,
                                        "near_window_end_1_bar": 1,
                                    },
                                    "by_exit_reason": {
                                        "trend_break": {
                                            "bucket_counts": {
                                                "near_window_end_1_bar": 1,
                                            },
                                        },
                                        "window_end": {
                                            "bucket_counts": {"window_end": 1},
                                        },
                                    },
                                    "by_unknown_subcategory": {},
                                    "by_asset": {
                                        "TEST": {
                                            "bucket_counts": {
                                                "window_end": 1,
                                                "near_window_end_1_bar": 1,
                                            },
                                        },
                                    },
                                },
                            },
                            "trend_break_invalidation_summary": {
                                "avg_mae": 0.11,
                                "avg_mfe": 0.02,
                            },
                            "trend_break_invalidation_simulation_summary": {
                                "avoided_loss": 0.99,
                                "sacrificed_profit": 0.88,
                                "net_pnl_delta": 0.11,
                            },
                        },
                    ],
                },
            ],
        }
    )

    assert rows[0]["boundary_proximity_bucket_counts"] == {
        "near_window_end_1_bar": 1,
        "window_end": 1,
    }
    assert rows[0]["boundary_proximity_by_exit_reason"]["trend_break"][
        "bucket_counts"
    ] == {"near_window_end_1_bar": 1}
    assert rows[0]["trend_break_total_pnl"] == -0.05
    assert rows[0]["trend_break_avg_mae"] == 0.11
    assert rows[0]["exit_reason_realized_pnl_impact"]["trend_break"][
        "total_pnl"
    ] == -0.05
    assert rows[0]["unknown_subtype_realized_pnl_impact"][
        "signal_change_ambiguous_transition"
    ]["total_pnl"] == -0.02
    assert rows[0]["boundary_bucket_realized_pnl_impact"][
        "near_window_end_1_bar"
    ]["total_pnl"] == -0.05
    assert rows[0]["asset_realized_pnl_impact"]["TEST"]["total_pnl"] == -0.04
    assert rows[0]["fold_realized_pnl_impact"]["0"]["trade_count"] == 2

    markdown = render_markdown(
        {
            "run_id": "run-boundary",
            "generated_at_utc": "2026-06-01T08:30:00+00:00",
            "preset": "trend_equities_4h_baseline",
            "verdict": VERDICT_PROMOTED,
            "summary": {
                "raw": 1,
                "screened": 1,
                "validated": 1,
                "rejected": 0,
                "promoted": 1,
            },
            "candidates": [],
            "top_rejection_reasons": [],
            "top_rejection_reasons_by_layer": {
                "screening_layer": [],
                "promotion_layer": [],
            },
            "per_candidate_diagnostics": [],
            "join_stats": {},
            "red_flags": [],
            "trend_pullback_exit_impact": rows,
            "regime_diagnostics": {},
            "statistical_diagnostics": {},
            "next_experiment": "Review boundary diagnostics.",
        }
    )
    assert "Boundary buckets" in markdown
    assert "near_window_end_1_bar=1" in markdown
    assert "Trend-break total PnL" in markdown
    assert "trend_break=-5.00%" in markdown
    assert "signal_change_ambiguous_transition=-2.00%" in markdown


def test_trend_pullback_exit_quality_renders_advisory_sections():
    rows = _build_trend_pullback_exit_quality(
        {
            "candidates": [
                {
                    "asset": "TEST",
                    "interval": "1d",
                    "decision": "promoted_to_validation",
                    "sample_diagnostics_summary": {
                        "best_sample_index": 0,
                        "best_sample_exit_quality_audit": {
                            "advisory_only": True,
                            "selected_best_sample_index": 0,
                            "performance_best_sample_index": 0,
                            "exit_quality_best_sample_index": 1,
                            "exit_quality_disagreement": True,
                            "selected_sample_health_score": -0.6,
                            "advisory_message": (
                                "Selected performance-best sample differs from "
                                "advisory exit-quality-best sample."
                            ),
                        },
                    },
                    "sample_diagnostics": [
                        {
                            "trend_pullback_exit_reason_summary": {
                                "exit_reason_semantics": {
                                    "pullback_resolved_and_trend_break": {
                                        "exit_semantic_class": (
                                            "ambiguous_late_or_choppy_exit"
                                        ),
                                        "exit_semantic_warning": (
                                            "not automatically healthy"
                                        ),
                                    },
                                },
                                "exit_health_summary": {
                                    "overall": {
                                        "health_class_counts": {
                                            "healthy_exit": 1,
                                            "late_or_choppy_exit": 1,
                                            "risk_exit": 1,
                                        },
                                        "by_health_class": {
                                            "risk_exit": {"trade_share": 0.33},
                                            "unknown_exit": {"trade_share": 0.0},
                                            "boundary_exit": {"trade_share": 0.0},
                                            "late_or_choppy_exit": {
                                                "trade_share": 0.33,
                                            },
                                        },
                                    },
                                    "by_asset": {
                                        "TEST": {
                                            "overall": {
                                                "trade_count": 3,
                                                "total_pnl": -0.04,
                                            },
                                        },
                                    },
                                    "by_exit_reason": {
                                        "pullback_resolved_and_trend_break": {
                                            "exit_health_class": (
                                                "late_or_choppy_exit"
                                            ),
                                        },
                                    },
                                    "by_unknown_subcategory": {},
                                    "by_boundary_proximity_bucket": {
                                        "not_near_window_end": {
                                            "overall": {"trade_count": 3},
                                        },
                                    },
                                },
                                "realized_pnl_impact": {
                                    "by_exit_reason": {
                                        "trend_break": {"total_pnl": -0.05},
                                        "pullback_resolved_and_trend_break": {
                                            "total_pnl": -0.01,
                                        },
                                    },
                                    "by_unknown_subcategory": {},
                                    "by_boundary_proximity_bucket": {
                                        "not_near_window_end": {
                                            "total_pnl": -0.04,
                                        },
                                    },
                                },
                                "boundary_proximity_summary": {
                                    "bucket_counts": {
                                        "not_near_window_end": 3,
                                    },
                                },
                            },
                        },
                    ],
                },
            ],
        }
    )

    assert rows[0]["advisory_only"] is True
    assert rows[0]["exit_health_counts"]["late_or_choppy_exit"] == 1
    assert rows[0]["exit_health_by_reason"][
        "pullback_resolved_and_trend_break"
    ]["exit_health_class"] == "late_or_choppy_exit"
    assert rows[0]["best_sample_exit_quality_audit"][
        "exit_quality_disagreement"
    ] is True

    markdown = render_markdown(
        {
            "run_id": "run-quality",
            "generated_at_utc": "2026-06-01T09:30:00+00:00",
            "preset": "trend_equities_4h_baseline",
            "verdict": VERDICT_PROMOTED,
            "summary": {
                "raw": 1,
                "screened": 1,
                "validated": 1,
                "rejected": 0,
                "promoted": 1,
            },
            "candidates": [],
            "top_rejection_reasons": [],
            "top_rejection_reasons_by_layer": {
                "screening_layer": [],
                "promotion_layer": [],
            },
            "per_candidate_diagnostics": [],
            "join_stats": {},
            "red_flags": [],
            "trend_pullback_exit_quality": rows,
            "regime_diagnostics": {},
            "statistical_diagnostics": {},
            "next_experiment": "Review exit quality.",
        }
    )
    assert "Trend-pullback exit quality (advisory only)" in markdown
    assert "Health classes are diagnostic context only" in markdown
    assert "Boundary proximity is context, not reclassification" in markdown
    assert "realized PnL impact remains separate" in markdown
    assert "`pullback_resolved_and_trend_break` is treated as ambiguous" in markdown
    assert "Selected performance-best sample differs" in markdown


def test_trend_pullback_exit_quality_handles_missing_diagnostics_gracefully():
    assert _build_trend_pullback_exit_quality({"candidates": [{}]}) == []
    assert (
        _build_trend_pullback_exit_quality(
            {
                "candidates": [
                    {
                        "asset": "ZERO",
                        "sample_diagnostics_summary": {"best_sample_index": 0},
                        "sample_diagnostics": [
                            {"trend_pullback_exit_reason_summary": {}},
                        ],
                    }
                ],
            }
        )[0]["exit_health_counts"]
        == {}
    )

def test_candidate_shadow_readiness_report_fails_closed_without_paper_readiness():
    from research.report_agent import _candidate_shadow_readiness_report

    report = _candidate_shadow_readiness_report(
        None,
        [
            {
                "best_sample_exit_quality_audit": {
                    "exit_quality_disagreement": False,
                },
                "exit_health_counts": {
                    "risk_exit": 1,
                    "late_or_choppy_exit": 0,
                    "unknown_exit": 0,
                    "boundary_exit": 0,
                },
            }
        ],
    )

    assert report is not None
    assert report["readiness_status"] == "blocked"
    assert report["advisory_only"] is True
    assert report["shadow_runtime_enabled"] is False
    assert report["paper_runtime_enabled"] is False
    assert report["live_eligible"] is False
    assert "paper_readiness_missing" in report["blocking_reasons"]

    markdown = render_markdown(
        {
            "run_id": "run-shadow-readiness-missing",
            "generated_at_utc": "2026-06-01T12:00:00+00:00",
            "preset": "trend_equities_4h_baseline",
            "verdict": VERDICT_PROMOTED,
            "summary": {
                "raw": 1,
                "screened": 1,
                "validated": 1,
                "rejected": 0,
                "promoted": 1,
            },
            "candidates": [],
            "top_rejection_reasons": [],
            "top_rejection_reasons_by_layer": {
                "screening_layer": [],
                "promotion_layer": [],
            },
            "per_candidate_diagnostics": [],
            "join_stats": {},
            "red_flags": [],
            "regime_diagnostics": {},
            "statistical_diagnostics": {},
            "candidate_shadow_readiness_report": report,
            "next_experiment": "Review shadow readiness blockers.",
        }
    )

    assert "Candidate Shadow Readiness (advisory only, default-off)" in markdown
    assert "paper_readiness_missing" in markdown
    assert "this report does not authorize runtime activation" in markdown


def test_candidate_shadow_readiness_report_can_recommend_operator_review_default_off():
    from research.report_agent import _candidate_shadow_readiness_report

    paper_readiness = {
        "counts": {
            "ready_for_paper_promotion": 1,
            "blocked": 0,
            "insufficient_evidence": 0,
        },
        "entries": [
            {
                "candidate_id": "cand-1",
                "asset_type": "equity",
                "sleeve_id": None,
                "readiness_status": "ready_for_paper_promotion",
                "blocking_reasons": [],
                "warnings": [],
                "evidence": {},
            }
        ],
    }

    report = _candidate_shadow_readiness_report(
        paper_readiness,
        [
            {
                "best_sample_exit_quality_audit": {
                    "exit_quality_disagreement": False,
                },
                "exit_health_counts": {
                    "risk_exit": 0,
                    "late_or_choppy_exit": 0,
                    "unknown_exit": 0,
                    "boundary_exit": 0,
                },
            }
        ],
    )

    assert report is not None
    assert report["readiness_status"] == "ready_for_operator_shadow_review"
    assert report["eligible_for_operator_shadow_review"] is True
    assert report["paper_ready_candidate_count"] == 1
    assert report["blocking_reasons"] == []
    assert report["shadow_runtime_enabled"] is False
    assert report["paper_runtime_enabled"] is False
    assert report["live_eligible"] is False
    assert report["operator_go_required"] is True
    assert report["candidates"][0]["eligible_for_operator_shadow_review"] is True

