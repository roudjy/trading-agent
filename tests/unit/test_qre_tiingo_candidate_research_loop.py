from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from research import qre_tiingo_candidate_research_loop as loop

FAMILIES = (
    "cross_sectional_momentum",
    "risk_on_risk_off_regime",
    "defensive_rotation",
    "volatility_compression_breakout",
    "mean_reversion_after_extreme_dispersion",
)
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "XLK", "XLF", "XLE", "XLV")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _lifecycle_record(family: str, index: int = 0, *, decision: str = "admitted") -> dict:
    status = (
        "admissible_for_research_candidate_formulation"
        if decision == "admitted"
        else "rejected_before_candidate_formulation"
    )
    return {
        "hypothesis_seed_id": f"seed_tiingo_{family}_{index}",
        "source_hypothesis_id": f"tiingo_hyp_{family}_{index}",
        "source_snapshot_id": "qdsnap_test",
        "feature_family": family,
        "status": status,
        "decision": decision,
        "source_hypothesis_digest": {"digest": f"sha256:{family}{index}", "keys": ["feature_family"]},
        "required_candidate_spec_fields": [
            "candidate_id",
            "parent_hypothesis_seed_id",
            "source_snapshot_id",
            "feature_family",
            "signal_definition",
            "selection_rule",
            "rebalance_rule",
            "holding_period",
            "benchmark",
            "null_control_requirement",
            "split_adjustment_requirement",
            "screening_only",
            "trading_authority",
        ],
        "allowed_candidate_families": [family],
        "forbidden_authorities": [
            "candidate_promotion",
            "strategy_registration",
            "validation",
            "paper",
            "shadow",
            "live",
            "trading",
            "broker",
            "orders",
        ],
        "next_action": "materialize_research_candidate_later",
        "trading_authority": False,
        "creates_candidates": False,
        "runs_screening": False,
    }


def _lifecycle_payload(records: list[dict] | None = None) -> dict:
    records = records if records is not None else [_lifecycle_record(family, index) for index, family in enumerate(FAMILIES)]
    return {
        "report_kind": "qre_tiingo_hypothesis_lifecycle",
        "schema_version": 1,
        "source_report_kind": "qre_tiingo_hypothesis_generator_e2e",
        "source_snapshot_id": "qdsnap_test",
        "summary": {
            "lifecycle_verdict": "pass_research_only_admission_boundary",
            "hypotheses_seen": len(records),
            "hypotheses_admitted": sum(1 for row in records if row["decision"] == "admitted"),
            "hypotheses_rejected": sum(1 for row in records if row["decision"] == "rejected"),
            "hypotheses_blocked": sum(1 for row in records if row["decision"] == "blocked"),
            "daily_digest_ready": True,
        },
        "hypothesis_lifecycle": records,
        "safety": {
            "trading_authority": False,
            "creates_candidates": False,
            "runs_screening": False,
            "promotes_candidates": False,
            "registers_strategy": False,
            "validation_authority": False,
            "paper_authority": False,
            "shadow_authority": False,
            "live_authority": False,
        },
        "daily_digest_input": {
            "counts": {
                "generated": len(records),
                "admitted": sum(1 for row in records if row["decision"] == "admitted"),
                "rejected": sum(1 for row in records if row["decision"] == "rejected"),
                "blocked": sum(1 for row in records if row["decision"] == "blocked"),
            }
        },
    }


def _upstream_payload() -> dict:
    return {
        "report_kind": "qre_tiingo_hypothesis_generator_e2e",
        "source_snapshot_id": "qdsnap_test",
        "summary": {"final_verdict": "pass_data_driven_hypothesis_generation"},
        "safety": {"trading_authority": False},
    }


def _write_inputs(root: Path, *, lifecycle_payload: dict | None = None) -> tuple[Path, Path, Path]:
    lifecycle_path = root / "lifecycle" / "latest.json"
    upstream_path = root / "upstream" / "latest.json"
    bars_path = root / "bars.csv"
    _write_json(lifecycle_path, lifecycle_payload or _lifecycle_payload())
    _write_json(upstream_path, _upstream_payload())
    _write_bars(bars_path)
    return lifecycle_path, upstream_path, bars_path


