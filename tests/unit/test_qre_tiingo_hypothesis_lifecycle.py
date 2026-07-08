from __future__ import annotations

import json
from pathlib import Path

from research import qre_tiingo_hypothesis_lifecycle as lifecycle

UPSTREAM_PATH = Path("logs/qre_tiingo_hypothesis_generator_e2e/latest.json")
SNAPSHOT_ID = "qdsnap_2b1258c6f592fa08"


def _hypothesis(index: int, *, family: str = "cross_sectional_momentum") -> dict:
    identity = f"tiingo_hyp_{family}_{index}"
    return {
        "hypothesis_id": identity,
        "content_identity": identity,
        "source_id": "tiingo_eod_equities_free",
        "source_snapshot_id": SNAPSHOT_ID,
        "generated_from_data_profile": True,
        "feature_family": family,
        "instruments_used": ["SPY", "QQQ"],
        "lookback_window": 60,
        "signal_definition": "Rank ETFs by 60d return.",
        "expected_direction": "Higher ranked ETFs persist.",
        "falsification_condition": "Null control matches identity.",
        "feature_refs": ["momentum_rank_60d"],
        "data_profile_digest": "profile_digest",
        "screening_only": True,
        "not_trade_signal": True,
        "trading_authority": False,
        "confidence": 0.7,
        "blocked_reasons": [],
    }


def _mode(
    name: str,
    *,
    hypotheses: list[dict] | None = None,
    valid_profile: bool = True,
    insufficient_history: bool = False,
    insufficient_cross_section: bool = False,
    corporate_events: bool = False,
    adjusted: bool = True,
) -> dict:
    hypotheses = list(hypotheses or [])
    profile = {
        "source_id": "tiingo_eod_equities_free",
        "source_snapshot_id": SNAPSHOT_ID,
        "data_profile_digest": "profile_digest",
        "universe": ["SPY", "QQQ"],
        "insufficient_history": insufficient_history,
        "insufficient_cross_section": insufficient_cross_section,
        "corporate_action_events": [{"symbol": "XLK"}] if corporate_events else [],
        "adjusted_price_continuity_applied": adjusted,
    }
    blocked = []
    if insufficient_history:
        blocked.append("insufficient_history")
    if insufficient_cross_section:
        blocked.append("insufficient_cross_section")
    return {
        "mode": name,
        "data_profile_valid": valid_profile,
        "blocked_reasons": blocked,
        "data_profile": profile,
        "hypotheses": hypotheses,
        "hypotheses_count": len(hypotheses),
        "content_identities": [row["content_identity"] for row in hypotheses],
        "safety": {
            "network_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "validation_executed": False,
            "candidate_promotion_allowed": False,
            "strategy_registration_allowed": False,
            "execution_performed": False,
            "paper_shadow_live_allowed": False,
            "trading_authority": False,
        },
    }


def _valid_payload() -> dict:
    real = [_hypothesis(1), _hypothesis(2, family="risk_on_risk_off_regime")]
    shuffled = [
        _hypothesis(1, family="defensive_rotation"),
        _hypothesis(2, family="volatility_compression_breakout"),
    ]
    truncated = _mode("truncated", insufficient_history=True)
    return {
        "report_kind": "qre_tiingo_hypothesis_generator_e2e",
        "schema_version": "1.0",
        "source_id": "tiingo_eod_equities_free",
        "source_snapshot_id": SNAPSHOT_ID,
        "source_tier": "SOURCE_SCREENING_ELIGIBLE",
        "timeframe": "1d",
        "modes": {
            "real": _mode("real", hypotheses=real),
            "shuffled_returns": _mode("shuffled_returns", hypotheses=shuffled),
            "truncated": truncated,
        },
        "summary": {
            "real_data_hypotheses_count": len(real),
            "shuffled_control_hypotheses_count": len(shuffled),
            "truncated_control_hypotheses_count": 0,
            "real_content_identities": [row["content_identity"] for row in real],
            "shuffled_content_identities": [row["content_identity"] for row in shuffled],
            "truncated_content_identities": [],
            "data_dependency_proven": True,
            "data_dependency_blockers": [],
            "final_verdict": "pass_data_driven_hypothesis_generation",
        },
        "safety": {
            "network_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "validation_executed": False,
            "candidate_promotion_allowed": False,
            "strategy_registration_allowed": False,
            "execution_performed": False,
            "paper_shadow_live_allowed": False,
            "trading_authority": False,
        },
    }


