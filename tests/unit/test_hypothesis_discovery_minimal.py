"""Tests for minimal v3.15.19 Hypothesis Discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import reason_records as rr
from reporting import hypothesis_discovery_summary as hds
from research.hypothesis_discovery import behavior_catalog as bc
from research.hypothesis_discovery import behavior_hypotheses as bh
from research.hypothesis_discovery import campaign_seed_proposer as csp
from research.hypothesis_discovery import opportunity_scoring as oscore
from research.hypothesis_discovery import preset_feasibility as pf


def _diag(
    *,
    null_margin: float = 0.80,
    tail: float = 0.10,
    entropy: float = 0.10,
    quorum: int = 3,
    budget: int = 10,
) -> dict[str, Any]:
    return {
        "null_model_beat_margin": null_margin,
        "tail_fragility_score": tail,
        "entropy_conflict_score": entropy,
        "evidence_quorum_count": quorum,
        "multiplicity_budget_remaining": budget,
    }


def test_behavior_catalog_is_closed_and_behavior_first() -> None:
    assert bc.BEHAVIOR_FAMILIES == (
        "trend_pullback",
        "volatility_breakout",
    )
    payload = bc.behavior_catalog_payload()
    families = [row["behavior_family"] for row in payload["behaviors"]]
    assert families == sorted(families)
    assert {row["strategy_family"] for row in payload["behaviors"]} == {
        "trend_pullback",
        "volatility_compression_breakout",
    }


def test_behavior_hypotheses_are_active_discovery_only() -> None:
    rows = bh.build_behavior_hypotheses()
    assert [row.hypothesis_id for row in rows] == [
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    ]
    assert all(row.status == "active_discovery" for row in rows)
    assert all(row.strategy_mapping_ref for row in rows)


def test_preset_feasibility_uses_existing_preset_bridge() -> None:
    feasible = pf.evaluate_preset_feasibility("trend_pullback_v1")
    assert feasible.feasible is True
    assert feasible.preset_names == ("trend_pullback_crypto_1h",)
    assert feasible.preset_feasibility_ref == "preset:trend_pullback_crypto_1h"

    missing = pf.evaluate_preset_feasibility("unknown_hypothesis")
    assert missing.feasible is False
    assert missing.preset_feasibility_ref == "preset:none"


def test_score_axiom_deterministic() -> None:
    inputs = oscore.normalise_inputs(_diag(), preset_feasible=True)
    a = oscore.opportunity_probability_score(inputs)
    b = oscore.opportunity_probability_score(dict(reversed(list(inputs.items()))))
    assert a == b


def test_score_axiom_bounded() -> None:
    bad = oscore.normalise_inputs(
        _diag(null_margin=99.0, tail=-1.0, entropy=42.0, quorum=99, budget=99),
        preset_feasible=True,
    )
    score = oscore.opportunity_probability_score(bad)
    assert 0.0 <= score <= 1.0


def test_score_axiom_monotone_positive_inputs() -> None:
    base = oscore.normalise_inputs(
        _diag(null_margin=0.20, quorum=1, budget=2),
        preset_feasible=True,
    )
    higher_null = dict(base)
    higher_null["null_model_beat_margin"] = 0.60
    higher_quorum = dict(base)
    higher_quorum["evidence_quorum_count"] = 3
    higher_budget = dict(base)
    higher_budget["multiplicity_budget_remaining"] = 10

    base_score = oscore.opportunity_probability_score(base)
    assert oscore.opportunity_probability_score(higher_null) >= base_score
    assert oscore.opportunity_probability_score(higher_quorum) >= base_score
    assert oscore.opportunity_probability_score(higher_budget) >= base_score


def test_score_axiom_monotone_negative_inputs() -> None:
    base = oscore.normalise_inputs(
        _diag(tail=0.10, entropy=0.10),
        preset_feasible=True,
    )
    higher_tail = dict(base)
    higher_tail["tail_fragility_score"] = 0.70
    higher_entropy = dict(base)
    higher_entropy["entropy_conflict_score"] = 0.70

    base_score = oscore.opportunity_probability_score(base)
    assert oscore.opportunity_probability_score(higher_tail) <= base_score
    assert oscore.opportunity_probability_score(higher_entropy) <= base_score


def test_score_axiom_independent_of_execution_side_state() -> None:
    src = Path(oscore.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "research_latest.json",
        "strategy_matrix.csv",
        "agent.execution",
        "agent.risk",
        "broker.",
        "live.",
        "paper.",
        "shadow.",
        "trading.",
    )
    for needle in forbidden:
        assert needle not in src


def test_score_axiom_inspectable_reason_record(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = csp.collect_snapshot(
        {"trend_pullback_v1": _diag()},
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=base,
    )
    records = rr.read_kind("scoring", artifact_dir=base)
    assert records
    ids = {r["record_id"] for r in records}
    assert snap["items"][0]["score"]["scoring_reason_record_id"] in ids
    assert records[0]["decision_kind"] == "scoring"


def test_score_axiom_noise_equivalence_on_identical_surrogate_inputs() -> None:
    surrogate = oscore.normalise_inputs(
        _diag(null_margin=0.25, tail=0.50, entropy=0.50, quorum=1, budget=5),
        preset_feasible=True,
    )
    shuffled_surrogate = dict(reversed(list(surrogate.items())))
    assert oscore.opportunity_probability_score(
        surrogate
    ) == oscore.opportunity_probability_score(shuffled_surrogate)


def test_diagnostics_filter_do_not_seed_when_null_fails(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    snap = csp.collect_snapshot(
        {"trend_pullback_v1": _diag(null_margin=0.0)},
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=base,
    )
    item = [
        row for row in snap["items"]
        if row["hypothesis_id"] == "trend_pullback_v1"
    ][0]
    assert item["score"]["decision"] == "filter_null"
    assert item["proposal_emitted"] is False
    assert all(
        seed["strategy_mapping_ref"] != item["strategy_mapping_ref"]
        for seed in snap["seeds"]
    )


def test_tail_and_entropy_are_filters_not_seed_sources(tmp_path: Path) -> None:
    snap_tail = csp.collect_snapshot(
        {"trend_pullback_v1": _diag(tail=0.99)},
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=tmp_path / "a" / "logs" / "reason_records",
    )
    row_tail = [
        row for row in snap_tail["items"]
        if row["hypothesis_id"] == "trend_pullback_v1"
    ][0]
    assert row_tail["score"]["decision"] == "filter_tail"

    snap_entropy = csp.collect_snapshot(
        {"trend_pullback_v1": _diag(entropy=0.99)},
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=tmp_path / "b" / "logs" / "reason_records",
    )
    row_entropy = [
        row for row in snap_entropy["items"]
        if row["hypothesis_id"] == "trend_pullback_v1"
    ][0]
    assert row_entropy["score"]["decision"] == "filter_entropy"


def test_snapshot_emits_proposal_only_seeds_with_adr_fields(
    tmp_path: Path,
) -> None:
    snap = csp.collect_snapshot(
        {
            "trend_pullback_v1": _diag(),
            "volatility_compression_breakout_v0": _diag(),
        },
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
    )
    assert snap["safe_to_execute"] is False
    assert snap["proposal_only"] is True
    assert snap["score_semantics"] == "expected_research_value_not_probability"
    assert snap["counts"]["seeds"] == 2
    required = {
        "seed_id",
        "generated_at_utc",
        "behavior_family",
        "strategy_mapping_ref",
        "preset_feasibility_ref",
        "opportunity_probability_score",
        "required_diagnostics",
        "required_null_model",
        "multiplicity_ledger_event_id",
        "scoring_reason_record_id",
        "schema_version",
    }
    for seed in snap["seeds"]:
        assert required.issubset(seed.keys())
        assert seed["schema_version"] == "v1"
        assert seed["required_diagnostics"] == list(oscore.ACTIVE_DIAGNOSTICS)
        assert 0.0 <= seed["opportunity_probability_score"] <= 1.0
        assert str(seed["multiplicity_ledger_event_id"]).startswith(
            "ml_pending_"
        )


def test_snapshot_is_byte_deterministic_with_frozen_timestamp(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    inputs = {"trend_pullback_v1": _diag()}
    a = csp.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=base,
    )
    b = csp.collect_snapshot(
        inputs,
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=base,
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_seed_log_is_append_only_and_idempotent(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "hypothesis_discovery_minimal"
    snap = csp.collect_snapshot(
        {"trend_pullback_v1": _diag()},
        frozen_utc="2026-05-21T00:00:00Z",
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
        emit_reason_records=False,
    )
    csp.write_outputs(snap, artifact_dir=base)
    csp.write_outputs(snap, artifact_dir=base)
    lines = (base / "seeds_v1.jsonl").read_text(encoding="utf-8").splitlines()
    seed_ids = [json.loads(line)["seed_id"] for line in lines]
    assert len(seed_ids) == len(set(seed_ids)) == snap["counts"]["seeds"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside allowlist"):
        csp._validate_write_target(tmp_path / "not_logs" / "latest.json")


def test_summary_reports_not_available_when_no_snapshot(tmp_path: Path) -> None:
    summary = hds.collect_summary(tmp_path / "missing.json")
    assert summary["available"] is False
    assert summary["safe_to_execute"] is False
    assert summary["proposal_only"] is True


def test_module_sources_do_not_import_execution_surfaces() -> None:
    modules = [bc, bh, pf, oscore, csp, hds]
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
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
    for module in modules:
        src = Path(module.__file__).resolve().read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in src, f"{module.__name__} contains {needle}"


def test_cli_summary_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    rc = hds.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["safe_to_execute"] is False
