"""Unit tests for A20c — Authority/Risk Classifier Integration.

Pins:

* Re-exported vocabularies match the canonical classifier verbatim
  (no second source of truth).
* Schema field tuples are exact and ordered.
* Every A20b unit receives an authority decision.
* Every ``expected_files`` and ``forbidden_files`` entry's per-file
  decision matches the verbatim output of
  ``reporting.execution_authority.classify(...)``.
* Aggregation is max-severity over the canonical decision ordering.
* Fail-closed: UNKNOWN risk -> NEEDS_HUMAN; empty expected_files
  -> NEEDS_HUMAN.
* Runtime / trading surfaces (broker, agent.risk, agent.execution,
  automation.live_gate) are never AUTO_ALLOWED.
* Frozen contracts are PERMANENTLY_DENIED.
* canonical_roadmap / canonical_policy_doc paths classify as
  NEEDS_HUMAN or stronger.
* Atomic write only under ``logs/roadmap_task_authority/``.
* No mutation of A20a or A20b artefacts (sha256 before/after).
* Deterministic byte-identical output for identical input with
  injected ``generated_at_utc``.
* Module source carries no forbidden imports / runtime tokens.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from reporting import execution_authority as ea
from reporting import roadmap_task_authority as rta
from reporting import roadmap_task_catalog as rtc
from reporting import roadmap_task_units as rtu


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T12:00:00Z"


@pytest.fixture
def snap() -> dict:
    return rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)


@pytest.fixture
def units_snap() -> dict:
    return rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)


@pytest.fixture
def catalog_snap() -> dict:
    return rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)


# ---------------------------------------------------------------------------
# Closed vocabularies — verbatim re-export from the canonical classifier
# ---------------------------------------------------------------------------


def test_decisions_are_verbatim_classifier_reexport() -> None:
    assert rta.DECISIONS == ea.DECISIONS


def test_risk_classes_are_verbatim_classifier_reexport() -> None:
    assert rta.RISK_CLASSES == ea.RISK_CLASSES


def test_severity_ordering_matches_decision_enum() -> None:
    assert rta._SEVERITY == {
        ea.DECISION_AUTO_ALLOWED: 0,
        ea.DECISION_NEEDS_HUMAN: 1,
        ea.DECISION_PERMANENTLY_DENIED: 2,
    }


def test_action_type_is_file_edit() -> None:
    # A20b units describe creating new tracked files; the modify
    # action passed to the classifier must be ``file_edit``.
    assert rta._ACTION_TYPE == "file_edit"
    assert rta._ACTION_TYPE in ea.ACTION_TYPES


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_per_file_decision_field_list_exact() -> None:
    assert rta.PER_FILE_DECISION_FIELDS == (
        "path",
        "action_type",
        "risk_class",
        "decision",
        "reason",
        "target_path_category",
    )


def test_unit_authority_decision_field_list_exact() -> None:
    assert rta.UNIT_AUTHORITY_DECISION_FIELDS == (
        "unit_id",
        "parent_task_id",
        "expected_files_decisions",
        "forbidden_files_decisions",
        "aggregate_decision",
        "aggregate_reason",
        "authority_hint_from_a20b",
        "classifier_schema_version",
        "classifier_module",
        "forbidden_surface_reasons",
    )


def test_unit_authority_projection_field_list_exact() -> None:
    assert rta.UNIT_AUTHORITY_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "source_catalog_module_version",
        "source_units_module_version",
        "authority_decisions",
        "classification_invariants",
    )


def test_every_authority_decision_has_every_field(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert set(d.keys()) == set(rta.UNIT_AUTHORITY_DECISION_FIELDS), d


def test_projection_carries_every_required_top_level_field(snap: dict) -> None:
    for field in rta.UNIT_AUTHORITY_PROJECTION_FIELDS:
        assert field in snap, field


def test_every_per_file_record_has_every_field(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        for rec in d["expected_files_decisions"]:
            assert set(rec.keys()) == set(rta.PER_FILE_DECISION_FIELDS), rec
        for rec in d["forbidden_files_decisions"]:
            assert set(rec.keys()) == set(rta.PER_FILE_DECISION_FIELDS), rec


# ---------------------------------------------------------------------------
# Coverage: every A20b unit receives an authority decision
# ---------------------------------------------------------------------------


def test_every_a20b_unit_receives_a_decision(
    snap: dict, units_snap: dict
) -> None:
    unit_ids = {u["id"] for u in units_snap["implementation_units"]}
    decided_ids = {d["unit_id"] for d in snap["authority_decisions"]}
    assert unit_ids == decided_ids


def test_decision_unit_ids_unique(snap: dict) -> None:
    ids = [d["unit_id"] for d in snap["authority_decisions"]]
    assert len(ids) == len(set(ids))


def test_every_decision_records_classifier_module(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["classifier_module"] == "reporting.execution_authority"
        assert d["classifier_schema_version"] == ea.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Per-file decisions are the verbatim classifier output (no second source)
# ---------------------------------------------------------------------------


def test_expected_file_decisions_match_classifier_verbatim(
    snap: dict, units_snap: dict
) -> None:
    units_by_id = {u["id"]: u for u in units_snap["implementation_units"]}
    for d in snap["authority_decisions"]:
        unit = units_by_id[d["unit_id"]]
        risk_class = (
            unit["risk_class"]
            if unit["risk_class"] in ea.RISK_CLASSES
            else ea.RISK_UNKNOWN
        )
        for rec in d["expected_files_decisions"]:
            canonical = ea.classify(
                action_type="file_edit",
                target_path=rec["path"],
                risk_class=risk_class,
            )
            assert rec["decision"] == canonical.decision, rec
            assert rec["reason"] == canonical.reason, rec
            assert (
                rec["target_path_category"] == canonical.target_path_category
            ), rec


def test_forbidden_file_decisions_match_classifier_verbatim(
    snap: dict, units_snap: dict
) -> None:
    units_by_id = {u["id"]: u for u in units_snap["implementation_units"]}
    for d in snap["authority_decisions"]:
        unit = units_by_id[d["unit_id"]]
        risk_class = (
            unit["risk_class"]
            if unit["risk_class"] in ea.RISK_CLASSES
            else ea.RISK_UNKNOWN
        )
        for rec in d["forbidden_files_decisions"]:
            canonical = ea.classify(
                action_type="file_edit",
                target_path=rec["path"],
                risk_class=risk_class,
            )
            assert rec["decision"] == canonical.decision, rec
            assert rec["reason"] == canonical.reason, rec
            assert (
                rec["target_path_category"] == canonical.target_path_category
            ), rec


def test_per_file_action_type_and_risk_class_are_consistent(
    snap: dict, units_snap: dict
) -> None:
    units_by_id = {u["id"]: u for u in units_snap["implementation_units"]}
    for d in snap["authority_decisions"]:
        unit = units_by_id[d["unit_id"]]
        expected_risk = (
            unit["risk_class"]
            if unit["risk_class"] in ea.RISK_CLASSES
            else ea.RISK_UNKNOWN
        )
        for rec in d["expected_files_decisions"] + d["forbidden_files_decisions"]:
            assert rec["action_type"] == "file_edit"
            assert rec["risk_class"] == expected_risk


# ---------------------------------------------------------------------------
# Aggregation rules
# ---------------------------------------------------------------------------


def test_aggregate_decision_is_in_canonical_decisions_enum(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["aggregate_decision"] in ea.DECISIONS


def test_aggregate_reason_is_in_canonical_reasons_enum(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["aggregate_reason"] in ea.REASONS, d


def test_aggregate_follows_max_severity_over_expected_files(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        if not d["expected_files_decisions"]:
            # Fail-closed branch is checked elsewhere.
            continue
        per_file_decisions = [
            rec["decision"] for rec in d["expected_files_decisions"]
        ]
        expected_aggregate = max(
            per_file_decisions, key=lambda v: rta._SEVERITY[v]
        )
        assert d["aggregate_decision"] == expected_aggregate, d


def test_any_permanently_denied_expected_file_drives_unit_to_denied() -> None:
    fake_unit = {
        "id": "syn_unit_denied",
        "roadmap_task_id": "phase_v3_15_16",
        "risk_class": "LOW",
        "expected_files": [
            "reporting/intelligent_routing_diagnostic_signals.py",
            "broker/foo.py",  # live_path -> PERMANENTLY_DENIED on modify
            "tests/unit/test_intelligent_routing_diagnostic_signals.py",
        ],
        "forbidden_files": [],
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "forbidden_surface_reasons": [],
    }
    decision = rta._decide_for_unit(fake_unit)
    assert decision["aggregate_decision"] == ea.DECISION_PERMANENTLY_DENIED
    assert decision["aggregate_reason"] == "denied_live_path_modification"


def test_any_needs_human_no_denied_drives_unit_to_needs_human() -> None:
    fake_unit = {
        "id": "syn_unit_needs_human",
        "roadmap_task_id": "phase_v3_15_16",
        "risk_class": "LOW",
        "expected_files": [
            "reporting/intelligent_routing_diagnostic_signals.py",  # auto-allowed
            "docs/governance/execution_authority.md",  # canonical_policy_doc -> NEEDS_HUMAN
        ],
        "forbidden_files": [],
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "forbidden_surface_reasons": [],
    }
    decision = rta._decide_for_unit(fake_unit)
    assert decision["aggregate_decision"] == ea.DECISION_NEEDS_HUMAN
    assert decision["aggregate_reason"] == "high_risk_canonical_policy_change"


def test_all_auto_allowed_drives_unit_to_auto_allowed() -> None:
    fake_unit = {
        "id": "syn_unit_auto",
        "roadmap_task_id": "phase_v3_15_16",
        "risk_class": "LOW",
        "expected_files": [
            "reporting/intelligent_routing_diagnostic_signals.py",
            "tests/unit/test_intelligent_routing_diagnostic_signals.py",
            "docs/governance/intelligent_routing_diagnostic_signals.md",
        ],
        "forbidden_files": [],
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "forbidden_surface_reasons": [],
    }
    decision = rta._decide_for_unit(fake_unit)
    assert decision["aggregate_decision"] == ea.DECISION_AUTO_ALLOWED


def test_empty_expected_files_falls_closed_to_needs_human() -> None:
    fake_unit = {
        "id": "syn_unit_empty",
        "roadmap_task_id": "phase_v3_15_16",
        "risk_class": "LOW",
        "expected_files": [],
        "forbidden_files": [],
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "forbidden_surface_reasons": [],
    }
    decision = rta._decide_for_unit(fake_unit)
    assert decision["aggregate_decision"] == ea.DECISION_NEEDS_HUMAN
    assert decision["aggregate_reason"] == "unknown_risk_or_target_fail_safe"


# ---------------------------------------------------------------------------
# UNKNOWN risk fails closed to NEEDS_HUMAN
# ---------------------------------------------------------------------------


def test_unknown_risk_class_falls_closed_to_needs_human() -> None:
    fake_unit = {
        "id": "syn_unit_unknown_risk",
        "roadmap_task_id": "phase_v3_15_16",
        "risk_class": "UNKNOWN",
        "expected_files": [
            "reporting/intelligent_routing_diagnostic_signals.py",
        ],
        "forbidden_files": [],
        "authority_hint": "NEEDS_HUMAN_CANDIDATE",
        "forbidden_surface_reasons": [],
    }
    decision = rta._decide_for_unit(fake_unit)
    assert decision["aggregate_decision"] == ea.DECISION_NEEDS_HUMAN
    assert decision["aggregate_reason"] == "unknown_risk_or_target_fail_safe"


def test_invalid_risk_string_is_coerced_to_unknown_and_fails_closed() -> None:
    fake_unit = {
        "id": "syn_unit_bad_risk",
        "roadmap_task_id": "phase_v3_15_16",
        "risk_class": "NOT_A_RISK_CLASS",
        "expected_files": [
            "reporting/intelligent_routing_diagnostic_signals.py",
        ],
        "forbidden_files": [],
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "forbidden_surface_reasons": [],
    }
    decision = rta._decide_for_unit(fake_unit)
    assert decision["aggregate_decision"] == ea.DECISION_NEEDS_HUMAN


# ---------------------------------------------------------------------------
# Runtime / trading surfaces never AUTO_ALLOWED
# ---------------------------------------------------------------------------


_NEVER_AUTO_ALLOWED_SAMPLES = (
    "broker/foo.py",
    "broker/x/y/z.py",
    "agent/risk/policy.py",
    "agent/execution/runner.py",
    "automation/live_gate.py",
    # Globs that A20b actually emits inside forbidden_files. The
    # classifier reads them as path strings and categorises them
    # by prefix.
    "broker/**",
    "agent/risk/**",
    "agent/execution/**",
)


@pytest.mark.parametrize("path", _NEVER_AUTO_ALLOWED_SAMPLES)
def test_runtime_trading_surface_is_never_auto_allowed_via_classifier(
    path: str,
) -> None:
    for risk_class in ea.RISK_CLASSES:
        decision = ea.classify(
            action_type="file_edit",
            target_path=path,
            risk_class=risk_class,
        )
        assert decision.decision != ea.DECISION_AUTO_ALLOWED, (
            path,
            risk_class,
            decision,
        )


_LIVE_PAPER_SHADOW_TRADING_GLOBS = (
    "live/**",
    "paper/**",
    "shadow/**",
    "trading/**",
    "execution/**",
)


@pytest.mark.parametrize("path", _LIVE_PAPER_SHADOW_TRADING_GLOBS)
def test_live_paper_shadow_trading_execution_paths_never_auto_allowed(
    path: str,
) -> None:
    """live/**, paper/**, shadow/**, trading/**, execution/** are not
    canonical ``live_path`` predicates in the classifier (those
    cover ``broker/**``, ``agent/risk/**``, ``agent/execution/**``,
    ``automation/live_gate.py``). The canonical classifier treats
    them as ``other`` -> ``NEEDS_HUMAN`` on every modify action,
    which still satisfies the 'never AUTO_ALLOWED' invariant.
    """
    for risk_class in ea.RISK_CLASSES:
        decision = ea.classify(
            action_type="file_edit",
            target_path=path,
            risk_class=risk_class,
        )
        assert decision.decision != ea.DECISION_AUTO_ALLOWED, (
            path,
            risk_class,
        )


def test_no_unit_in_main_aggregates_to_auto_allowed_on_a_runtime_surface(
    snap: dict,
) -> None:
    """Across every unit on main, no AUTO_ALLOWED aggregate may rest
    on a per-file decision against a broker / agent.risk /
    agent.execution / live_gate path. Catches a future A20b
    regression that would smuggle a runtime surface into
    expected_files."""
    runtime_categories = {"live_path"}
    for d in snap["authority_decisions"]:
        if d["aggregate_decision"] != ea.DECISION_AUTO_ALLOWED:
            continue
        for rec in d["expected_files_decisions"]:
            assert rec["target_path_category"] not in runtime_categories, rec


# ---------------------------------------------------------------------------
# Frozen contracts remain denied
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ],
)
def test_frozen_contract_paths_are_permanently_denied(path: str) -> None:
    for risk_class in ea.RISK_CLASSES:
        decision = ea.classify(
            action_type="file_edit",
            target_path=path,
            risk_class=risk_class,
        )
        assert decision.decision == ea.DECISION_PERMANENTLY_DENIED, (
            path,
            risk_class,
        )
        assert decision.reason == "denied_frozen_contract_mutation"


def test_no_unit_in_main_aggregates_to_auto_allowed_on_frozen_contract(
    snap: dict,
) -> None:
    for d in snap["authority_decisions"]:
        if d["aggregate_decision"] != ea.DECISION_AUTO_ALLOWED:
            continue
        for rec in d["expected_files_decisions"]:
            assert rec["target_path_category"] != "frozen_contract", rec


# ---------------------------------------------------------------------------
# Canonical roadmap / canonical policy doc paths are NEEDS_HUMAN or stronger
# ---------------------------------------------------------------------------


_CANONICAL_PROTECTED_SAMPLES = (
    "docs/governance/execution_authority.md",
    "docs/governance/no_touch_paths.md",
    "docs/governance/observability_security_hardening.md",
    "docs/roadmap/Roadmap v6.md",
    "docs/roadmap/autonomous_development.txt",
)


@pytest.mark.parametrize("path", _CANONICAL_PROTECTED_SAMPLES)
def test_canonical_roadmap_or_policy_path_is_needs_human_or_stronger(
    path: str,
) -> None:
    for risk_class in ea.RISK_CLASSES:
        decision = ea.classify(
            action_type="file_edit",
            target_path=path,
            risk_class=risk_class,
        )
        assert decision.decision in (
            ea.DECISION_NEEDS_HUMAN,
            ea.DECISION_PERMANENTLY_DENIED,
        ), (path, risk_class, decision)


# ---------------------------------------------------------------------------
# Authority-hint preservation (A20b hint is NOT authority)
# ---------------------------------------------------------------------------


def test_authority_hint_from_a20b_is_preserved(
    snap: dict, units_snap: dict
) -> None:
    units_by_id = {u["id"]: u for u in units_snap["implementation_units"]}
    for d in snap["authority_decisions"]:
        unit = units_by_id[d["unit_id"]]
        assert d["authority_hint_from_a20b"] == unit["authority_hint"]


def test_hint_never_overrides_classifier_aggregate(snap: dict) -> None:
    """The A20b hint is metadata only. A unit's aggregate_decision
    must be derivable purely from its expected_files_decisions via
    max-severity; the hint never enters the aggregation."""
    for d in snap["authority_decisions"]:
        if not d["expected_files_decisions"]:
            continue
        per_file_decisions = [
            rec["decision"] for rec in d["expected_files_decisions"]
        ]
        expected_aggregate = max(
            per_file_decisions, key=lambda v: rta._SEVERITY[v]
        )
        assert d["aggregate_decision"] == expected_aggregate


# ---------------------------------------------------------------------------
# Classification invariants
# ---------------------------------------------------------------------------


def test_invariants_flip_calls_execution_authority_classifier(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["calls_execution_authority_classifier"] is True


def test_invariants_flip_final_authority_classified(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["final_authority_classified"] is True


def test_invariants_pin_no_runtime_trading_authority(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["no_runtime_trading_authority"] is True


def test_invariants_pin_no_step5_runtime(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["no_step5_runtime"] is True
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_invariants_pin_no_level6(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["no_level6"] is True


def test_invariants_pin_no_production_merge_authority(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["no_production_merge_authority"] is True


def test_invariants_pin_writes_only_roadmap_task_authority_log(
    snap: dict,
) -> None:
    inv = snap["classification_invariants"]
    assert inv["writes_only_roadmap_task_authority_log"] is True


def test_invariants_pin_aac_and_next_buildable_not_implemented(
    snap: dict,
) -> None:
    inv = snap["classification_invariants"]
    # A20d / A20e are still pending.
    assert inv["aac_visibility_present"] is False
    assert inv["next_buildable_selector_present"] is False


def test_invariants_pin_no_seed_jsonl_writes(snap: dict) -> None:
    inv = snap["classification_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts() -> None:
    a = rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_authority_decisions_order_stable(snap: dict) -> None:
    sorted_pairs = [
        (d["parent_task_id"], d["unit_id"]) for d in snap["authority_decisions"]
    ]
    assert sorted_pairs == sorted(sorted_pairs)


def test_source_module_versions_match_upstream(
    snap: dict, units_snap: dict, catalog_snap: dict
) -> None:
    assert snap["source_units_module_version"] == units_snap["module_version"]
    assert snap["source_catalog_module_version"] == catalog_snap["module_version"]


# ---------------------------------------------------------------------------
# No upstream mutation (sha256 before/after)
# ---------------------------------------------------------------------------


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_collect_snapshot_does_not_mutate_a20a_artifact_in_memory() -> None:
    before = json.dumps(
        rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC),
        sort_keys=True,
    ).encode("utf-8")
    rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    after = json.dumps(
        rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC),
        sort_keys=True,
    ).encode("utf-8")
    assert _sha256(before) == _sha256(after)


def test_collect_snapshot_does_not_mutate_a20b_artifact_in_memory() -> None:
    before = json.dumps(
        rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC),
        sort_keys=True,
    ).encode("utf-8")
    rta.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    after = json.dumps(
        rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC),
        sort_keys=True,
    ).encode("utf-8")
    assert _sha256(before) == _sha256(after)


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rta._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(tmp_path: Path) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rta._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_task_authority" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rta._atomic_write_json(good, {"x": 1})
    assert good.is_file()
    assert json.loads(good.read_text(encoding="utf-8")) == {"x": 1}


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "roadmap_task_authority" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rta._atomic_write_json(target, {"x": 1})
    rta._atomic_write_json(target, {"x": 2})
    siblings = list(target.parent.iterdir())
    assert siblings == [target], siblings


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_authority" / "latest.json"
    monkeypatch.setattr(rta, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rta, "ARTIFACT_DIR", sentinel.parent)
    rc = rta.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"roadmap_task_authority"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_authority" / "latest.json"
    monkeypatch.setattr(rta, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rta, "ARTIFACT_DIR", sentinel.parent)
    rc = rta.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "roadmap_task_authority" in out
    assert "calls_execution_authority_classifier=True" in out
    assert "final_authority_classified=True" in out
    assert "no_runtime_trading_authority=True" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_authority" / "latest.json"
    monkeypatch.setattr(rta, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rta, "ARTIFACT_DIR", sentinel.parent)
    rc = rta.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "roadmap_task_authority"
    assert payload["module_version"].startswith("v3.15.16.A20c")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_authority" / "latest.json"
    monkeypatch.setattr(rta, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rta, "ARTIFACT_DIR", sentinel.parent)
    rc = rta.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rta.__file__).read_text(encoding="utf-8")


def _module_imports() -> list[str]:
    import ast as _ast

    tree = _ast.parse(_module_source())
    out: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, _ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                out.append(f"{mod}.{alias.name}" if mod else alias.name)
    return out


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    assert "subprocess." not in src


def test_no_socket_or_urllib_or_http_or_requests() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "from socket",
        "import urllib",
        "from urllib",
        "import http",
        "from http",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_runtime_imports_via_ast() -> None:
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "live",
        "paper",
        "shadow",
        "trading",
        "reporting.intelligent_routing",
        "reporting.development_queue_admission_policy",
        "reporting.development_agent_activity_timeline",
    )
    for module in _module_imports():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_no_gh_or_git_cli_calls() -> None:
    """No process-level invocation of gh / git. Docstring mentions
    are explicitly allowed."""
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system(",
        "os.popen(",
        "shell=True",
        "eval(",
        "exec(",
    ):
        assert forbidden not in src, forbidden


def test_no_github_api_or_external_api_calls() -> None:
    src = _module_source()
    for forbidden in (
        "api.github.com",
        "anthropic",
        "openai",
        "Bearer ",
        "X-API-Key",
        "X-GitHub-Token",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_only_canonical_upstreams() -> None:
    """A20c may only import from the canonical classifier + A20a +
    A20b. Any other third-party reporting module is forbidden."""
    allowed_reporting_imports = {
        "reporting.execution_authority",
        "reporting.roadmap_task_catalog",
        "reporting.roadmap_task_units",
    }
    for module in _module_imports():
        if module.startswith("reporting."):
            assert module in allowed_reporting_imports, module


def test_module_imports_cleanly() -> None:
    importlib.reload(rta)
    assert callable(rta.collect_snapshot)
    assert callable(rta.write_outputs)
    assert callable(rta.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rta.SCHEMA_VERSION, str) and rta.SCHEMA_VERSION
    assert isinstance(rta.MODULE_VERSION, str) and rta.MODULE_VERSION
    assert rta.MODULE_VERSION.endswith("A20c")