def _write_payload(root: Path, payload: dict) -> Path:
    path = root / UPSTREAM_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _build(root: Path) -> dict:
    return lifecycle.build_lifecycle_report(repo_root=root, input_path=UPSTREAM_PATH)


def _assert_blocked(root: Path, reason: str) -> None:
    report = _build(root)
    assert report["summary"]["lifecycle_verdict"] == "blocked"
    assert reason in report["blocked_reasons"]
    assert report["trading_authority"] is False
    assert report["safety"]["creates_candidates"] is False
    assert report["safety"]["runs_screening"] is False


def test_missing_upstream_report_fails_closed(tmp_path: Path) -> None:
    _assert_blocked(tmp_path, "missing_upstream_report")


def test_malformed_upstream_report_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / UPSTREAM_PATH
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    _assert_blocked(tmp_path, "malformed_upstream_report")


def test_unexpected_report_kind_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["report_kind"] = "wrong"
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "unexpected_upstream_report_kind")


def test_unsafe_trading_authority_true_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["safety"]["trading_authority"] = True
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "unsafe_trading_authority")


def test_final_verdict_not_pass_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["summary"]["final_verdict"] = "fail_static_or_template_driven"
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "upstream_final_verdict_not_pass")


def test_data_dependency_false_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["summary"]["data_dependency_proven"] = False
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "data_dependency_not_proven")


def test_missing_source_snapshot_id_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload.pop("source_snapshot_id")
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "missing_source_snapshot_id")


def test_missing_real_mode_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"].pop("real")
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "missing_real_mode")


def test_missing_shuffled_mode_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"].pop("shuffled_returns")
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "missing_shuffled_mode")


def test_missing_truncated_mode_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"].pop("truncated")
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "missing_truncated_mode")


def test_invalid_real_data_profile_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"]["real"]["data_profile_valid"] = False
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "invalid_real_data_profile")


def test_missing_real_hypotheses_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"]["real"]["hypotheses"] = []
    payload["modes"]["real"]["hypotheses_count"] = 0
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "missing_real_hypotheses")


def test_missing_shuffled_hypotheses_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"]["shuffled_returns"]["hypotheses"] = []
    payload["modes"]["shuffled_returns"]["hypotheses_count"] = 0
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "missing_shuffled_hypotheses")


def test_real_shuffled_identity_collision_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    real_ids = payload["modes"]["real"]["content_identities"]
    payload["modes"]["shuffled_returns"]["content_identities"] = list(real_ids)
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "real_shuffled_identity_not_different")


def test_truncated_control_not_blocked_fails_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"]["truncated"] = _mode("truncated", hypotheses=[_hypothesis(8)])
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "truncated_control_not_blocked")


