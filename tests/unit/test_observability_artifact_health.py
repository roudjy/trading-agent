"""Unit tests for research.diagnostics.artifact_health."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics.artifact_health import inspect_artifact_health


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def test_empty_input_list(fixed_now: datetime):
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=())
    assert payload["schema_version"] == "1.0"
    assert payload["generated_at_utc"] == "2026-04-28T10:00:00Z"
    assert payload["summary"]["total"] == 0
    assert payload["artifacts"] == []


def test_missing_artifact(tmp_path: Path, fixed_now: datetime):
    artifacts = (
        ("missing.json", "campaign_artifact", tmp_path / "missing.json"),
    )
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    assert row["exists"] is False
    assert row["parse_ok"] is False
    assert row["stale"] is False
    assert payload["summary"]["missing"] == 1
    assert payload["summary"]["fresh"] == 0


def test_valid_json_artifact(tmp_path: Path, fixed_now: datetime):
    p = tmp_path / "valid.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at_utc": "2026-04-28T09:00:00Z",
                "campaigns": [{"campaign_id": "c-1"}],
            }
        ),
        encoding="utf-8",
    )
    artifacts = (("valid.json", "campaign_artifact", p),)
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    assert row["exists"] is True
    assert row["parse_ok"] is True
    assert row["schema_version"] == "1.0"
    assert row["generated_at_utc"] == "2026-04-28T09:00:00Z"
    assert row["linked_ids"]["campaign_id"] == "c-1"
    assert row["contract_class"] == "campaign_artifact"
    assert payload["summary"]["fresh"] == 1


def test_corrupt_json_artifact(tmp_path: Path, fixed_now: datetime):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    artifacts = (("bad.json", "campaign_artifact", p),)
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    assert row["exists"] is True
    assert row["parse_ok"] is False
    assert row["parse_error_type"] == "JSONDecodeError"
    assert payload["summary"]["corrupt"] == 1


def test_empty_file_classified_as_empty(tmp_path: Path, fixed_now: datetime):
    p = tmp_path / "empty.json"
    p.write_text("", encoding="utf-8")
    artifacts = (("empty.json", "campaign_artifact", p),)
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    assert row["exists"] is True
    assert row["empty"] is True
    assert payload["summary"]["empty"] == 1


def test_stale_artifact(tmp_path: Path, fixed_now: datetime):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({}), encoding="utf-8")
    # Backdate by 12h; campaign_artifact threshold is 4h.
    old_time = fixed_now.timestamp() - 12 * 3600
    import os

    os.utime(p, (old_time, old_time))
    artifacts = (("old.json", "campaign_artifact", p),)
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    assert row["stale"] is True
    assert "threshold=" in (row["stale_reason"] or "")
    assert payload["summary"]["stale"] == 1


def test_frozen_contract_classification(tmp_path: Path, fixed_now: datetime):
    p = tmp_path / "research_latest.json"
    p.write_text(json.dumps({"foo": 1}), encoding="utf-8")
    artifacts = (("research_latest.json", "frozen_public_contract", p),)
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    assert row["contract_class"] == "frozen_public_contract"
    assert payload["summary"]["by_contract_class"] == {"frozen_public_contract": 1}


def test_csv_inspected_stat_only(tmp_path: Path, fixed_now: datetime):
    p = tmp_path / "strategy_matrix.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    artifacts = (("strategy_matrix.csv", "frozen_public_contract", p),)
    payload = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    row = payload["artifacts"][0]
    # CSV is inspected stat-only, so it counts as parse_ok with no schema_version.
    assert row["parse_ok"] is True
    assert row["schema_version"] is None


def test_deterministic_output_for_fixed_inputs(tmp_path: Path, fixed_now: datetime):
    """Identical inputs at the same instant must produce byte-identical output."""
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"campaigns": []}), encoding="utf-8")
    artifacts = (("x.json", "campaign_artifact", p),)
    a = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    b = inspect_artifact_health(now_utc=fixed_now, artifacts=artifacts)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
