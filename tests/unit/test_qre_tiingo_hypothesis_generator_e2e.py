from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from research.qre_tiingo_hypothesis_generator_e2e import (
    DEFAULT_OUTPUT_DIR,
    EXPECTED_SNAPSHOT_ID,
    EXPECTED_SOURCE_ID,
    EXPECTED_SOURCE_TIER,
    EXPECTED_UNIVERSE,
    SAFE_FLAGS,
    build_report,
    write_outputs,
)


def _write_resolution(
    root: Path,
    *,
    source: str = EXPECTED_SOURCE_ID,
    snapshot: str = EXPECTED_SNAPSHOT_ID,
    tier: str = EXPECTED_SOURCE_TIER,
    trading_authority: bool = False,
    blockers: list[str] | None = None,
) -> None:
    path = root / "generated_research/alpha_discovery/source_resolution/latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "qre_source_onboarding_v1",
        "report_kind": "qre_alpha_source_resolution",
        "rows": [
            {
                "selected_source": source,
                "selected_snapshot": snapshot,
                "current_source_tier": tier,
                "trading_authority": trading_authority,
                "unresolved_blockers": blockers or [],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_fixture_bars(root: Path, *, symbols: tuple[str, ...] = ("SPY", "QQQ", "TLT", "GLD", "XLK"), days: int = 130) -> None:
    path = root / "data/imports/tiingo_eod_equities_free/tiingo_eod_etf_20210101_20251231/bars.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    slopes = {"SPY": 0.0015, "QQQ": 0.0022, "TLT": -0.0002, "GLD": 0.0008, "XLK": 0.0028}
    current_day = 0
    date_index = 0
    while date_index < days:
        current = date(2021, 1, 4) + timedelta(days=current_day)
        current_day += 1
        if current.weekday() >= 5:
            continue
        for symbol in symbols:
            drift = slopes.get(symbol, 0.001)
            wave = ((date_index % 9) - 4) * 0.0007
            close = 100.0 * (1.0 + drift + wave) ** date_index
            open_ = close / (1.0 + wave if abs(wave) > 0.00001 else 1.0001)
            high = max(open_, close) * 1.002
            low = min(open_, close) * 0.998
            rows.append(
                {
                    "date": current.isoformat(),
                    "symbol": symbol,
                    "open": f"{open_:.6f}",
                    "high": f"{high:.6f}",
                    "low": f"{low:.6f}",
                    "close": f"{close:.6f}",
                    "volume": str(1_000_000 + date_index),
                }
            )
        date_index += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def _ready_root(root: Path) -> None:
    _write_resolution(root)
    _write_fixture_bars(root)


def test_fail_closed_when_source_resolution_is_missing(tmp_path: Path) -> None:
    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_source_resolution"
    assert "missing_or_malformed_source_resolution" in payload["blocked_reasons"]
    assert payload["trading_authority"] is False


def test_fail_closed_when_selected_source_is_wrong(tmp_path: Path) -> None:
    _write_resolution(tmp_path, source="yfinance")

    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_source_resolution"
    assert "unexpected_selected_source" in payload["blocked_reasons"]


def test_fail_closed_when_selected_snapshot_is_wrong(tmp_path: Path) -> None:
    _write_resolution(tmp_path, snapshot="old-snapshot")

    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_source_resolution"
    assert "unexpected_selected_snapshot" in payload["blocked_reasons"]


def test_fail_closed_when_source_tier_is_wrong(tmp_path: Path) -> None:
    _write_resolution(tmp_path, tier="SOURCE_BLOCKED")

    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_source_resolution"
    assert "unexpected_source_tier" in payload["blocked_reasons"]


def test_fail_closed_when_trading_authority_is_true(tmp_path: Path) -> None:
    _write_resolution(tmp_path, trading_authority=True)

    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_source_resolution"
    assert "trading_authority_must_be_false" in payload["blocked_reasons"]


def test_fail_closed_when_unresolved_blockers_are_non_empty(tmp_path: Path) -> None:
    _write_resolution(tmp_path, blockers=["missing_license"])

    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_source_resolution"
    assert "unresolved_blockers_present" in payload["blocked_reasons"]


def test_real_mode_loads_fixture_bars_and_produces_valid_profile(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, status = build_report(tmp_path, mode="real", max_hypotheses=5, seed=1729)
    profile = payload["data_profile"]

    assert status == 0
    assert payload["data_profile_valid"] is True
    assert profile["source_id"] == EXPECTED_SOURCE_ID
    assert profile["source_snapshot_id"] == EXPECTED_SNAPSHOT_ID
    assert profile["row_count"] == 650
    assert profile["symbol_count"] == 5
    assert profile["coverage_ratio"] == 1.0
    assert profile["data_fingerprint"].startswith("sha256:")


def test_real_mode_produces_data_derived_hypotheses_with_source_snapshot_id(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, _status = build_report(tmp_path, mode="real", max_hypotheses=5, seed=1729)

    assert payload["hypotheses_count"] > 0
    assert all(hypothesis["source_snapshot_id"] == EXPECTED_SNAPSHOT_ID for hypothesis in payload["hypotheses"])
    assert all(hypothesis["generated_from_data_profile"] is True for hypothesis in payload["hypotheses"])


def test_every_hypothesis_uses_only_tiingo_etf_universe(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, _status = build_report(tmp_path, mode="real", max_hypotheses=5, seed=1729)

    allowed = set(EXPECTED_UNIVERSE)
    assert all(set(hypothesis["instruments_used"]) <= allowed for hypothesis in payload["hypotheses"])


def test_shuffled_returns_changes_content_identity_or_degrades_verdict(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, _status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)
    summary = payload["summary"]

    assert (
        summary["real_content_identities"] != summary["shuffled_content_identities"]
        or summary["final_verdict"] != "pass_data_driven_hypothesis_generation"
    )


def test_truncated_mode_emits_insufficient_history_or_cross_section(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, _status = build_report(tmp_path, mode="truncated", max_hypotheses=5, seed=1729)

    assert payload["data_profile"]["insufficient_history"] is True or payload["data_profile"]["insufficient_cross_section"] is True
    assert payload["hypotheses_count"] == 0


def test_mode_all_computes_data_dependency_proven_correctly(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, _status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)
    summary = payload["summary"]

    assert summary["real_data_hypotheses_count"] > 0
    assert summary["real_content_identities"] != summary["shuffled_content_identities"]
    assert summary["truncated_control_hypotheses_count"] == 0
    assert summary["data_dependency_proven"] is True
    assert summary["final_verdict"] == "pass_data_driven_hypothesis_generation"


def test_safety_flags_are_always_false_for_forbidden_authority_paths(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    payload, _status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert payload["safety"] == SAFE_FLAGS
    assert all(mode["safety"] == SAFE_FLAGS for mode in payload["modes"].values())


def test_write_writes_only_under_expected_logs_directory(tmp_path: Path) -> None:
    _ready_root(tmp_path)
    payload, _status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    write_outputs(tmp_path, DEFAULT_OUTPUT_DIR, payload)

    files = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())
    assert "logs/qre_tiingo_hypothesis_generator_e2e/latest.json" in files
    assert "logs/qre_tiingo_hypothesis_generator_e2e/operator_summary.md" in files
    assert not any(path.startswith("research/research_latest.json") for path in files)
    assert not any(path.startswith("research/strategy_matrix.csv") for path in files)


def test_without_write_no_output_files_are_written(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert not (tmp_path / DEFAULT_OUTPUT_DIR / "latest.json").exists()
    assert not (tmp_path / DEFAULT_OUTPUT_DIR / "operator_summary.md").exists()


def test_deterministic_rerun_with_same_seed_yields_same_content_identities(tmp_path: Path) -> None:
    _ready_root(tmp_path)

    first, _status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)
    second, _status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert first["summary"]["real_content_identities"] == second["summary"]["real_content_identities"]
    assert first["summary"]["shuffled_content_identities"] == second["summary"]["shuffled_content_identities"]


def test_old_controlled_universe_symbols_are_rejected_or_absent(tmp_path: Path) -> None:
    _write_resolution(tmp_path)
    _write_fixture_bars(tmp_path, symbols=("AAPL", "MSFT", "SONY"), days=130)

    payload, status = build_report(tmp_path, mode="all", max_hypotheses=5, seed=1729)

    assert status == 1
    assert payload["final_verdict"] == "blocked_data_unavailable"
    assert "old_controlled_universe_detected" in payload["blocked_reasons"]