def test_split_events_without_adjustment_fail_closed(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["modes"]["real"]["data_profile"]["corporate_action_events"] = [{"symbol": "XLK"}]
    payload["modes"]["real"]["data_profile"]["adjusted_price_continuity_applied"] = False
    _write_payload(tmp_path, payload)
    _assert_blocked(tmp_path, "split_adjustment_required_but_missing")


def test_valid_upstream_report_produces_lifecycle_records(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    report = _build(tmp_path)
    assert report["summary"]["lifecycle_verdict"] == "pass_research_only_admission_boundary"
    assert len(report["hypothesis_lifecycle"]) == 2
    assert report["summary"]["hypotheses_seen"] == 2


def test_valid_upstream_report_admits_hypotheses(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    report = _build(tmp_path)
    assert {row["decision"] for row in report["hypothesis_lifecycle"]} == {"admitted"}
    assert {row["status"] for row in report["hypothesis_lifecycle"]} == {
        "admissible_for_research_candidate_formulation"
    }


def test_deterministic_hypothesis_seed_id_values(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    first = _build(tmp_path)
    second = _build(tmp_path)
    assert [row["hypothesis_seed_id"] for row in first["hypothesis_lifecycle"]] == [
        row["hypothesis_seed_id"] for row in second["hypothesis_lifecycle"]
    ]


def test_deterministic_event_id_values(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    first = _build(tmp_path)
    second = _build(tmp_path)
    assert [row["event_id"] for row in first["events"]] == [row["event_id"] for row in second["events"]]


def test_default_mode_writes_nothing(tmp_path: Path, capsys) -> None:
    _write_payload(tmp_path, _valid_payload())
    status = lifecycle.main(["--repo-root", str(tmp_path)])
    parsed = json.loads(capsys.readouterr().out)
    assert status == 0
    assert parsed["report_kind"] == lifecycle.REPORT_KIND
    assert not (tmp_path / lifecycle.DEFAULT_OUTPUT_DIR / "latest.json").exists()


def test_write_writes_only_lifecycle_logs(tmp_path: Path, capsys) -> None:
    _write_payload(tmp_path, _valid_payload())
    lifecycle.main(["--repo-root", str(tmp_path), "--write"])
    capsys.readouterr()
    files = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())
    created = [path for path in files if path != UPSTREAM_PATH.as_posix()]
    assert created
    assert all(path.startswith("logs/qre_tiingo_hypothesis_lifecycle/") for path in created)
    assert "research/research_latest.json" not in files
    assert "research/strategy_matrix.csv" not in files


def test_write_writes_required_artifacts(tmp_path: Path, capsys) -> None:
    _write_payload(tmp_path, _valid_payload())
    lifecycle.main(["--repo-root", str(tmp_path), "--write"])
    capsys.readouterr()
    base = tmp_path / lifecycle.DEFAULT_OUTPUT_DIR
    assert (base / "latest.json").is_file()
    assert (base / "events.jsonl").is_file()
    assert (base / "operator_summary.md").is_file()


def test_events_jsonl_matches_latest_events(tmp_path: Path, capsys) -> None:
    _write_payload(tmp_path, _valid_payload())
    lifecycle.main(["--repo-root", str(tmp_path), "--write"])
    capsys.readouterr()
    base = tmp_path / lifecycle.DEFAULT_OUTPUT_DIR
    latest = json.loads((base / "latest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (base / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows == latest["events"]


def test_operator_updates_are_emitted_for_meaningful_events(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    admitted = _build(tmp_path)
    assert admitted["operator_updates"]
    assert {row["update_type"] for row in admitted["operator_updates"]} == {
        event["event_type"] for event in admitted["events"]
    }
    blocked = lifecycle.build_lifecycle_report(repo_root=tmp_path, input_path=Path("missing.json"))
    assert blocked["operator_updates"][0]["update_type"] == "hypothesis_blocked"


def test_daily_digest_input_contains_counts_and_authority_summary(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    report = _build(tmp_path)
    digest = report["daily_digest_input"]
    assert digest["counts"] == {"generated": 2, "admitted": 2, "rejected": 0, "blocked": 0}
    assert report["summary"]["daily_digest_ready"] is True
    assert all(value is False for value in digest["authority_summary"].values())


def test_admitted_records_do_not_create_candidates(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    report = _build(tmp_path)
    assert all(row["creates_candidates"] is False for row in report["hypothesis_lifecycle"])
    assert all(row["runs_screening"] is False for row in report["hypothesis_lifecycle"])


def test_safety_flags_all_remain_false(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    report = _build(tmp_path)
    assert all(value is False for value in report["safety"].values())
    assert report["trading_authority"] is False


def test_forbidden_values_are_not_active_statuses_or_decisions(tmp_path: Path) -> None:
    _write_payload(tmp_path, _valid_payload())
    report = _build(tmp_path)
    forbidden = {"promote_to_validation", "register_strategy", "paper_ready", "shadow_ready", "live_ready", "trade", "order", "position"}
    values = set()
    for row in report["hypothesis_lifecycle"]:
        values.add(row["decision"])
        values.add(row["status"])
        values.add(row["next_action"])
    for event in report["events"]:
        values.add(event["decision"])
        values.add(event["status"])
    assert values.isdisjoint(forbidden)


def test_operator_summary_contains_generated_admitted_rejected_blocked_counts(tmp_path: Path, capsys) -> None:
    _write_payload(tmp_path, _valid_payload())
    lifecycle.main(["--repo-root", str(tmp_path), "--write"])
    capsys.readouterr()
    text = (tmp_path / lifecycle.DEFAULT_OUTPUT_DIR / "operator_summary.md").read_text(encoding="utf-8")
    assert "- Generated events: 2" in text
    assert "- Admitted: 2" in text
    assert "- Rejected: 0" in text
    assert "- Blocked: 0" in text
    assert "No candidates were created" in text
    assert "No screening was run" in text

