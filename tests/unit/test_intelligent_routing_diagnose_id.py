"""PR-D — --diagnose-id tests for reporting.intelligent_routing.

Pins (Critical-review item 2):

* ``_diagnose_id`` returns the matching decision when present.
* Empty / missing campaign_id yields a structured envelope with
  ``error != None`` and ``match == None``.
* If the artifact is missing, ``artifact_status == "not_available"``
  and no exception is raised.
* If the artifact is malformed, ``artifact_status == "malformed"``.
* **--diagnose-id never writes** (Critical-review item 2):
  - if ``logs/intelligent_routing/latest.json`` already exists,
    invoking ``main(["--diagnose-id", ...])`` does **not** change
    its bytes or its mtime.
  - if it does not exist, the directory is **not** created.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


def _write_artifact(path: Path, decisions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "report_kind": "intelligent_routing",
        "version": "v3.15.16",
        "routing_effect": "advisory_only",
        "queue_ordering_effect": "none",
        "generated_at_utc": "2026-05-06T12:00:00+00:00",
        "provenance": {},
        "decisions": decisions,
        "summary": {
            "total": len(decisions),
            "advisory_suppressed_dead_zone": 0,
            "advisory_suppressed_near_duplicate": 0,
            "high_info_gain": 0,
            "novel_behavior_coordinates": 0,
            "metadata_gaps": 0,
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _decision(cid: str, reason: str | None = None) -> dict:
    return {
        "campaign_id": cid,
        "preset_name": "preset_x",
        "behavior_coordinates": {
            "family": "ema_crossover",
            "asset_class": "crypto",
            "timeframe": "4h",
            "provisional": True,
        },
        "info_gain_score": 0.0,
        "info_gain_bucket": "none",
        "dead_zone_status": "alive",
        "near_duplicate_group": None,
        "orthogonality_bucket": "novel",
        "advisory_suppression_reason": reason,
        "advisory_priority_score": 2,
        "advisory_rank": 1,
        "tie_break_key": f"2026-05-06T10:00:00+00:00|{cid}",
    }


# ---------------------------------------------------------------------------
# _diagnose_id — schema + match logic
# ---------------------------------------------------------------------------


def test_diagnose_id_returns_match_when_present(tmp_path: Path) -> None:
    artifact = tmp_path / "latest.json"
    _write_artifact(artifact, [_decision("col-c1"), _decision("col-c2")])
    out = ir._diagnose_id("col-c2", latest_artifact_path=artifact)
    assert out["report_kind"] == ir.DIAGNOSE_REPORT_KIND
    assert out["target_campaign_id"] == "col-c2"
    assert out["artifact_status"] == "present"
    assert isinstance(out["match"], dict)
    assert out["match"]["campaign_id"] == "col-c2"
    assert out["error"] is None


def test_diagnose_id_returns_no_match_envelope(tmp_path: Path) -> None:
    artifact = tmp_path / "latest.json"
    _write_artifact(artifact, [_decision("col-c1")])
    out = ir._diagnose_id("col-other", latest_artifact_path=artifact)
    assert out["artifact_status"] == "present"
    assert out["match"] is None
    assert out["error"] == "campaign_id_not_in_artifact"


def test_diagnose_id_handles_missing_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "missing.json"
    out = ir._diagnose_id("col-c1", latest_artifact_path=artifact)
    assert out["artifact_status"] == "not_available"
    assert out["match"] is None
    assert out["error"] == "artifact_not_found"


def test_diagnose_id_handles_malformed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "bad.json"
    artifact.write_text("not json", encoding="utf-8")
    out = ir._diagnose_id("col-c1", latest_artifact_path=artifact)
    assert out["artifact_status"] == "malformed"
    assert out["match"] is None
    assert out["error"] == "artifact_unreadable_or_invalid_json"


def test_diagnose_id_handles_decisions_not_a_list(tmp_path: Path) -> None:
    artifact = tmp_path / "weird.json"
    artifact.write_text(
        json.dumps({"decisions": "oops"}), encoding="utf-8",
    )
    out = ir._diagnose_id("col-c1", latest_artifact_path=artifact)
    assert out["artifact_status"] == "malformed"
    assert out["error"] == "decisions_field_not_a_list"


def test_diagnose_id_empty_target(tmp_path: Path) -> None:
    artifact = tmp_path / "latest.json"
    _write_artifact(artifact, [_decision("col-c1")])
    out = ir._diagnose_id("", latest_artifact_path=artifact)
    assert out["match"] is None
    assert out["error"] == "empty_target_campaign_id"


# ---------------------------------------------------------------------------
# CLI --diagnose-id NEVER writes (Critical-review item 2)
# ---------------------------------------------------------------------------


def test_cli_diagnose_id_does_not_change_existing_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If logs/intelligent_routing/latest.json already exists,
    --diagnose-id must not change its bytes or mtime."""
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    _write_artifact(out_path, [_decision("col-c1")])
    bytes_before = out_path.read_bytes()
    mtime_before = out_path.stat().st_mtime
    # Ensure a measurable mtime gap exists: pause the test enough to
    # guarantee the filesystem mtime would differ if a write occurred.
    time.sleep(0.05)
    rc = ir.main(["--diagnose-id", "col-c1"])
    assert rc == 0
    bytes_after = out_path.read_bytes()
    mtime_after = out_path.stat().st_mtime
    assert bytes_before == bytes_after
    assert mtime_before == mtime_after


def test_cli_diagnose_id_does_not_create_artifact_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If logs/intelligent_routing/ does not exist, --diagnose-id must
    not create it."""
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    rc = ir.main(["--diagnose-id", "col-anything"])
    assert rc == 0
    assert not out_dir.exists()
    assert not out_path.exists()


def test_cli_diagnose_id_emits_envelope_on_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    _write_artifact(out_path, [_decision("col-target")])
    rc = ir.main(["--diagnose-id", "col-target"])
    assert rc == 0
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["report_kind"] == "intelligent_routing_diagnose_id"
    assert body["target_campaign_id"] == "col-target"
    assert body["match"]["campaign_id"] == "col-target"


def test_cli_diagnose_id_with_write_flag_still_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--diagnose-id takes precedence over --write; no artifact write
    occurs even if --write is also passed."""
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    rc = ir.main(["--diagnose-id", "col-x", "--write"])
    assert rc == 0
    assert not out_path.exists()