def _write_bars(path: Path, *, days: int = 360, split: bool = False, malformed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if malformed:
        path.write_text("date,symbol,close\n2021-01-01,SPY,100\n", encoding="utf-8")
        return
    drifts = {
        "SPY": 0.00055,
        "QQQ": 0.00075,
        "IWM": 0.00035,
        "DIA": 0.00045,
        "TLT": 0.00010,
        "GLD": 0.00015,
        "XLK": 0.00085,
        "XLF": 0.00025,
        "XLE": -0.00005,
        "XLV": 0.00020,
    }
    lines = ["date,symbol,open,high,low,close,volume"]
    start = date(2021, 1, 1)
    for idx in range(days):
        current = start + timedelta(days=idx)
        for symbol in SYMBOLS:
            price = 100.0 * ((1.0 + drifts[symbol]) ** idx)
            if split and symbol == "XLK" and idx >= 300:
                price *= 0.5
            lines.append(
                f"{current.isoformat()},{symbol},{price:.6f},{price * 1.01:.6f},{price * 0.99:.6f},{price:.6f},1000000"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(root: Path, **kwargs) -> dict:
    lifecycle_path, upstream_path, bars_path = _write_inputs(root)
    params = {
        "repo_root": root,
        "lifecycle_input": lifecycle_path,
        "upstream_e2e_input": upstream_path,
        "bars_input": bars_path,
        "prior_feedback_input": root / "missing_prior.json",
        "output_dir": root / "logs" / "qre_tiingo_candidate_research_loop",
        "max_candidates": 5,
        "null_iterations": 32,
        "seed": 1729,
    }
    params.update(kwargs)
    return loop.build_report(**params)


def test_missing_malformed_unexpected_and_unsafe_lifecycle_fail_closed(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream.json"
    bars = tmp_path / "bars.csv"
    _write_json(upstream, _upstream_payload())
    _write_bars(bars)

    missing = loop.build_report(repo_root=tmp_path, lifecycle_input=tmp_path / "missing.json", upstream_e2e_input=upstream, bars_input=bars)
    assert missing["summary"]["loop_verdict"] == "blocked_missing_or_unsafe_input"
    assert "missing_lifecycle_artifact" in missing["blocked_reasons"]

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{not-json", encoding="utf-8")
    malformed = loop.build_report(repo_root=tmp_path, lifecycle_input=malformed_path, upstream_e2e_input=upstream, bars_input=bars)
    assert "malformed_lifecycle_artifact" in malformed["blocked_reasons"]

    bad_kind_path = tmp_path / "bad_kind.json"
    payload = _lifecycle_payload()
    payload["report_kind"] = "wrong"
    _write_json(bad_kind_path, payload)
    bad_kind = loop.build_report(repo_root=tmp_path, lifecycle_input=bad_kind_path, upstream_e2e_input=upstream, bars_input=bars)
    assert "unexpected_lifecycle_report_kind" in bad_kind["blocked_reasons"]

    unsafe_path = tmp_path / "unsafe.json"
    payload = _lifecycle_payload()
    payload["safety"]["trading_authority"] = True
    _write_json(unsafe_path, payload)
    unsafe = loop.build_report(repo_root=tmp_path, lifecycle_input=unsafe_path, upstream_e2e_input=upstream, bars_input=bars)
    assert "unsafe_lifecycle_authority:trading_authority" in unsafe["blocked_reasons"]


def test_lifecycle_verdict_not_pass_and_no_admitted_records_fail_closed(tmp_path: Path) -> None:
    lifecycle_path, upstream_path, bars_path = _write_inputs(tmp_path)
    payload = _lifecycle_payload()
    payload["summary"]["lifecycle_verdict"] = "blocked"
    _write_json(lifecycle_path, payload)
    verdict = loop.build_report(repo_root=tmp_path, lifecycle_input=lifecycle_path, upstream_e2e_input=upstream_path, bars_input=bars_path)
    assert "lifecycle_verdict_not_pass" in verdict["blocked_reasons"]

    payload = _lifecycle_payload([_lifecycle_record("cross_sectional_momentum", decision="rejected")])
    _write_json(lifecycle_path, payload)
    no_admitted = loop.build_report(repo_root=tmp_path, lifecycle_input=lifecycle_path, upstream_e2e_input=upstream_path, bars_input=bars_path)
    assert no_admitted["summary"]["loop_verdict"] == "blocked_no_admitted_hypotheses"


def test_admitted_lifecycle_records_become_deterministic_input_contracts(tmp_path: Path) -> None:
    rejected = _lifecycle_record("risk_on_risk_off_regime", 8, decision="rejected")
    payload = _lifecycle_payload([_lifecycle_record("cross_sectional_momentum", 1), rejected])
    contracts, skipped = loop.build_input_contracts(payload)
    contracts_again, _ = loop.build_input_contracts(payload)

    assert len(contracts) == 1
    assert len(skipped) == 1
    assert contracts == contracts_again
    assert contracts[0]["contract_id"].startswith("contract_tiingo_")
    assert contracts[0]["contract_digest"].startswith("sha256:")
    assert contracts[0]["trading_authority"] is False
    assert contracts[0]["research_only"] is True
    assert contracts[0]["screening_only"] is True


def test_all_known_candidate_family_templates_materialize_with_required_safety(tmp_path: Path) -> None:
    lifecycle_path, upstream_path, bars_path = _write_inputs(tmp_path)
    report = loop.build_report(
        repo_root=tmp_path,
        lifecycle_input=lifecycle_path,
        upstream_e2e_input=upstream_path,
        bars_input=bars_path,
        prior_feedback_input=tmp_path / "missing.json",
    )

    families = {candidate["feature_family"] for candidate in report["candidate_specs"]}
    assert families == set(FAMILIES)
    assert report["summary"]["candidates_materialized"] == 5
    for candidate in report["candidate_specs"]:
        assert candidate["candidate_id"].startswith("cand_tiingo_")
        assert candidate["candidate_digest"].startswith("sha256:")
        assert candidate["screening_protocol"] == "tiingo_research_candidate_screening_v1"
        assert candidate["null_control_requirement"] == "required"
        assert candidate["split_adjustment_requirement"] == "required"
        assert candidate["screening_only"] is True
        assert candidate["research_only"] is True
        assert candidate["not_trade_signal"] is True
        assert candidate["trading_authority"] is False
        assert candidate["creates_orders"] is False
        assert "orders" not in candidate
        assert "positions" not in candidate
        assert "trading_signals" not in candidate


def test_unknown_candidate_family_is_blocked(tmp_path: Path) -> None:
    payload = _lifecycle_payload([_lifecycle_record("unknown_family", 1)])
    lifecycle_path, upstream_path, bars_path = _write_inputs(tmp_path, lifecycle_payload=payload)
    report = loop.build_report(
        repo_root=tmp_path,
        lifecycle_input=lifecycle_path,
        upstream_e2e_input=upstream_path,
        bars_input=bars_path,
        prior_feedback_input=tmp_path / "missing.json",
    )

    assert report["summary"]["loop_verdict"] == "blocked_no_candidate_specs"
    assert "blocked_unknown_candidate_family" in report["blocked_reasons"]


def test_candidate_ids_are_deterministic(tmp_path: Path) -> None:
    report = _run(tmp_path / "a")
    report_again = _run(tmp_path / "a")
    assert [row["candidate_id"] for row in report["candidate_specs"]] == [
        row["candidate_id"] for row in report_again["candidate_specs"]
    ]


def test_missing_and_malformed_bars_block_screening(tmp_path: Path) -> None:
    lifecycle_path, upstream_path, bars_path = _write_inputs(tmp_path)
    missing = loop.build_report(
        repo_root=tmp_path,
        lifecycle_input=lifecycle_path,
        upstream_e2e_input=upstream_path,
        bars_input=tmp_path / "missing_bars.csv",
        prior_feedback_input=tmp_path / "missing.json",
    )
    assert missing["summary"]["loop_verdict"] == "blocked_no_screening_data"
    assert "missing_bars_input" in missing["blocked_reasons"]

    _write_bars(bars_path, malformed=True)
    malformed = loop.build_report(
        repo_root=tmp_path,
        lifecycle_input=lifecycle_path,
        upstream_e2e_input=upstream_path,
        bars_input=bars_path,
        prior_feedback_input=tmp_path / "missing.json",
    )
    assert malformed["summary"]["loop_verdict"] == "blocked_no_screening_data"
    assert any(str(reason).startswith("malformed_bars_input") for reason in malformed["blocked_reasons"])


def test_insufficient_observations_yield_insufficient_evidence(tmp_path: Path) -> None:
    lifecycle_path, upstream_path, bars_path = _write_inputs(tmp_path)
    _write_bars(bars_path, days=120)
    report = loop.build_report(
        repo_root=tmp_path,
        lifecycle_input=lifecycle_path,
        upstream_e2e_input=upstream_path,
        bars_input=bars_path,
        prior_feedback_input=tmp_path / "missing.json",
    )
    assert report["summary"]["insufficient_evidence"] >= 1
    assert all(result["decision"] in loop.ALLOWED_SCREENING_DECISIONS for result in report["screening_results"])


def test_screening_computes_finite_metrics_benchmark_and_seeded_null_controls(tmp_path: Path) -> None:
    report = _run(tmp_path)
    results = report["screening_results"]

    assert results
    for result in results:
        assert result["screening_only"] is True
        assert result["research_only"] is True
        assert result["trading_authority"] is False
        assert result["validation_authority"] is False
        assert result["promotes_candidates"] is False
        assert result["decision"] in loop.ALLOWED_SCREENING_DECISIONS
        assert isinstance(result["benchmark_total_return"], float)
        assert result["null_control"]["null_iterations"] == 32
        assert result["null_control"]["seed"] == 1729
        assert "equal_weight_benchmark" in result["null_control"]
        assert "shuffled_selection_null" in result["null_control"]
        for key in ("candidate_total_return", "benchmark_total_return", "excess_return", "candidate_sharpe_like"):
            assert isinstance(result[key], float)


def test_null_controls_are_deterministic_and_change_with_seed(tmp_path: Path) -> None:
    report = _run(tmp_path / "same_a", seed=1729)
    same = _run(tmp_path / "same_a", seed=1729)
    different = _run(tmp_path / "different", seed=1730)

    nulls = [row["null_control"] for row in report["screening_results"]]
    same_nulls = [row["null_control"] for row in same["screening_results"]]
    different_nulls = [row["null_control"] for row in different["screening_results"]]
    assert nulls == same_nulls
    assert nulls != different_nulls


def test_split_like_discontinuity_is_adjusted_before_screening(tmp_path: Path) -> None:
    lifecycle_path, upstream_path, bars_path = _write_inputs(tmp_path)
    _write_bars(bars_path, split=True)
    bars, reasons = loop.load_bars(bars_path)

    assert reasons == []
    assert bars is not None
    xlk = {row["date"]: row for row in bars if row["symbol"] == "XLK"}
    event_return = xlk["2021-10-28"]["adjusted_close_for_research"] / xlk["2021-10-27"]["adjusted_close_for_research"] - 1.0
    assert event_return > -0.1
    report = loop.build_report(
        repo_root=tmp_path,
        lifecycle_input=lifecycle_path,
        upstream_e2e_input=upstream_path,
        bars_input=bars_path,
        prior_feedback_input=tmp_path / "missing.json",
    )
    assert report["screening_results"]


def test_feedback_mapping_and_ids_are_deterministic() -> None:
    expected = {
        "screening_pass": ("retain_for_more_screening", "rematerialize_same_spec", "retain_hypothesis"),
        "null_not_beaten": ("modify_candidate_later", "materialize_modified_spec", "modify_hypothesis_parameters_later"),
        "screening_fail": ("reject_candidate_for_now", "do_not_rematerialize_same_spec", "reject_hypothesis_for_now"),
        "insufficient_evidence": ("insufficient_evidence", "collect_more_data", "needs_more_evidence"),
        "blocked_unsafe_input": ("block_candidate", "repair_input_contract", "block_hypothesis"),
    }
    for decision, mapped in expected.items():
        result = {
            "candidate_id": f"cand_{decision}",
            "parent_contract_id": f"contract_{decision}",
            "parent_hypothesis_seed_id": "seed",
            "source_snapshot_id": "qdsnap_test",
            "decision": decision,
        }
        feedback = loop.feedback_from_screening(result)
        feedback_again = loop.feedback_from_screening(result)
        assert feedback == feedback_again
        assert feedback["feedback_id"].startswith("fb_tiingo_")
        assert feedback["feedback_decision"] == mapped[0]
        assert feedback["next_candidate_action"] == mapped[1]
        assert feedback["next_hypothesis_action"] == mapped[2]
        assert feedback["consumable_by_next_run"] is True
        assert feedback["trading_authority"] is False


def test_no_prior_feedback_reports_not_consumed(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report["summary"]["feedback_consumed"] is False
    assert report["summary"]["feedback_applied_count"] == 0


def test_prior_retain_feedback_rematerializes_same_candidate(tmp_path: Path) -> None:
    first = _run(tmp_path / "first")
    prior = tmp_path / "prior.json"
    _write_json(prior, {"feedback_records": [first["feedback_records"][0] | {"feedback_decision": "retain_for_more_screening"}]})
    second = _run(tmp_path / "second", prior_feedback_input=prior)

    assert second["summary"]["feedback_consumed"] is True
    assert second["summary"]["feedback_applied_count"] == 1
    assert second["summary"]["retained_by_prior_feedback"] == 1
    assert first["candidate_specs"][0]["candidate_id"] in {row["candidate_id"] for row in second["candidate_specs"]}


def test_prior_reject_modify_insufficient_and_block_feedback_change_next_run(tmp_path: Path) -> None:
    first = _run(tmp_path / "first")
    records = []
    decisions = [
        "reject_candidate_for_now",
        "modify_candidate_later",
        "insufficient_evidence",
        "block_candidate",
    ]
    for feedback, decision in zip(first["feedback_records"][:4], decisions, strict=True):
        changed = dict(feedback)
        changed["feedback_decision"] = decision
        records.append(changed)
    prior = tmp_path / "prior.json"
    _write_json(prior, {"feedback_records": records})

    second = _run(tmp_path / "second", prior_feedback_input=prior)

    assert second["summary"]["feedback_consumed"] is True
    assert second["summary"]["feedback_applied_count"] == 4
    assert second["summary"]["suppressed_by_prior_feedback"] == 1
    assert second["summary"]["modified_by_prior_feedback"] == 1
    assert "suppressed_by_prior_feedback" in second["blocked_reasons"]
    assert "blocked_by_prior_feedback" in second["blocked_reasons"]
    assert any(candidate["prior_feedback_variant"] == "modified_by_prior_feedback" for candidate in second["candidate_specs"])
    assert any(result["decision"] == "insufficient_evidence" for result in second["screening_results"])
    assert [row["candidate_id"] for row in first["candidate_specs"]] != [
        row["candidate_id"] for row in second["candidate_specs"]
    ]


def test_write_outputs_and_default_mode_write_nothing(tmp_path: Path) -> None:
    report = _run(tmp_path)
    output_dir = tmp_path / "logs" / "qre_tiingo_candidate_research_loop"
    assert not output_dir.exists()

    paths = loop.write_outputs(report, repo_root=tmp_path, output_dir=output_dir)

    assert set(paths) == {
        "latest",
        "input_contracts",
        "candidate_specs",
        "screening_results",
        "feedback_records",
        "operator_summary",
    }
    assert (output_dir / "latest.json").is_file()
    assert (output_dir / "input_contracts.jsonl").is_file()
    assert (output_dir / "candidate_specs.jsonl").is_file()
    assert (output_dir / "screening_results.jsonl").is_file()
    assert (output_dir / "feedback_records.jsonl").is_file()
    assert (output_dir / "operator_summary.md").is_file()
    assert all(path.startswith("logs/qre_tiingo_candidate_research_loop/") for path in paths.values())


def test_write_outputs_rejects_other_output_dir(tmp_path: Path) -> None:
    report = _run(tmp_path)
    try:
        loop.write_outputs(report, repo_root=tmp_path, output_dir=tmp_path / "other")
    except ValueError as exc:
        assert "output_dir_must_be_logs_qre_tiingo_candidate_research_loop" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected output dir rejection")


def test_protected_research_outputs_are_not_mutated(tmp_path: Path) -> None:
    research_latest = Path("research/research_latest.json")
    strategy_matrix = Path("research/strategy_matrix.csv")
    before_latest = research_latest.read_bytes()
    before_matrix = strategy_matrix.read_bytes()

    _run(tmp_path)

    assert research_latest.read_bytes() == before_latest
    assert strategy_matrix.read_bytes() == before_matrix


def test_all_safety_flags_daily_digest_and_operator_summary_are_research_only(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report["safety"] == loop.SAFETY
    assert report["daily_digest_input"]["counts"]["input_contracts_admitted"] == 5
    assert report["daily_digest_input"]["authority_summary"] == loop.SAFETY
    summary = loop.render_operator_summary(report)
    assert "# Tiingo Candidate Research Loop" in summary
    assert "No orders were created" in summary
    assert "No broker/risk authority exists" in summary
    forbidden_active_terms = ("validation_ready", "paper_ready", "shadow_ready", "live_ready", "trade_ready")
    assert not any(term in json.dumps(report) for term in forbidden_active_terms)

