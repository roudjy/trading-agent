"""PR-D — integration test for reporting.intelligent_routing_status.

Pins:

* The status reporter reads ``logs/intelligent_routing/latest.json``
  and emits a structured envelope with bucket counts and the
  advisory framing carried verbatim.
* Default CLI mode is ``--no-write`` (writes nothing).
* ``--write`` persists exactly ``logs/intelligent_routing_status/
  latest.json`` (single file).
* The status reporter does **not** import or modify
  ``reporting.governance_status`` (Critical-review item 3).
* Missing artifact → ``routing_artifact_status="not_available"`` and
  ``error="routing_artifact_not_found"``; no crash.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing_status as irs


def _write_routing_artifact(path: Path, decisions: list[dict]) -> None:
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


def _decision(
    cid: str, *,
    info_gain_bucket: str = "none",
    orthogonality_bucket: str = "novel",
    advisory_suppression_reason: str | None = None,
) -> dict:
    return {
        "campaign_id": cid,
        "preset_name": "preset_x",
        "behavior_coordinates": {
            "family": "f", "asset_class": "a", "timeframe": "t",
            "provisional": True,
        },
        "info_gain_score": 0.0,
        "info_gain_bucket": info_gain_bucket,
        "dead_zone_status": "alive",
        "near_duplicate_group": None,
        "orthogonality_bucket": orthogonality_bucket,
        "advisory_suppression_reason": advisory_suppression_reason,
        "advisory_priority_score": 0,
        "advisory_rank": 1,
        "tie_break_key": f"|{cid}",
    }


# ---------------------------------------------------------------------------
# build_status — envelope shape + bucket counts
# ---------------------------------------------------------------------------


def test_build_status_with_present_artifact(tmp_path: Path) -> None:
    art = tmp_path / "latest.json"
    _write_routing_artifact(art, [
        _decision("c1", info_gain_bucket="high", orthogonality_bucket="novel"),
        _decision("c2", info_gain_bucket="medium", orthogonality_bucket="adjacent"),
        _decision("c3", info_gain_bucket="medium", orthogonality_bucket="adjacent"),
        _decision("c4", advisory_suppression_reason="dead_zone"),
        _decision("c5", advisory_suppression_reason="near_duplicate"),
    ])
    out = irs.build_status(routing_artifact_path=art)
    assert out["report_kind"] == "intelligent_routing_status"
    assert out["routing_artifact_status"] == "present"
    assert out["routing_effect"] == "advisory_only"
    assert out["queue_ordering_effect"] == "none"
    s = out["summary"]
    assert s["total"] == 5
    assert s["by_advisory_suppression_reason"]["none"] == 3
    assert s["by_advisory_suppression_reason"]["dead_zone"] == 1
    assert s["by_advisory_suppression_reason"]["near_duplicate"] == 1
    assert s["by_info_gain_bucket"]["high"] == 1
    assert s["by_info_gain_bucket"]["medium"] == 2
    assert s["by_orthogonality_bucket"]["novel"] >= 1


def test_build_status_with_missing_artifact(tmp_path: Path) -> None:
    out = irs.build_status(routing_artifact_path=tmp_path / "absent.json")
    assert out["routing_artifact_status"] == "not_available"
    assert out["error"] == "routing_artifact_not_found"
    assert out["summary"]["total"] == 0


def test_build_status_with_malformed_artifact(tmp_path: Path) -> None:
    art = tmp_path / "bad.json"
    art.write_text("not json", encoding="utf-8")
    out = irs.build_status(routing_artifact_path=art)
    assert out["routing_artifact_status"] == "malformed"
    assert out["error"] == "routing_artifact_unreadable_or_invalid_json"


# ---------------------------------------------------------------------------
# CLI --no-write / --write semantics
# ---------------------------------------------------------------------------


def test_cli_default_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_dir = tmp_path / "logs" / "intelligent_routing_status"
    monkeypatch.setattr(irs, "STATUS_OUTPUT_DIR", out_dir)
    monkeypatch.setattr(irs, "STATUS_LATEST_OUTPUT_PATH", out_dir / "latest.json")
    rc = irs.main([])
    assert rc == 0
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["report_kind"] == "intelligent_routing_status"
    assert not out_dir.exists()


def test_cli_write_persists_only_latest_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "logs" / "intelligent_routing_status"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(irs, "STATUS_OUTPUT_DIR", out_dir)
    monkeypatch.setattr(irs, "STATUS_LATEST_OUTPUT_PATH", out_path)
    rc = irs.main(["--write"])
    assert rc == 0
    assert out_path.exists()
    siblings = sorted(p.name for p in out_dir.iterdir())
    assert siblings == ["latest.json"]


# ---------------------------------------------------------------------------
# Critical-review item 3 — does NOT modify reporting.governance_status
# ---------------------------------------------------------------------------


def test_status_module_does_not_import_governance_status() -> None:
    """The standalone status module must not pull in
    reporting.governance_status, per Critical-review item 3."""
    importlib.reload(irs)
    import sys
    irs_mod_obj = sys.modules.get("reporting.intelligent_routing_status")
    assert irs_mod_obj is not None
    # The module must not transitively import reporting.governance_status
    # as part of its import. We re-snapshot sys.modules around a clean
    # reimport.
    sys.modules.pop("reporting.intelligent_routing_status", None)
    importlib.import_module("reporting.intelligent_routing_status")
    # We can't enforce that no other test in the run loaded it, but the
    # module's source must not reference it.
    src = (Path(__file__).resolve().parent.parent.parent
           / "reporting" / "intelligent_routing_status.py").read_text(
        encoding="utf-8"
    )
    # Look for an actual import statement, not a substring match — the
    # docstring may legitimately *mention* governance_status to record
    # that this module deliberately does not import it (Critical-review
    # item 3).
    import re
    pattern = re.compile(
        r"^(?:from\s+reporting(?:\.\w+)?\s+import\s+[^\n]*governance_status"
        r"|import\s+reporting\.governance_status)",
        flags=re.MULTILINE,
    )
    assert pattern.search(src) is None
