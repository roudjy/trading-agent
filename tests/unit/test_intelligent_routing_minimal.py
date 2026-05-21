"""Tests for ``reporting.intelligent_routing_minimal``.

Pins the minimal v3.15.16 reset slice declared by queue item 2 in
``docs/development_work_queue/seed.jsonl`` (per
``docs/governance/roadmap_scope_status.md`` §3).

What this suite asserts:

* the five-rule decision ladder is deterministic and order-stable;
* each classified candidate emits exactly one routing reason
  record via :mod:`reporting.reason_records`;
* the snapshot is byte-deterministic given a frozen timestamp;
* the atomic-write allowlist refuses paths outside
  ``logs/intelligent_routing_minimal/``;
* the module is stdlib-only and imports no execution-side
  surfaces;
* the module does not modify frozen contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import intelligent_routing_minimal as irm
from reporting import reason_records as rr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _c(
    *,
    campaign_id: str,
    info_gain: float = 0.5,
    dwell: int = 0,
    dep_unmet: bool = False,
    budget: int = 100,
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "info_gain_estimate": info_gain,
        "dead_zone_dwell": dwell,
        "dependency_unmet": dep_unmet,
        "multiplicity_budget_remaining": budget,
    }


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_routing_decisions_match_reason_records_family() -> None:
    assert irm.ROUTING_DECISIONS == rr.DECISIONS_BY_KIND["routing"]


def test_input_candidate_keys_are_closed() -> None:
    assert irm.INPUT_CANDIDATE_KEYS == (
        "campaign_id",
        "info_gain_estimate",
        "dead_zone_dwell",
        "dependency_unmet",
        "multiplicity_budget_remaining",
    )


def test_output_candidate_keys_are_closed() -> None:
    assert irm.OUTPUT_CANDIDATE_KEYS == (
        "campaign_id",
        "decision",
        "priority_score",
        "rank",
        "reason_codes",
        "reason_text",
        "record_id",
    )


def test_thresholds_are_pinned() -> None:
    assert irm.DEFAULT_DEAD_ZONE_DWELL_THRESHOLD == 3
    assert irm.DEFAULT_LOW_INFO_GAIN_THRESHOLD == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_candidates_must_be_list_or_tuple() -> None:
    with pytest.raises(ValueError, match="list/tuple"):
        irm.validate_candidates(
            {"campaign_id": "x"}  # type: ignore[arg-type]
        )


def test_too_many_candidates_rejected() -> None:
    big = [
        _c(campaign_id=f"c_{i:04d}")
        for i in range(irm.MAX_CANDIDATES + 1)
    ]
    with pytest.raises(ValueError, match="too many"):
        irm.validate_candidates(big)


def test_missing_field_rejected() -> None:
    bad = _c(campaign_id="x")
    del bad["info_gain_estimate"]
    with pytest.raises(ValueError, match="missing fields"):
        irm.validate_candidates([bad])


def test_duplicate_campaign_id_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        irm.validate_candidates([_c(campaign_id="x"), _c(campaign_id="x")])


def test_dependency_unmet_must_be_bool() -> None:
    bad = _c(campaign_id="x")
    bad["dependency_unmet"] = "true"  # str, not bool
    with pytest.raises(ValueError, match="dependency_unmet"):
        irm.validate_candidates([bad])


# ---------------------------------------------------------------------------
# Decision ladder (deterministic; precedence-tested)
# ---------------------------------------------------------------------------


def test_prioritize_when_info_gain_high(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.5)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "prioritize"
    assert snap["items"][0]["reason_codes"] == ["info_gain_high"]
    assert snap["counts"]["by_decision"]["prioritize"] == 1
    assert snap["final_recommendation"] == "ready_for_implementation"


def test_defer_when_info_gain_below_threshold(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.10)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "defer"
    assert snap["items"][0]["reason_codes"] == ["info_gain_low"]


def test_dead_zone_suppress_when_dwell_at_threshold(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.9, dwell=3)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "dead_zone_suppress"
    assert snap["items"][0]["reason_codes"] == ["dead_zone_dwell_exceeded"]
    # Dead-zone-suppressed items carry zero priority_score.
    assert snap["items"][0]["priority_score"] == 0.0


def test_defer_when_dependency_unmet_overrides_high_info_gain(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [
            _c(
                campaign_id="c1",
                info_gain=0.99,
                dep_unmet=True,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "defer"
    assert snap["items"][0]["reason_codes"] == ["dependency_unmet"]


def test_reject_when_multiplicity_budget_zero(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.9, budget=0)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "reject"
    assert snap["items"][0]["reason_codes"] == [
        "multiplicity_budget_exceeded"
    ]
    assert snap["items"][0]["priority_score"] == 0.0


def test_reject_precedence_over_dependency_unmet(tmp_path: Path) -> None:
    """Budget exhaustion beats dependency-unmet (precedence rule 1)."""
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [
            _c(
                campaign_id="c1",
                info_gain=0.5,
                dep_unmet=True,
                budget=0,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "reject"


def test_dependency_unmet_precedence_over_dead_zone(tmp_path: Path) -> None:
    """Dependency unmet beats dead-zone (precedence rule 2)."""
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [
            _c(
                campaign_id="c1",
                info_gain=0.5,
                dwell=10,
                dep_unmet=True,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "defer"
    assert snap["items"][0]["reason_codes"] == ["dependency_unmet"]


def test_dead_zone_precedence_over_low_info_gain(tmp_path: Path) -> None:
    """Dead-zone beats low-info-gain defer (precedence rule 3)."""
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.05, dwell=5)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "dead_zone_suppress"


# ---------------------------------------------------------------------------
# Ranking and ordering (deterministic)
# ---------------------------------------------------------------------------


def test_ranking_orders_prioritized_first_then_by_score_then_by_id(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [
            _c(campaign_id="b_high", info_gain=0.8),
            _c(campaign_id="a_low", info_gain=0.10),
            _c(campaign_id="c_high", info_gain=0.8),
            _c(campaign_id="d_dead", info_gain=0.9, dwell=10),
            _c(campaign_id="e_reject", info_gain=0.9, budget=0),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    titles = [it["campaign_id"] for it in snap["items"]]
    # prioritize first (two of them, sorted by descending score then
    # ASC campaign_id), then defer, then dead_zone_suppress, then
    # reject.
    assert titles == [
        "b_high",
        "c_high",
        "a_low",
        "d_dead",
        "e_reject",
    ]
    assert snap["items"][0]["rank"] == 0
    assert snap["items"][-1]["rank"] == len(snap["items"]) - 1


def test_snapshot_is_byte_deterministic_with_frozen_timestamp(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    inputs = [
        _c(campaign_id="c1", info_gain=0.4),
        _c(campaign_id="c2", info_gain=0.2),
    ]
    a = irm.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    # The first run appends; the second run is idempotent on
    # record_id so the snapshot text is byte-identical.
    b = irm.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_empty_snapshot_returns_nothing_ready(tmp_path: Path) -> None:
    snap = irm.collect_snapshot(
        [], frozen_utc="2026-05-21T00:00:00Z"
    )
    assert snap["counts"]["total"] == 0
    assert snap["final_recommendation"] == "nothing_ready"
    assert snap["safe_to_execute"] is False


# ---------------------------------------------------------------------------
# Reason-record emission
# ---------------------------------------------------------------------------


def test_each_candidate_emits_exactly_one_routing_reason_record(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    inputs = [
        _c(campaign_id="c1", info_gain=0.9),
        _c(campaign_id="c2", info_gain=0.10),
        _c(campaign_id="c3", info_gain=0.9, dwell=10),
        _c(campaign_id="c4", info_gain=0.9, dep_unmet=True),
        _c(campaign_id="c5", info_gain=0.9, budget=0),
    ]
    snap = irm.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["counts"]["total"] == 5
    # One record per candidate in the routing JSONL.
    records = rr.read_kind("routing", artifact_dir=base)
    assert len({r["record_id"] for r in records}) == 5
    # record_id in snapshot matches the ledger record.
    snapshot_ids = {it["record_id"] for it in snap["items"]}
    ledger_ids = {r["record_id"] for r in records}
    assert snapshot_ids == ledger_ids


def test_record_ids_are_deterministic_across_runs(tmp_path: Path) -> None:
    base = tmp_path / "a" / "logs" / "reason_records"
    snap_a = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.5)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    # Different parent dir, same inputs → same record_id.
    base2 = tmp_path / "b" / "logs" / "reason_records"
    snap_b = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.5)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base2,
    )
    assert snap_a["items"][0]["record_id"] == snap_b["items"][0]["record_id"]


def test_record_ids_change_when_inputs_change(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    a = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.5)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    b = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.6)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert a["items"][0]["record_id"] != b["items"][0]["record_id"]


def test_emit_reason_records_false_does_not_write(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.5)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
        emit_reason_records=False,
    )
    # Snapshot still carries record_id, but no ledger file exists.
    assert "record_id" in snap["items"][0]
    routing_path = base / "routing_v1.jsonl"
    assert not routing_path.exists()


# ---------------------------------------------------------------------------
# Atomic-write allowlist
# ---------------------------------------------------------------------------


def test_write_outputs_into_allowlisted_path(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "intelligent_routing_minimal"
    snap = irm.collect_snapshot(
        [_c(campaign_id="c1", info_gain=0.7)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=tmp_path / "logs" / "reason_records",
    )
    out = irm.write_outputs(snap, artifact_dir=base)
    latest = base / "latest.json"
    assert latest.is_file()
    assert "intelligent_routing_minimal" in out["latest"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    """The atomic-write helper refuses any path that does not pass
    through ``logs/intelligent_routing_minimal/``."""
    bad = tmp_path / "evil_dir"
    bad.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="outside allowlist"):
        irm._validate_write_target(bad / "latest.json")


# ---------------------------------------------------------------------------
# Module purity / no execution-side imports
# ---------------------------------------------------------------------------


def test_module_is_stdlib_only_in_source() -> None:
    """No subprocess / socket / requests / urllib imports."""
    src = Path(irm.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
    )
    for needle in forbidden:
        assert (
            needle not in src
        ), f"intelligent_routing_minimal imports forbidden: {needle}"


def test_module_does_not_import_execution_surfaces() -> None:
    src = Path(irm.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "agent.execution",
        "agent.risk",
        "automation.live",
        "automation.broker",
        "broker.",
        "execution.live",
        "live.",
        "paper.",
        "shadow.",
        "trading.",
    )
    for needle in forbidden:
        assert (
            needle not in src
        ), f"intelligent_routing_minimal imports forbidden: {needle}"


def test_safe_to_execute_is_hardcoded_false() -> None:
    snap = irm.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["safe_to_execute"] is False


def test_mode_is_dry_run() -> None:
    snap = irm.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["mode"] == "dry-run"


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_status_returns_not_available_when_no_snapshot(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Redirect ARTIFACT_DIR to a temp dir for the duration.
    monkeypatch.setattr(
        irm,
        "ARTIFACT_LATEST",
        tmp_path / "logs" / "intelligent_routing_minimal" / "latest.json",
    )
    rc = irm.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["final_recommendation"] == "not_available"


def test_cli_no_write_does_not_write_artifacts(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = irm.main(["--no-write", "--frozen-utc", "2026-05-21T00:00:00Z"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["counts"]["total"] == 0
    assert parsed["safe_to_execute"] is False
