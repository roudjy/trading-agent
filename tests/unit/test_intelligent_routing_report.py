"""PR-B — report builder + CLI tests for reporting.intelligent_routing.

Pins:

* The report carries the advisory framing fields verbatim.
* Missing inputs produce a graceful ``not_available`` envelope per
  input — no crash.
* The report is byte-deterministic across two invocations with
  identical inputs and identical ``now_utc``.
* The CLI default is ``--no-write`` (writes nothing).
* ``--write`` persists exactly one file: ``logs/intelligent_routing/
  latest.json``. No timestamped siblings (Correction 8).
* The report content emitted to stdout in ``--no-write`` mode equals
  the content the same invocation would have written under ``--write``.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


# ---------------------------------------------------------------------------
# Fixtures: synthetic input artifacts in a temp tree
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now_utc() -> _dt.datetime:
    return _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)


@pytest.fixture
def synth_inputs(tmp_path: Path) -> dict[str, Path]:
    """Build a small but realistic multi-campaign input set."""
    queue = {
        "schema_version": "1.0",
        "queue": [
            {
                "campaign_id": "col-c1",
                "priority_tier": 2,
                "spawned_at_utc": "2026-05-06T10:00:00+00:00",
                "state": "pending",
            },
            {
                "campaign_id": "col-c2",
                "priority_tier": 2,
                "spawned_at_utc": "2026-05-06T10:01:00+00:00",
                "state": "pending",
            },
            {
                "campaign_id": "col-c3",
                "priority_tier": 3,
                "spawned_at_utc": "2026-05-06T10:02:00+00:00",
                "state": "pending",
            },
        ],
    }
    registry = {
        "schema_version": "1.0",
        "campaigns": [
            {
                "campaign_id": "col-c1",
                "preset_name": "preset_alpha",
                "strategy_family": "ema_crossover",
                "asset_class": "crypto",
                "extra": {"timeframe": "4h"},
                "input_artifact_fingerprint": "abcd1234deadbeef",
                "spawned_at_utc": "2026-05-06T10:00:00+00:00",
            },
            {
                "campaign_id": "col-c2",
                "preset_name": "preset_alpha",
                "strategy_family": "ema_crossover",
                "asset_class": "crypto",
                "extra": {"timeframe": "4h"},
                "input_artifact_fingerprint": "abcd1234deadbeef",
                "spawned_at_utc": "2026-05-06T10:01:00+00:00",
            },
            {
                "campaign_id": "col-c3",
                "preset_name": "preset_beta",
                "strategy_family": "rsi_extreme",
                "asset_class": "equities",
                "extra": {"timeframe": "1d"},
                "input_artifact_fingerprint": "ffff0000",
                "spawned_at_utc": "2026-05-06T10:02:00+00:00",
            },
        ],
    }
    dead_zones = {
        "schema_version": "1.0",
        "zones": [
            {
                "asset": "crypto",
                "timeframe": "4h",
                "strategy_family": "ema_crossover",
                "zone_status": "dead",
            },
            {
                "asset": "equities",
                "timeframe": "1d",
                "strategy_family": "rsi_extreme",
                "zone_status": "alive",
            },
        ],
    }
    information_gain = {
        "schema_version": "1.0",
        "col_campaign_id": "col-c3",
        "preset_name": "preset_beta",
        "hypothesis_id": "h_x",
        "information_gain": {
            "score": 0.85,
            "bucket": "high",
            "is_meaningful_campaign": True,
        },
    }

    qp = tmp_path / "queue.json"
    rp = tmp_path / "registry.json"
    dp = tmp_path / "dead_zones.json"
    ip = tmp_path / "ig.json"
    qp.write_text(json.dumps(queue), encoding="utf-8")
    rp.write_text(json.dumps(registry), encoding="utf-8")
    dp.write_text(json.dumps(dead_zones), encoding="utf-8")
    ip.write_text(json.dumps(information_gain), encoding="utf-8")
    return {
        "queue": qp,
        "registry": rp,
        "dead_zones": dp,
        "information_gain": ip,
    }


# ---------------------------------------------------------------------------
# build_report — happy path
# ---------------------------------------------------------------------------


def _build(synth_inputs: dict[str, Path], now: _dt.datetime) -> ir.RoutingReport:
    return ir.build_report(
        now_utc=now,
        queue_path=synth_inputs["queue"],
        registry_path=synth_inputs["registry"],
        dead_zones_path=synth_inputs["dead_zones"],
        information_gain_path=synth_inputs["information_gain"],
    )


def test_report_carries_advisory_framing(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    payload = report.to_payload()
    assert payload["routing_effect"] == "advisory_only"
    assert payload["queue_ordering_effect"] == "none"
    assert payload["schema_version"] == "1.0"
    assert payload["report_kind"] == "intelligent_routing"
    assert payload["version"] == "v3.15.16"
    assert (
        payload["generated_at_utc"]
        == fixed_now_utc.astimezone(_dt.timezone.utc).isoformat()
    )


def test_report_decisions_one_per_campaign(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    cids = sorted(d.campaign_id for d in report.decisions)
    assert cids == ["col-c1", "col-c2", "col-c3"]


def test_report_dead_zone_status_classified(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # crypto/4h/ema_crossover is "dead" in the fixture.
    assert by_id["col-c1"].dead_zone_status == "dead"
    assert by_id["col-c2"].dead_zone_status == "dead"
    # equities/1d/rsi_extreme is "alive".
    assert by_id["col-c3"].dead_zone_status == "alive"


def test_report_info_gain_lookup_per_campaign(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # IG fixture only has col-c3 → score 0.85, bucket "high".
    assert by_id["col-c3"].info_gain_score == pytest.approx(0.85)
    assert by_id["col-c3"].info_gain_bucket == "high"
    # The other two have no IG entry → fall back to 0/none.
    assert by_id["col-c1"].info_gain_score == 0.0
    assert by_id["col-c1"].info_gain_bucket == "none"
    assert by_id["col-c2"].info_gain_score == 0.0
    assert by_id["col-c2"].info_gain_bucket == "none"


def test_report_orthogonality_bucket_uses_prior_count_excluding_self(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # col-c1 and col-c2 share (ema_crossover, crypto, 4h). Each sees
    # exactly 1 prior — adjacent.
    assert by_id["col-c1"].orthogonality_bucket == "adjacent"
    assert by_id["col-c2"].orthogonality_bucket == "adjacent"
    # col-c3 has unique coords — novel.
    assert by_id["col-c3"].orthogonality_bucket == "novel"


def test_report_near_duplicate_group_consistent_within_coords(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    by_id = {d.campaign_id: d for d in report.decisions}
    # Same coords + same fingerprint prefix → same group.
    assert (
        by_id["col-c1"].near_duplicate_group
        == by_id["col-c2"].near_duplicate_group
    )
    # Different coords → different group.
    assert (
        by_id["col-c1"].near_duplicate_group
        != by_id["col-c3"].near_duplicate_group
    )


def test_report_decisions_are_sorted_deterministically(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    """PR-C: decisions are listed in ``advisory_rank`` ascending order
    — equivalent to ``(-priority, tie_break_key)`` ascending. Two
    invocations with identical inputs produce the same total ordering.
    """
    report = _build(synth_inputs, fixed_now_utc)
    ranks = [d.advisory_rank for d in report.decisions]
    assert ranks == sorted(ranks)
    # Re-build and assert the listing is byte-identical with a pinned
    # generated_at_utc.
    report2 = _build(synth_inputs, fixed_now_utc)
    assert report.to_payload() == report2.to_payload()


def test_report_summary_counts(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    """PR-C: summary counters reflect the suppression pipeline.

    Fixture: col-c1 and col-c2 share coords (crypto/4h/ema_crossover)
    and the dead-zones artifact marks that coord ``dead`` — both get
    ``advisory_suppressed_dead_zone``. col-c3 is on a unique alive
    coordinate.
    """
    report = _build(synth_inputs, fixed_now_utc)
    s = report.summary
    assert s.total == 3
    # Both crypto/4h/ema_crossover campaigns are dead-zone suppressed.
    assert s.advisory_suppressed_dead_zone == 2
    # Dead-zone takes precedence over near-duplicate, so the
    # near-duplicate counter stays 0.
    assert s.advisory_suppressed_near_duplicate == 0
    assert s.high_info_gain == 1  # only col-c3 (IG=0.85)
    assert s.novel_behavior_coordinates == 1  # only col-c3 (unique coords)
    assert s.metadata_gaps == 0  # all coordinates fully populated


def test_report_provenance_present_for_every_input(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = _build(synth_inputs, fixed_now_utc)
    payload = report.to_payload()
    prov = payload["provenance"]
    assert isinstance(prov, dict)
    # One key per input file.
    assert len(prov) == 4
    for entry in prov.values():
        assert entry["status"] == "present"
        # SHA256 is 64 hex chars.
        assert len(entry["sha256"]) == 64
        assert "mtime_utc" in entry


# ---------------------------------------------------------------------------
# Missing inputs → not_available envelope
# ---------------------------------------------------------------------------


def test_report_missing_inputs_emit_not_available(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    # All four paths absent.
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=tmp_path / "missing_queue.json",
        registry_path=tmp_path / "missing_registry.json",
        dead_zones_path=tmp_path / "missing_dz.json",
        information_gain_path=tmp_path / "missing_ig.json",
    )
    payload = report.to_payload()
    assert payload["routing_effect"] == "advisory_only"
    assert payload["decisions"] == []
    assert payload["summary"]["total"] == 0
    for entry in payload["provenance"].values():
        assert entry["status"] == "not_available"


def test_report_malformed_json_does_not_crash(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=bad,
        registry_path=bad,
        dead_zones_path=bad,
        information_gain_path=bad,
    )
    assert report.decisions == ()
    assert report.summary.total == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_report_byte_identical_across_two_invocations(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    a = _build(synth_inputs, fixed_now_utc).to_payload()
    b = _build(synth_inputs, fixed_now_utc).to_payload()
    text_a = json.dumps(a, indent=2, sort_keys=True)
    text_b = json.dumps(b, indent=2, sort_keys=True)
    assert text_a == text_b


def test_report_callable_now_utc_seam(
    synth_inputs: dict[str, Path], fixed_now_utc: _dt.datetime,
) -> None:
    report = ir.build_report(
        now_utc=lambda: fixed_now_utc,
        queue_path=synth_inputs["queue"],
        registry_path=synth_inputs["registry"],
        dead_zones_path=synth_inputs["dead_zones"],
        information_gain_path=synth_inputs["information_gain"],
    )
    assert report.generated_at_utc == fixed_now_utc.isoformat()


# ---------------------------------------------------------------------------
# CLI semantics — --no-write is the default; --write persists one file
# ---------------------------------------------------------------------------


def test_cli_default_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default invocation prints to stdout and creates no logs/ output."""
    out_dir = tmp_path / "logs" / "intelligent_routing"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_dir / "latest.json")
    rc = ir.main([])
    assert rc == 0
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["routing_effect"] == "advisory_only"
    # No artifact directory created.
    assert not out_dir.exists()


