"""Tests for ``reporting.reason_records``.

Pins invariants RR-I1..RR-I10 from
``docs/governance/reason_records.md`` §7 and the schema from
``docs/governance/reason_records/schema.v1.md``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import reason_records as rr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_routing_record(
    *, subject_id: str = "campaign_001", frozen_utc: str = "2026-05-21T00:00:00Z"
) -> dict[str, Any]:
    inputs = {"data_window": "2026Q1", "campaign_id": subject_id}
    return rr.build_record(
        decision_kind=rr.DECISION_KIND_ROUTING,
        subject_id=subject_id,
        decision="prioritize",
        reason_codes=["info_gain_high"],
        reason_text="High expected information gain.",
        inputs=inputs,
        frozen_utc=frozen_utc,
    )


def _valid_scoring_record(
    *, subject_id: str = "candidate_xyz",
    frozen_utc: str = "2026-05-21T00:00:01Z",
) -> dict[str, Any]:
    inputs = {"data_window": "2026Q1", "candidate_id": subject_id}
    return rr.build_record(
        decision_kind=rr.DECISION_KIND_SCORING,
        subject_id=subject_id,
        decision="filter_null",
        reason_codes=["null_p_value_above_threshold"],
        reason_text="Did not beat null model.",
        inputs=inputs,
        frozen_utc=frozen_utc,
    )


# ---------------------------------------------------------------------------
# Closed vocabularies (RR-I5)
# ---------------------------------------------------------------------------


def test_decision_kinds_are_closed_and_ordered() -> None:
    assert rr.DECISION_KINDS == ("routing", "sampling", "scoring")


def test_decision_vocab_per_kind_matches_spec() -> None:
    assert rr.DECISIONS_BY_KIND["routing"] == (
        "prioritize",
        "dead_zone_suppress",
        "defer",
        "reject",
    )
    assert rr.DECISIONS_BY_KIND["sampling"] == (
        "stratify",
        "null_baseline",
        "exclude_region",
        "downsample",
        "upsample",
    )
    assert rr.DECISIONS_BY_KIND["scoring"] == (
        "keep",
        "filter_tail",
        "filter_entropy",
        "filter_null",
        "filter_cost",
        "undecided",
    )


def test_reason_codes_anchor_set_per_kind_matches_spec() -> None:
    assert rr.REASON_CODES_BY_KIND["routing"] == frozenset({
        "info_gain_high",
        "info_gain_low",
        "dead_zone_dwell_exceeded",
        "dependency_unmet",
        "multiplicity_budget_exceeded",
        "operator_directive",
    })
    assert "null_baseline_required" in rr.REASON_CODES_BY_KIND["sampling"]
    assert "null_p_value_above_threshold" in rr.REASON_CODES_BY_KIND["scoring"]


# ---------------------------------------------------------------------------
# Determinism: record_id (RR-I4)
# ---------------------------------------------------------------------------


def test_record_id_is_deterministic() -> None:
    a = rr.compute_record_id("routing", "campaign_001", "a" * 64)
    b = rr.compute_record_id("routing", "campaign_001", "a" * 64)
    assert a == b
    assert a.startswith("rr_")
    assert len(a) == len("rr_") + 16


def test_record_id_differs_on_any_input_change() -> None:
    a = rr.compute_record_id("routing", "campaign_001", "a" * 64)
    b = rr.compute_record_id("sampling", "campaign_001", "a" * 64)
    c = rr.compute_record_id("routing", "campaign_002", "a" * 64)
    d = rr.compute_record_id("routing", "campaign_001", "b" * 64)
    assert len({a, b, c, d}) == 4


# ---------------------------------------------------------------------------
# Schema validation (RR-I5, RR-I10)
# ---------------------------------------------------------------------------


def test_valid_routing_record_round_trips() -> None:
    rec = _valid_routing_record()
    assert set(rec.keys()) == set(rr.RECORD_SCHEMA_KEYS)
    assert rec["decision_kind"] == "routing"
    assert rec["schema_version"] == 1
    rr.validate_record(rec)


def test_unknown_decision_kind_rejected() -> None:
    rec = _valid_routing_record()
    rec["decision_kind"] = "unknown_family"
    rec["record_id"] = rr.compute_record_id(
        "unknown_family", rec["subject_id"], rec["inputs_digest"]
    )
    with pytest.raises(ValueError, match="decision_kind"):
        rr.validate_record(rec)


def test_unknown_decision_for_kind_rejected() -> None:
    rec = _valid_routing_record()
    # "filter_null" is a scoring decision, not routing.
    rec["decision"] = "filter_null"
    with pytest.raises(ValueError, match="decision"):
        rr.validate_record(rec)


def test_unknown_reason_code_for_kind_rejected() -> None:
    rec = _valid_routing_record()
    # "null_p_value_above_threshold" is a scoring reason_code.
    rec["reason_codes"] = ["null_p_value_above_threshold"]
    with pytest.raises(ValueError, match="reason_code"):
        rr.validate_record(rec)


def test_subject_id_too_long_rejected() -> None:
    long_sid = "x" * (rr.MAX_SUBJECT_ID_LEN + 1)
    with pytest.raises(ValueError, match="subject_id"):
        rr.build_record(
            decision_kind="routing",
            subject_id=long_sid,
            decision="prioritize",
            reason_codes=["info_gain_high"],
            reason_text="ok",
            inputs={"x": 1},
        )


def test_inputs_digest_must_be_64_hex() -> None:
    with pytest.raises(ValueError, match="inputs_digest"):
        rr.validate_record(
            {
                "decision": "prioritize",
                "decision_kind": "routing",
                "inputs_digest": "abc",  # wrong length
                "reason_codes": ["info_gain_high"],
                "reason_text": "ok",
                "record_id": "rr_0000000000000000",
                "schema_version": 1,
                "subject_id": "x",
                "ts_utc": "2026-05-21T00:00:00Z",
            }
        )


def test_record_id_mismatch_rejected() -> None:
    rec = _valid_routing_record()
    rec["record_id"] = "rr_deadbeef00000000"  # wrong
    with pytest.raises(ValueError, match="record_id mismatch"):
        rr.validate_record(rec)


def test_reason_text_too_long_rejected() -> None:
    with pytest.raises(ValueError, match="reason_text length"):
        rr.build_record(
            decision_kind="routing",
            subject_id="x",
            decision="prioritize",
            reason_codes=["info_gain_high"],
            reason_text="z" * (rr.MAX_REASON_TEXT_LEN + 1),
            inputs={"x": 1},
        )


def test_reason_text_with_secret_pattern_rejected() -> None:
    with pytest.raises(ValueError, match="secret"):
        rr.build_record(
            decision_kind="routing",
            subject_id="x",
            decision="prioritize",
            reason_codes=["info_gain_high"],
            reason_text="leaking API_KEY=...",
            inputs={"x": 1},
        )


def test_schema_version_must_be_one() -> None:
    rec = _valid_routing_record()
    rec["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        rr.validate_record(rec)


def test_unexpected_extra_field_rejected() -> None:
    rec = _valid_routing_record()
    rec["new_field"] = "x"
    with pytest.raises(ValueError, match="unexpected fields"):
        rr.validate_record(rec)


def test_missing_field_rejected() -> None:
    rec = _valid_routing_record()
    del rec["reason_text"]
    with pytest.raises(ValueError, match="missing fields"):
        rr.validate_record(rec)


def test_ts_utc_must_parse() -> None:
    rec = _valid_routing_record()
    rec["ts_utc"] = "not a timestamp"
    with pytest.raises(ValueError, match="ts_utc"):
        rr.validate_record(rec)


def test_oversize_record_rejected() -> None:
    big_text = "x" * rr.MAX_REASON_TEXT_LEN  # boundary; not oversize alone
    rec = rr.build_record(
        decision_kind="routing",
        subject_id="x",
        decision="prioritize",
        reason_codes=["info_gain_high", "info_gain_low"],
        reason_text=big_text,
        inputs={"x": 1},
    )
    # Tamper to push past the byte budget.
    rec["reason_text"] = "y" * (rr.MAX_RECORD_BYTES + 1)
    with pytest.raises(ValueError):
        rr.validate_record(rec)


# ---------------------------------------------------------------------------
# Write API (RR-I1 append-only, RR-I2 idempotent, RR-I8 allowlist)
# ---------------------------------------------------------------------------


def test_append_creates_jsonl_with_one_line(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    rec = _valid_routing_record()
    out = rr.append(rec, artifact_dir=base)
    assert out["status"] == "appended"
    path = base / "routing_v1.jsonl"
    assert path.is_file()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 1
    assert json.loads(lines[0]) == rec


def test_append_is_idempotent_on_record_id(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    rec = _valid_routing_record()
    a = rr.append(rec, artifact_dir=base)
    b = rr.append(rec, artifact_dir=base)
    assert a["status"] == "appended"
    assert b["status"] == "skipped_duplicate"
    path = base / "routing_v1.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 1


def test_append_does_not_rewrite_existing_lines(tmp_path: Path) -> None:
    """RR-I1: existing bytes are preserved."""
    base = tmp_path / "logs" / "reason_records"
    a = _valid_routing_record(subject_id="campaign_001")
    b = _valid_routing_record(
        subject_id="campaign_002", frozen_utc="2026-05-21T00:00:02Z"
    )
    rr.append(a, artifact_dir=base)
    path = base / "routing_v1.jsonl"
    before = path.read_bytes()
    rr.append(b, artifact_dir=base)
    after = path.read_bytes()
    assert after.startswith(before)
    assert len(after) > len(before)


def test_append_routes_to_per_kind_jsonl(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    routing = _valid_routing_record()
    scoring = _valid_scoring_record()
    rr.append(routing, artifact_dir=base)
    rr.append(scoring, artifact_dir=base)
    assert (base / "routing_v1.jsonl").is_file()
    assert (base / "scoring_v1.jsonl").is_file()
    routing_lines = (
        (base / "routing_v1.jsonl").read_text(encoding="utf-8").splitlines()
    )
    scoring_lines = (
        (base / "scoring_v1.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len([s for s in routing_lines if s]) == 1
    assert len([s for s in scoring_lines if s]) == 1


def test_append_writes_manifest(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    rec = _valid_routing_record()
    rr.append(rec, artifact_dir=base)
    manifest_path = base / "manifest.v1.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["total_records"] == 1
    assert manifest["by_kind"]["routing"] == 1
    assert manifest["note"] == "records_present"


def test_append_refuses_write_outside_allowlist(tmp_path: Path) -> None:
    """RR-I8: write target must contain the allowlist substring."""
    # The atomic-write allowlist key is "logs/reason_records/". A
    # path that does not contain that substring is refused.
    bad = tmp_path / "evil_dir" / "routing_v1.jsonl"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="outside allowlist"):
        rr._validate_write_target(bad)


# ---------------------------------------------------------------------------
# Read API (RR-I7 reader purity)
# ---------------------------------------------------------------------------


def test_read_kind_filters_by_subject_id(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    a = _valid_routing_record(subject_id="campaign_001")
    b = _valid_routing_record(
        subject_id="campaign_002", frozen_utc="2026-05-21T00:00:02Z"
    )
    rr.append(a, artifact_dir=base)
    rr.append(b, artifact_dir=base)
    only_a = rr.read_kind("routing", subject_id="campaign_001", artifact_dir=base)
    assert len(only_a) == 1
    assert only_a[0]["subject_id"] == "campaign_001"


def test_fused_for_subject_unions_across_kinds(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    routing = _valid_routing_record(subject_id="campaign_001")
    scoring = rr.build_record(
        decision_kind="scoring",
        subject_id="campaign_001",
        decision="keep",
        reason_codes=["dsr_threshold_pass"],
        reason_text="Pass.",
        inputs={"x": 2},
        frozen_utc="2026-05-21T00:00:03Z",
    )
    rr.append(routing, artifact_dir=base)
    rr.append(scoring, artifact_dir=base)
    fused = rr.fused_for_subject("campaign_001", artifact_dir=base)
    assert len(fused) == 2
    # Ordered by ts_utc ascending.
    assert fused[0]["ts_utc"] <= fused[1]["ts_utc"]


def test_collect_manifest_aggregates_correctly(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    rr.append(_valid_routing_record(subject_id="c001"), artifact_dir=base)
    rr.append(
        _valid_routing_record(
            subject_id="c002", frozen_utc="2026-05-21T00:00:05Z"
        ),
        artifact_dir=base,
    )
    rr.append(_valid_scoring_record(subject_id="c001"), artifact_dir=base)
    m = rr.collect_manifest(
        artifact_dir=base, frozen_utc="2026-05-21T01:00:00Z"
    )
    assert m["total_records"] == 3
    assert m["by_kind"]["routing"] == 2
    assert m["by_kind"]["scoring"] == 1
    assert m["by_decision"]["routing"]["prioritize"] == 2
    assert m["by_decision"]["scoring"]["filter_null"] == 1
    assert m["by_subject_id_top"]["c001"] == 2


def test_collect_manifest_empty_returns_no_records_note(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "reason_records"
    m = rr.collect_manifest(
        artifact_dir=base, frozen_utc="2026-05-21T01:00:00Z"
    )
    assert m["total_records"] == 0
    assert m["note"] == "no_records"
    assert m["by_kind"] == {"routing": 0, "sampling": 0, "scoring": 0}


def test_write_manifest_materialises_empty_manifest_without_records(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    manifest = rr.write_manifest(
        artifact_dir=base,
        frozen_utc="2026-05-21T01:00:00Z",
    )
    manifest_path = base / "manifest.v1.json"
    assert manifest_path.is_file()
    assert manifest["total_records"] == 0
    assert manifest["note"] == "no_records"
    assert not (base / "routing_v1.jsonl").exists()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted == manifest


# ---------------------------------------------------------------------------
# Reader purity + execution-import deny (RR-I7, RR-I9)
# ---------------------------------------------------------------------------


def test_module_is_stdlib_only_in_source() -> None:
    """RR-I7: no subprocess / socket / requests / gh / git imports."""
    src = (
        Path(rr.__file__)
        .resolve()
        .read_text(encoding="utf-8")
    )
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
        assert needle not in src, f"reason_records imports forbidden: {needle}"


def test_module_does_not_import_execution_surfaces() -> None:
    """RR-I9: no execution-side imports."""
    src = (
        Path(rr.__file__)
        .resolve()
        .read_text(encoding="utf-8")
    )
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
        assert needle not in src, f"reason_records imports forbidden: {needle}"


# ---------------------------------------------------------------------------
# Frozen contracts (RR-I8 negative)
# ---------------------------------------------------------------------------


def test_write_prefix_does_not_resolve_into_research_or_strategy(
    tmp_path: Path,
) -> None:
    """Explicitly assert that a path resolving into the canonical
    frozen-contract files cannot pass the allowlist."""
    with pytest.raises(ValueError):
        rr._validate_write_target(
            tmp_path / "research" / "research_latest.json"
        )
    with pytest.raises(ValueError):
        rr._validate_write_target(
            tmp_path / "research" / "strategy_matrix.csv"
        )
