from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research import qre_approved_bounded_evidence_materialization as approved


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _approval() -> dict[str, object]:
    return {
        "approval_id": "qre_bounded_validation_first_batch_001",
        "approved_by": "operator:joery",
        "approved_at_utc": "2026-06-18T18:37:18Z",
        "expiry_utc": "2026-06-19T18:37:18Z",
        "scope": {
            "symbols": ["AAPL", "NVDA"],
            "preset_id": "trend_pullback_continuation_daily_v1",
            "timeframe": "daily_v1",
        },
        "allowed_command_class": "bounded_controlled_validation",
        "allowed_output_paths": list(approved.ALLOWED_OUTPUT_PATHS),
        "forbidden_capabilities": [
            "strategy_synthesis",
            "candidate_promotion",
            "broker_access",
        ],
        "dry_run_allowed": True,
        "real_run_allowed": True,
        "evidence_acceptance_allowed": True,
        "external_fetch_allowed": False,
    }


def _queue_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_basket_next_action_queue",
        "rows": [
            {
                "symbol": "AAPL",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
            },
            {
                "symbol": "NVDA",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "candidate_id": "seed::trend_pullback_continuation_daily_v1::NVDA",
            },
        ],
    }


def test_normalize_approval_payload_flattens_scope() -> None:
    normalized = approved._normalize_approval_payload(_approval())
    assert normalized["symbols"] == ["AAPL", "NVDA"]
    assert normalized["preset_id"] == "trend_pullback_continuation_daily_v1"
    assert normalized["timeframe"] == "daily_v1"
    assert normalized["external_fetch_allowed"] is False


def test_read_json_accepts_utf8_bom(tmp_path: Path) -> None:
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(_approval()), encoding="utf-8-sig")

    payload = approved._read_json(approval_path)

    assert payload["approval_id"] == "qre_bounded_validation_first_batch_001"


def test_build_request_payload_uses_approved_scope() -> None:
    normalized = approved._normalize_approval_payload(_approval())
    payload = approved._build_request_payload(normalized, created_at_utc="2026-06-18T19:00:00Z")
    assert payload["symbols"] == ["AAPL", "NVDA"]
    assert payload["preset_id"] == "trend_pullback_continuation_daily_v1"
    assert payload["timeframe"] == "daily_v1"
    assert payload["approval_ref"] == "qre_bounded_validation_first_batch_001"


def test_candidate_ids_from_queue_uses_existing_ids(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs/qre_basket_next_action_queue/latest.json", _queue_payload())
    result = approved._candidate_ids_from_queue(
        repo_root=tmp_path,
        symbols=["AAPL", "NVDA"],
        preset_id="trend_pullback_continuation_daily_v1",
        timeframe="daily_v1",
    )
    assert result["AAPL"] == "seed::trend_pullback_continuation_daily_v1::AAPL"
    assert result["NVDA"] == "seed::trend_pullback_continuation_daily_v1::NVDA"


def test_common_local_window_and_stitched_cache_are_local_only(tmp_path: Path) -> None:
    cache_dir = tmp_path / "data/cache/market"
    cache_dir.mkdir(parents=True, exist_ok=True)
    aapl = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2026-04-08", periods=6, freq="D", tz="UTC"),
            "open": [1, 2, 3, 4, 5, 6],
            "high": [2, 3, 4, 5, 6, 7],
            "low": [0, 1, 2, 3, 4, 5],
            "close": [1, 2, 3, 4, 5, 6],
            "volume": [10, 11, 12, 13, 14, 15],
        }
    )
    nvda = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2026-04-10", periods=6, freq="D", tz="UTC"),
            "open": [7, 8, 9, 10, 11, 12],
            "high": [8, 9, 10, 11, 12, 13],
            "low": [6, 7, 8, 9, 10, 11],
            "close": [7, 8, 9, 10, 11, 12],
            "volume": [20, 21, 22, 23, 24, 25],
        }
    )
    aapl.to_parquet(cache_dir / "yfinance__AAPL__1d__20260408__20260413__a.parquet", index=False)
    nvda.to_parquet(cache_dir / "yfinance__NVDA__1d__20260410__20260415__b.parquet", index=False)

    left = approved._load_stitched_local_cache_frame(repo_root=tmp_path, symbol="AAPL", interval="1d")
    right = approved._load_stitched_local_cache_frame(repo_root=tmp_path, symbol="NVDA", interval="1d")
    start, end = approved._common_local_window({"AAPL": left, "NVDA": right})

    assert len(left) == 6
    assert len(right) == 6
    assert start.isoformat() == "2026-04-10T00:00:00"
    assert end.isoformat() == "2026-04-13T00:00:00"