def test_cli_no_write_flag_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_dir = tmp_path / "logs" / "intelligent_routing"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_dir / "latest.json")
    rc = ir.main(["--no-write"])
    assert rc == 0
    assert not out_dir.exists()


def test_cli_write_persists_exactly_latest_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    rc = ir.main(["--write"])
    assert rc == 0
    # latest.json written.
    assert out_path.exists()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert body["routing_effect"] == "advisory_only"
    # No timestamped siblings (Correction 8).
    siblings = sorted(p.name for p in out_dir.iterdir())
    assert siblings == ["latest.json"]


def test_cli_no_write_and_write_produce_same_payload_modulo_now(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stdout payload from --no-write equals the file content under
    --write when the inputs are identical (modulo generated_at_utc)."""
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    # Pin the clock so the timestamps match.
    fixed = _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)
    monkeypatch.setattr(ir, "_now_utc_default", lambda: fixed)
    rc1 = ir.main(["--no-write"])
    captured = capsys.readouterr()
    rc2 = ir.main(["--write"])
    assert rc1 == 0 and rc2 == 0
    written = out_path.read_text(encoding="utf-8")
    # Both serializations use indent=2 sort_keys=True.
    assert json.loads(captured.out) == json.loads(written)


def test_cli_write_is_idempotent_when_inputs_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    fixed = _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)
    monkeypatch.setattr(ir, "_now_utc_default", lambda: fixed)
    ir.main(["--write"])
    bytes_a = out_path.read_bytes()
    ir.main(["--write"])
    bytes_b = out_path.read_bytes()
    assert bytes_a == bytes_b
