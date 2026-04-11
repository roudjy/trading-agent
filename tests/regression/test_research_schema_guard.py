import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.results import (
    JSON_SUMMARY_SCHEMA,
    JSON_TOP_LEVEL_SCHEMA,
    ROW_SCHEMA,
    SchemaDriftError,
    _assert_payload_schema,
    make_result_row,
    write_latest_json,
    write_results_to_csv,
)


AS_OF_UTC = datetime(2026, 4, 8, 10, 59, 31, 381566, tzinfo=UTC)
FIXTURE_CSV_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "research_schema_stability"
    / "strategy_matrix.csv"
)


def _strategy():
    return {
        "name": "synthetic_strategy",
        "family": "trend",
        "hypothesis": "Synthetic hypothesis",
    }


def _metrics():
    return {
        "win_rate": 0.55,
        "sharpe": 1.234,
        "deflated_sharpe": 1.111,
        "max_drawdown": 0.12,
        "trades_per_maand": 2.5,
        "consistentie": 0.75,
        "totaal_trades": 12,
        "goedgekeurd": True,
        "criteria_checks": {
            "consistentie": True,
            "deflated_sharpe": True,
            "max_drawdown": True,
            "trades_per_maand": True,
            "win_rate": True,
        },
        "reden": "",
    }


def _row():
    return make_result_row(
        strategy=_strategy(),
        asset="BTC-USD",
        interval="1d",
        params={"periode": 14},
        as_of_utc=AS_OF_UTC,
        metrics=_metrics(),
    )


def test_row_schema_matches_make_result_row_keys():
    row = _row()

    assert tuple(row.keys()) == ROW_SCHEMA


def test_json_top_level_schema_matches_write_latest_json(tmp_path):
    path = tmp_path / "research_latest.json"
    write_latest_json([_row()], as_of_utc=AS_OF_UTC, path=path)

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert tuple(payload.keys()) == JSON_TOP_LEVEL_SCHEMA


def test_json_summary_schema_matches_write_latest_json(tmp_path):
    path = tmp_path / "research_latest.json"
    write_latest_json([_row()], as_of_utc=AS_OF_UTC, path=path)

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert tuple(payload["summary"].keys()) == JSON_SUMMARY_SCHEMA


def test_write_csv_rejects_extra_row_key(tmp_path):
    row = _row()
    row["bogus_key"] = "unexpected"

    with pytest.raises(SchemaDriftError, match="drift") as excinfo:
        write_results_to_csv([row], path=tmp_path / "strategy_matrix.csv")

    assert "bogus_key" in str(excinfo.value)


def test_write_csv_rejects_missing_row_key(tmp_path):
    row = _row()
    row.pop("reden")

    with pytest.raises(SchemaDriftError) as excinfo:
        write_results_to_csv([row], path=tmp_path / "strategy_matrix.csv")

    assert "reden" in str(excinfo.value)


def test_write_json_rejects_reordered_top_level():
    payload = {
        "count": 1,
        "generated_at_utc": AS_OF_UTC.isoformat(),
        "summary": {
            "success": 1,
            "failed": 0,
            "goedgekeurd": 1,
        },
        "results": [_row()],
    }

    with pytest.raises(SchemaDriftError):
        _assert_payload_schema(payload)


def test_csv_header_line_equals_row_schema_joined(tmp_path):
    path = tmp_path / "strategy_matrix.csv"
    write_results_to_csv([_row()], path=path)

    header = path.read_text(encoding="utf-8").splitlines()[0]

    assert header == ",".join(ROW_SCHEMA)


def test_fixture_csv_header_matches_row_schema():
    header = FIXTURE_CSV_PATH.read_text(encoding="utf-8").splitlines()[0]

    assert header == ",".join(ROW_SCHEMA)


def test_happy_path_real_make_result_row_roundtrip(tmp_path):
    row = _row()
    csv_path = tmp_path / "strategy_matrix.csv"
    json_path = tmp_path / "research_latest.json"

    write_results_to_csv([row], path=csv_path)
    write_latest_json([row], as_of_utc=AS_OF_UTC, path=json_path)

    csv_lines = csv_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert len(csv_lines) == 2
    assert csv_lines[0] == ",".join(ROW_SCHEMA)
    assert tuple(payload.keys()) == JSON_TOP_LEVEL_SCHEMA
    assert tuple(payload["summary"].keys()) == JSON_SUMMARY_SCHEMA
    assert tuple(payload["results"][0].keys()) == ROW_SCHEMA
