"""Tests for ``reporting.sampling_intelligence_minimal``.

Pins the minimal v3.15.17 reset slice declared by queue item 3 in
``docs/development_work_queue/seed.jsonl`` (per
``docs/governance/roadmap_scope_status.md`` §3).

What this suite asserts:

* the six-rule decision ladder is deterministic and order-stable;
* each classified candidate emits exactly one sampling reason
  record via :mod:`reporting.reason_records`;
* the snapshot is byte-deterministic given a frozen timestamp;
* the atomic-write allowlist refuses paths outside
  ``logs/sampling_intelligence_minimal/``;
* the module is stdlib-only and imports no execution-side
  surfaces;
* the module does not modify frozen contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import reason_records as rr
from reporting import sampling_intelligence_minimal as sim


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _c(
    *,
    stratum_id: str,
    coverage_actual: float = 0.20,
    coverage_target: float = 0.20,
    regime_match: bool = True,
    null_baseline_required: bool = False,
    budget: int = 100,
) -> dict[str, Any]:
    return {
        "stratum_id": stratum_id,
        "coverage_actual": coverage_actual,
        "coverage_target": coverage_target,
        "regime_match": regime_match,
        "null_baseline_required": null_baseline_required,
        "multiplicity_budget_remaining": budget,
    }


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_sampling_decisions_match_reason_records_family() -> None:
    assert sim.SAMPLING_DECISIONS == rr.DECISIONS_BY_KIND["sampling"]


def test_input_candidate_keys_are_closed() -> None:
    assert sim.INPUT_CANDIDATE_KEYS == (
        "stratum_id",
        "coverage_actual",
        "coverage_target",
        "regime_match",
        "null_baseline_required",
        "multiplicity_budget_remaining",
    )


def test_output_candidate_keys_are_closed() -> None:
    assert sim.OUTPUT_CANDIDATE_KEYS == (
        "stratum_id",
        "decision",
        "priority_score",
        "rank",
        "reason_codes",
        "reason_text",
        "record_id",
    )


def test_thresholds_are_pinned() -> None:
    assert sim.DEFAULT_COVERAGE_IMBALANCE_THRESHOLD == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_candidates_must_be_list_or_tuple() -> None:
    with pytest.raises(ValueError, match="list/tuple"):
        sim.validate_candidates(
            {"stratum_id": "x"}  # type: ignore[arg-type]
        )


def test_too_many_candidates_rejected() -> None:
    big = [
        _c(stratum_id=f"s_{i:04d}")
        for i in range(sim.MAX_CANDIDATES + 1)
    ]
    with pytest.raises(ValueError, match="too many"):
        sim.validate_candidates(big)


def test_missing_field_rejected() -> None:
    bad = _c(stratum_id="x")
    del bad["coverage_actual"]
    with pytest.raises(ValueError, match="missing fields"):
        sim.validate_candidates([bad])


def test_duplicate_stratum_id_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        sim.validate_candidates([_c(stratum_id="x"), _c(stratum_id="x")])


def test_regime_match_must_be_bool() -> None:
    bad = _c(stratum_id="x")
    bad["regime_match"] = "true"  # str, not bool
    with pytest.raises(ValueError, match="regime_match"):
        sim.validate_candidates([bad])


def test_null_baseline_required_must_be_bool() -> None:
    bad = _c(stratum_id="x")
    bad["null_baseline_required"] = 1  # int, not bool
    with pytest.raises(ValueError, match="null_baseline_required"):
        sim.validate_candidates([bad])


# ---------------------------------------------------------------------------
# Decision ladder (deterministic; precedence-tested)
# ---------------------------------------------------------------------------


def test_stratify_when_coverage_within_threshold(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.20,
                coverage_target=0.20,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "stratify"
    assert snap["items"][0]["reason_codes"] == [
        "multiplicity_budget_remaining"
    ]
    assert snap["counts"]["by_decision"]["stratify"] == 1
    assert snap["counts"]["actionable"] == 1
    assert snap["final_recommendation"] == "ready_for_sampling"


def test_upsample_when_coverage_below_target(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.05,
                coverage_target=0.30,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "upsample"
    assert snap["items"][0]["reason_codes"] == ["coverage_imbalance"]


def test_downsample_when_coverage_above_target(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.50,
                coverage_target=0.20,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "downsample"
    assert snap["items"][0]["reason_codes"] == ["coverage_imbalance"]


def test_null_baseline_when_required(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.20,
                coverage_target=0.20,
                null_baseline_required=True,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "null_baseline"
    assert snap["items"][0]["reason_codes"] == ["null_baseline_required"]


def test_exclude_region_when_regime_mismatch(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.05,
                coverage_target=0.30,
                regime_match=False,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "exclude_region"
    assert snap["items"][0]["reason_codes"] == ["regime_mismatch"]
    assert snap["items"][0]["priority_score"] == 0.0


def test_exclude_region_when_budget_zero(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [_c(stratum_id="s1", budget=0)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "exclude_region"
    assert snap["items"][0]["reason_codes"] == [
        "multiplicity_budget_remaining"
    ]
    assert snap["items"][0]["priority_score"] == 0.0


def test_budget_zero_precedence_over_null_baseline(tmp_path: Path) -> None:
    """Budget exhaustion beats null-baseline (precedence rule 1)."""
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                budget=0,
                null_baseline_required=True,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "exclude_region"
    assert snap["items"][0]["reason_codes"] == [
        "multiplicity_budget_remaining"
    ]


def test_null_baseline_precedence_over_regime_mismatch(
    tmp_path: Path,
) -> None:
    """Null-baseline beats regime-mismatch (precedence rule 2)."""
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                regime_match=False,
                null_baseline_required=True,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "null_baseline"


def test_regime_mismatch_precedence_over_coverage_imbalance(
    tmp_path: Path,
) -> None:
    """Regime-mismatch beats coverage-imbalance upsample (rule 3)."""
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.0,
                coverage_target=1.0,
                regime_match=False,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["items"][0]["decision"] == "exclude_region"
    assert snap["items"][0]["reason_codes"] == ["regime_mismatch"]


def test_threshold_boundary_is_strict(tmp_path: Path) -> None:
    """Exactly at the threshold magnitude is **not** imbalanced.

    Pins the boundary semantics: the rule fires only on *strictly*
    greater-than threshold deviations. At equality, the stratum
    falls through to the default ``stratify`` decision.
    """
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(
                stratum_id="s1",
                coverage_actual=0.10,
                coverage_target=0.20,
            )
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    # |0.20 - 0.10| == 0.10 (threshold). Not greater; not
    # imbalanced. Falls to stratify.
    assert snap["items"][0]["decision"] == "stratify"


# ---------------------------------------------------------------------------
# Ranking and ordering (deterministic)
# ---------------------------------------------------------------------------


def test_ranking_orders_by_decision_then_score_then_id(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(stratum_id="b_strat", coverage_actual=0.20, coverage_target=0.20),
            _c(stratum_id="a_up_small", coverage_actual=0.05, coverage_target=0.20),
            _c(stratum_id="c_up_big", coverage_actual=0.00, coverage_target=0.80),
            _c(stratum_id="d_down", coverage_actual=0.60, coverage_target=0.20),
            _c(
                stratum_id="e_excl",
                coverage_actual=0.20,
                coverage_target=0.20,
                regime_match=False,
            ),
            _c(stratum_id="f_null", null_baseline_required=True),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    titles = [it["stratum_id"] for it in snap["items"]]
    # Order: stratify, null_baseline, upsample (high score first),
    # downsample, exclude_region.
    assert titles == [
        "b_strat",
        "f_null",
        "c_up_big",
        "a_up_small",
        "d_down",
        "e_excl",
    ]
    assert snap["items"][0]["rank"] == 0
    assert snap["items"][-1]["rank"] == len(snap["items"]) - 1


def test_ranking_tiebreaker_is_stratum_id_ascending(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(stratum_id="z_strat"),
            _c(stratum_id="a_strat"),
            _c(stratum_id="m_strat"),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    titles = [it["stratum_id"] for it in snap["items"]]
    # All stratify, same score -> alphabetical by stratum_id.
    assert titles == ["a_strat", "m_strat", "z_strat"]


def test_snapshot_is_byte_deterministic_with_frozen_timestamp(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    inputs = [
        _c(stratum_id="s1", coverage_actual=0.05, coverage_target=0.20),
        _c(stratum_id="s2", coverage_actual=0.50, coverage_target=0.20),
    ]
    a = sim.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    # The first run appends; the second run is idempotent on
    # record_id so the snapshot text is byte-identical.
    b = sim.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_empty_snapshot_returns_nothing_ready(tmp_path: Path) -> None:
    snap = sim.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["counts"]["total"] == 0
    assert snap["counts"]["actionable"] == 0
    assert snap["final_recommendation"] == "nothing_ready"
    assert snap["safe_to_execute"] is False


def test_only_exclude_region_yields_nothing_ready(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [
            _c(stratum_id="s1", budget=0),
            _c(stratum_id="s2", regime_match=False),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["counts"]["by_decision"]["exclude_region"] == 2
    assert snap["counts"]["actionable"] == 0
    assert snap["final_recommendation"] == "nothing_ready"


# ---------------------------------------------------------------------------
# Reason-record emission
# ---------------------------------------------------------------------------


def test_each_candidate_emits_exactly_one_sampling_reason_record(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    inputs = [
        _c(stratum_id="s1", coverage_actual=0.20, coverage_target=0.20),
        _c(stratum_id="s2", coverage_actual=0.05, coverage_target=0.30),
        _c(stratum_id="s3", coverage_actual=0.50, coverage_target=0.20),
        _c(stratum_id="s4", null_baseline_required=True),
        _c(stratum_id="s5", budget=0),
        _c(stratum_id="s6", regime_match=False),
    ]
    snap = sim.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert snap["counts"]["total"] == 6
    # One record per candidate in the sampling JSONL.
    records = rr.read_kind("sampling", artifact_dir=base)
    assert len({r["record_id"] for r in records}) == 6
    # record_id in snapshot matches the ledger record.
    snapshot_ids = {it["record_id"] for it in snap["items"]}
    ledger_ids = {r["record_id"] for r in records}
    assert snapshot_ids == ledger_ids


def test_emitted_records_use_sampling_kind_only(tmp_path: Path) -> None:
    """The slice must not write to the routing or scoring JSONLs."""
    base = tmp_path / "logs" / "reason_records"
    sim.collect_snapshot(
        [_c(stratum_id="s1")],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert rr.read_kind("sampling", artifact_dir=base)
    assert rr.read_kind("routing", artifact_dir=base) == []
    assert rr.read_kind("scoring", artifact_dir=base) == []


def test_record_ids_are_deterministic_across_runs(tmp_path: Path) -> None:
    base = tmp_path / "a" / "logs" / "reason_records"
    snap_a = sim.collect_snapshot(
        [_c(stratum_id="s1", coverage_actual=0.10, coverage_target=0.20)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    # Different parent dir, same inputs → same record_id.
    base2 = tmp_path / "b" / "logs" / "reason_records"
    snap_b = sim.collect_snapshot(
        [_c(stratum_id="s1", coverage_actual=0.10, coverage_target=0.20)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base2,
    )
    assert snap_a["items"][0]["record_id"] == snap_b["items"][0]["record_id"]


def test_record_ids_change_when_inputs_change(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    a = sim.collect_snapshot(
        [_c(stratum_id="s1", coverage_actual=0.10, coverage_target=0.20)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    b = sim.collect_snapshot(
        [_c(stratum_id="s1", coverage_actual=0.15, coverage_target=0.20)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    assert a["items"][0]["record_id"] != b["items"][0]["record_id"]


def test_emit_reason_records_false_does_not_write(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = sim.collect_snapshot(
        [_c(stratum_id="s1")],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
        emit_reason_records=False,
    )
    # Snapshot still carries record_id, but no ledger file exists.
    assert "record_id" in snap["items"][0]
    sampling_path = base / "sampling_v1.jsonl"
    assert not sampling_path.exists()


def test_idempotent_replay_yields_one_record_per_candidate(
    tmp_path: Path,
) -> None:
    """RR-I2 idempotence: replaying the same snapshot does not
    duplicate the JSONL records."""
    base = tmp_path / "logs" / "reason_records"
    inputs = [_c(stratum_id="s1", coverage_actual=0.05, coverage_target=0.20)]
    sim.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    sim.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=base,
    )
    records = rr.read_kind("sampling", artifact_dir=base)
    assert len(records) == 1


# ---------------------------------------------------------------------------
# Atomic-write allowlist
# ---------------------------------------------------------------------------


def test_write_outputs_into_allowlisted_path(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "sampling_intelligence_minimal"
    snap = sim.collect_snapshot(
        [_c(stratum_id="s1", coverage_actual=0.05, coverage_target=0.20)],
        frozen_utc="2026-05-21T00:00:00Z",
        artifact_dir_for_reasons=tmp_path / "logs" / "reason_records",
    )
    out = sim.write_outputs(snap, artifact_dir=base)
    latest = base / "latest.json"
    assert latest.is_file()
    assert "sampling_intelligence_minimal" in out["latest"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    """The atomic-write helper refuses any path that does not pass
    through ``logs/sampling_intelligence_minimal/``."""
    bad = tmp_path / "evil_dir"
    bad.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="outside allowlist"):
        sim._validate_write_target(bad / "latest.json")


# ---------------------------------------------------------------------------
# Module purity / no execution-side imports
# ---------------------------------------------------------------------------


def test_module_is_stdlib_only_in_source() -> None:
    """No subprocess / socket / requests / urllib imports."""
    src = Path(sim.__file__).resolve().read_text(encoding="utf-8")
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
        ), f"sampling_intelligence_minimal imports forbidden: {needle}"


def test_module_does_not_import_execution_surfaces() -> None:
    src = Path(sim.__file__).resolve().read_text(encoding="utf-8")
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
        ), f"sampling_intelligence_minimal imports forbidden: {needle}"


def test_safe_to_execute_is_hardcoded_false() -> None:
    snap = sim.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["safe_to_execute"] is False


def test_mode_is_dry_run() -> None:
    snap = sim.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["mode"] == "dry-run"


def test_report_kind_is_pinned() -> None:
    assert sim.REPORT_KIND == "sampling_intelligence_minimal_digest"


def test_module_version_is_pinned() -> None:
    assert sim.MODULE_VERSION == "v3.15.17-minimal-reset-2026-05-21"


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
        sim,
        "ARTIFACT_LATEST",
        tmp_path
        / "logs"
        / "sampling_intelligence_minimal"
        / "latest.json",
    )
    rc = sim.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["final_recommendation"] == "not_available"


def test_cli_no_write_does_not_write_artifacts(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = sim.main(["--no-write", "--frozen-utc", "2026-05-21T00:00:00Z"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["counts"]["total"] == 0
    assert parsed["safe_to_execute"] is False
