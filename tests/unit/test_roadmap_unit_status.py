"""Unit tests for A21a — Dynamic Unit Status Ledger.

Pins:

* closed vocabularies (DYNAMIC_UNIT_STATUS,
  DYNAMIC_STATUS_SOURCE, DYNAMIC_STATUS_INVALID_REASON);
* schema field tuples (DYNAMIC_UNIT_STATUS_RECORD_FIELDS,
  ROADMAP_UNIT_STATUS_PROJECTION_FIELDS);
* deterministic output with injected ``generated_at_utc``;
* byte-identical output for identical input;
* atomic write only under ``logs/roadmap_unit_status/``;
* ``--no-write`` does not write; ``--status`` does not write;
* merged status requires non-empty pr_number, merge_sha, reason;
* invalid records (bad status, bad source, missing fields,
  non-hex SHA) carry ``valid = False`` and a closed-vocab
  validation_reason;
* duplicate unit_ids fail closed deterministically;
* bootstrap seed contains exactly the three already-merged
  v3.15.16 routing-layer units with pinned PR numbers and
  merge SHAs;
* ``step5_implementation_allowed`` remains ``False``;
* no Step 5, no Level 6, no production-merge authority, no
  runtime/trading/paper/shadow/live authority;
* no forbidden imports / runtime tokens in module source.
"""

from __future__ import annotations

import ast as _ast
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import roadmap_unit_status as rus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T20:00:00Z"


def _valid_merged_record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "unit_id": "u_syn_unit",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-05-18T10:00:00Z",
        "pr_number": 999,
        "merge_sha": "abc1234def567890abc1234def567890abc1234d",
        "reason": "implemented by synthetic PR",
        "evidence": ["github_pr_number=999"],
    }
    base.update(overrides)
    return base


def _snap_with(
    *records: dict[str, Any], ts: str = _FROZEN_UTC
) -> dict[str, Any]:
    return rus.collect_snapshot(
        seed=tuple(records), generated_at_utc=ts
    )


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_dynamic_unit_status_vocab_is_closed_exact() -> None:
    assert rus.DYNAMIC_UNIT_STATUS == (
        "not_started",
        "in_progress",
        "pr_open",
        "merged",
        "failed",
        "blocked",
        "skipped",
    )


def test_dynamic_status_source_vocab_is_closed_exact() -> None:
    assert rus.DYNAMIC_STATUS_SOURCE == (
        "pr_merge",
        "operator_override",
        "loop_state",
        "ci_failure",
        "operator_block",
    )


def test_dynamic_status_invalid_reason_vocab_includes_empty_string() -> None:
    """`""` denotes a valid record (no invalidity reason)."""
    assert "" in rus.DYNAMIC_STATUS_INVALID_REASON


def test_dynamic_status_invalid_reason_vocab_is_closed_exact() -> None:
    assert rus.DYNAMIC_STATUS_INVALID_REASON == (
        "",
        "unknown_status",
        "unknown_source",
        "empty_unit_id",
        "merged_without_pr_number",
        "merged_without_merge_sha",
        "merged_without_reason",
        "duplicate_unit_id",
        "missing_updated_at_utc",
        "evidence_not_a_list",
        "pr_number_not_a_positive_int",
        "merge_sha_not_a_hex_string",
    )


def test_dynamic_status_output_path_pinned() -> None:
    assert rus.DYNAMIC_STATUS_OUTPUT_PATH == (
        "logs/roadmap_unit_status/latest.json"
    )


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_record_field_list_exact() -> None:
    assert rus.DYNAMIC_UNIT_STATUS_RECORD_FIELDS == (
        "unit_id",
        "status",
        "source",
        "updated_at_utc",
        "pr_number",
        "merge_sha",
        "reason",
        "evidence",
        "valid",
        "validation_reason",
    )


def test_projection_field_list_exact() -> None:
    assert rus.ROADMAP_UNIT_STATUS_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "source_units_module_version",
        "ledger_records",
        "duplicate_unit_ids",
        "invalid_record_count",
        "valid_record_count",
        "fail_closed",
        "ledger_invariants",
    )


def test_every_record_has_every_field() -> None:
    snap = _snap_with(_valid_merged_record())
    for r in snap["ledger_records"]:
        assert set(r.keys()) == set(
            rus.DYNAMIC_UNIT_STATUS_RECORD_FIELDS
        ), r


def test_top_level_carries_every_projection_field() -> None:
    snap = _snap_with(_valid_merged_record())
    for field in rus.ROADMAP_UNIT_STATUS_PROJECTION_FIELDS:
        assert field in snap, field


# ---------------------------------------------------------------------------
# Bootstrap seed pins
# ---------------------------------------------------------------------------


def test_bootstrap_seed_has_three_v3_15_16_records() -> None:
    """The bootstrap ledger seed must encode exactly the three
    already-merged v3.15.16 routing-layer units."""
    snap = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    seed_unit_ids = sorted(r["unit_id"] for r in snap["ledger_records"])
    assert seed_unit_ids == [
        "u_v3_15_16_diagnostic_routing_signals_schema_001",
        "u_v3_15_16_routing_explanation_reporter_001",
        "u_v3_15_16_routing_governance_doc_001",
    ]


def test_bootstrap_seed_pr_numbers_pinned() -> None:
    snap = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    by_unit = {r["unit_id"]: r for r in snap["ledger_records"]}
    assert by_unit["u_v3_15_16_diagnostic_routing_signals_schema_001"][
        "pr_number"
    ] == 250
    assert by_unit["u_v3_15_16_routing_explanation_reporter_001"][
        "pr_number"
    ] == 252
    assert by_unit["u_v3_15_16_routing_governance_doc_001"][
        "pr_number"
    ] == 254


def test_bootstrap_seed_merge_shas_pinned() -> None:
    snap = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    by_unit = {r["unit_id"]: r for r in snap["ledger_records"]}
    assert by_unit["u_v3_15_16_diagnostic_routing_signals_schema_001"][
        "merge_sha"
    ] == "fcb1abbea4bd2ca190fe6e807b3dacd184faa702"
    assert by_unit["u_v3_15_16_routing_explanation_reporter_001"][
        "merge_sha"
    ] == "6f588a89b43a2cfec40f92252bde530220877b37"
    assert by_unit["u_v3_15_16_routing_governance_doc_001"][
        "merge_sha"
    ] == "df7dc6562ec3cd3a9f87e83e758881bd6fdb16f8"


def test_bootstrap_seed_all_records_are_valid() -> None:
    snap = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    for r in snap["ledger_records"]:
        assert r["valid"] is True, r
        assert r["validation_reason"] == "", r
    assert snap["fail_closed"] is False
    assert snap["invalid_record_count"] == 0
    assert snap["valid_record_count"] == 3
    assert snap["duplicate_unit_ids"] == []


def test_bootstrap_seed_all_records_are_pr_merge_source() -> None:
    snap = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    for r in snap["ledger_records"]:
        assert r["source"] == "pr_merge"


def test_bootstrap_seed_all_records_are_merged_status() -> None:
    snap = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    for r in snap["ledger_records"]:
        assert r["status"] == "merged"


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


def test_merged_status_requires_pr_number() -> None:
    snap = _snap_with(_valid_merged_record(pr_number=0))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "pr_number_not_a_positive_int"
    assert snap["fail_closed"] is True


def test_merged_status_requires_merge_sha() -> None:
    snap = _snap_with(_valid_merged_record(merge_sha=""))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "merged_without_merge_sha"
    assert snap["fail_closed"] is True


def test_merged_status_requires_reason() -> None:
    snap = _snap_with(_valid_merged_record(reason=""))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "merged_without_reason"
    assert snap["fail_closed"] is True


def test_merged_status_rejects_non_hex_sha() -> None:
    snap = _snap_with(_valid_merged_record(merge_sha="not-a-hex-sha"))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "merge_sha_not_a_hex_string"


def test_unknown_status_value_is_invalid() -> None:
    snap = _snap_with(
        _valid_merged_record(status="not_a_real_status")
    )
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "unknown_status"


def test_unknown_source_value_is_invalid() -> None:
    snap = _snap_with(
        _valid_merged_record(source="not_a_real_source")
    )
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "unknown_source"


def test_empty_unit_id_is_invalid() -> None:
    snap = _snap_with(_valid_merged_record(unit_id=""))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "empty_unit_id"


def test_missing_updated_at_is_invalid() -> None:
    snap = _snap_with(_valid_merged_record(updated_at_utc=""))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "missing_updated_at_utc"


def test_non_list_evidence_is_invalid() -> None:
    snap = _snap_with(_valid_merged_record(evidence="not-a-list"))
    rec = snap["ledger_records"][0]
    assert rec["valid"] is False
    assert rec["validation_reason"] == "evidence_not_a_list"


def test_pr_open_status_does_not_require_pr_number() -> None:
    """``pr_open`` is a valid non-terminal status. It records that a
    PR has been opened but does not yet require a merge SHA."""
    snap = _snap_with(
        _valid_merged_record(
            status="pr_open", pr_number=0, merge_sha="", reason=""
        )
    )
    rec = snap["ledger_records"][0]
    assert rec["valid"] is True
    assert rec["validation_reason"] == ""


def test_in_progress_status_does_not_require_evidence() -> None:
    snap = _snap_with(
        _valid_merged_record(
            status="in_progress",
            source="loop_state",
            pr_number=0,
            merge_sha="",
            reason="",
        )
    )
    rec = snap["ledger_records"][0]
    assert rec["valid"] is True


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def test_duplicate_unit_id_fails_closed() -> None:
    snap = _snap_with(
        _valid_merged_record(unit_id="u_dup"),
        _valid_merged_record(unit_id="u_dup", pr_number=12345),
    )
    assert snap["duplicate_unit_ids"] == ["u_dup"]
    assert snap["fail_closed"] is True
    for r in snap["ledger_records"]:
        assert r["valid"] is False
        assert r["validation_reason"] == "duplicate_unit_id"


def test_duplicate_does_not_taint_unrelated_records() -> None:
    snap = _snap_with(
        _valid_merged_record(unit_id="u_a"),
        _valid_merged_record(unit_id="u_b"),
        _valid_merged_record(unit_id="u_b", pr_number=42),
    )
    by_id = {r["unit_id"]: r for r in snap["ledger_records"]}
    # u_a is untouched.
    a_records = [r for r in snap["ledger_records"] if r["unit_id"] == "u_a"]
    assert len(a_records) == 1
    assert a_records[0]["valid"] is True
    # u_b duplicates both invalid.
    b_records = [r for r in snap["ledger_records"] if r["unit_id"] == "u_b"]
    assert len(b_records) == 2
    assert all(r["valid"] is False for r in b_records)
    assert snap["duplicate_unit_ids"] == ["u_b"]
    _ = by_id  # silence unused


def test_duplicate_detection_is_deterministic() -> None:
    """Duplicates list is stable across runs (sorted)."""
    snap_a = _snap_with(
        _valid_merged_record(unit_id="u_b"),
        _valid_merged_record(unit_id="u_b", pr_number=2),
        _valid_merged_record(unit_id="u_a"),
        _valid_merged_record(unit_id="u_a", pr_number=2),
    )
    snap_b = _snap_with(
        _valid_merged_record(unit_id="u_a"),
        _valid_merged_record(unit_id="u_a", pr_number=2),
        _valid_merged_record(unit_id="u_b"),
        _valid_merged_record(unit_id="u_b", pr_number=2),
    )
    assert snap_a["duplicate_unit_ids"] == snap_b["duplicate_unit_ids"]


def test_no_implicit_merged_resurrection() -> None:
    """A duplicate that tries to replace a ``merged`` record with
    ``not_started`` is rejected via duplicate fail-closed."""
    snap = _snap_with(
        _valid_merged_record(unit_id="u_x"),
        _valid_merged_record(
            unit_id="u_x",
            status="not_started",
            source="operator_override",
            pr_number=0,
            merge_sha="",
            reason="",
        ),
    )
    assert "u_x" in snap["duplicate_unit_ids"]
    assert snap["fail_closed"] is True


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts() -> None:
    a = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_records_sorted_stably_by_unit_id() -> None:
    snap = _snap_with(
        _valid_merged_record(unit_id="u_zz"),
        _valid_merged_record(unit_id="u_aa", pr_number=2),
        _valid_merged_record(unit_id="u_mm", pr_number=3),
    )
    unit_ids = [r["unit_id"] for r in snap["ledger_records"]]
    assert unit_ids == sorted(unit_ids)


# ---------------------------------------------------------------------------
# Step 5 / Level 6 / authority invariants
# ---------------------------------------------------------------------------


def test_step5_implementation_allowed_is_final_false() -> None:
    assert rus.step5_implementation_allowed is False


def test_step5_enabled_substage_is_none() -> None:
    assert rus.STEP5_ENABLED_SUBSTAGE == "none"


def test_projection_pins_step5_implementation_allowed_false() -> None:
    snap = _snap_with(_valid_merged_record())
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_ledger_invariants_pin_no_runtime_trading_authority() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["no_runtime_trading_authority"] is True


def test_ledger_invariants_pin_no_step5_no_level6_no_production_merge() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["no_step5_runtime"] is True
    assert inv["no_level6"] is True
    assert inv["no_production_merge_authority"] is True
    assert inv["step5_implementation_allowed"] is False


def test_ledger_invariants_pin_no_work_execution() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["no_work_execution"] is True
    assert inv["no_branch_creation"] is True
    assert inv["no_pr_creation"] is True
    assert inv["no_merge_or_deploy"] is True


def test_ledger_invariants_pin_no_mutation_routes_or_approval_buttons() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["no_mutation_routes"] is True
    assert inv["no_approval_buttons"] is True


def test_ledger_invariants_pin_no_a20b_mutation() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["mutates_a20b_artifact"] is False
    assert inv["writes_only_roadmap_unit_status_log"] is True


def test_ledger_invariants_pin_no_seed_jsonl_writes() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False
    assert inv["writes_to_approval_inbox"] is False
    assert inv["writes_to_work_queue_jsonl"] is False


def test_ledger_invariants_pin_no_classifier_or_llm_calls() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["calls_execution_authority_classifier"] is False
    assert inv["calls_llm_or_external_api"] is False
    assert inv["uses_subprocess_or_network"] is False


def test_ledger_invariants_pin_fail_closed_contracts() -> None:
    snap = _snap_with(_valid_merged_record())
    inv = snap["ledger_invariants"]
    assert inv["merged_status_requires_evidence"] is True
    assert inv["duplicate_unit_id_fails_closed"] is True
    assert inv["invalid_record_fails_closed"] is True
    assert inv["no_implicit_merged_resurrection"] is True


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rus._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(
    tmp_path: Path,
) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
        "docs/development_work_queue/latest.jsonl",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rus._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rus._atomic_write_json(good, {"x": 1})
    assert good.is_file()


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rus._atomic_write_json(good, {"a": 1})
    rus._atomic_write_json(good, {"b": 2})
    # No leftover temp files in the directory.
    leftovers = [
        p
        for p in good.parent.iterdir()
        if p.name.startswith(".roadmap_unit_status.")
    ]
    assert leftovers == []


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    monkeypatch.setattr(rus, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rus, "ARTIFACT_DIR", sentinel.parent)
    rc = rus.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"roadmap_unit_status"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    monkeypatch.setattr(rus, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rus, "ARTIFACT_DIR", sentinel.parent)
    rc = rus.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "roadmap_unit_status" in out
    assert "no_runtime_trading_authority=True" in out
    assert "no_step5_runtime=True" in out
    assert "no_level6=True" in out
    assert "no_production_merge_authority=True" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    monkeypatch.setattr(rus, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rus, "ARTIFACT_DIR", sentinel.parent)
    rc = rus.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "roadmap_unit_status"
    assert payload["module_version"].endswith("A21a")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    monkeypatch.setattr(rus, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rus, "ARTIFACT_DIR", sentinel.parent)
    rc = rus.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Read-only invariants (no work execution)
# ---------------------------------------------------------------------------


def test_collect_snapshot_does_not_mutate_upstream_or_seed(
    tmp_path: Path,
) -> None:
    """The seed is a Final tuple; the snapshot does not mutate it."""
    seed_before = hashlib.sha256(
        repr(rus._STATUS_LEDGER_SEED).encode("utf-8")
    ).hexdigest()
    rus.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    seed_after = hashlib.sha256(
        repr(rus._STATUS_LEDGER_SEED).encode("utf-8")
    ).hexdigest()
    assert seed_before == seed_after


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rus.__file__).read_text(encoding="utf-8")


def _module_imports() -> list[str]:
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
        "reporting.execution_authority",
        "reporting.development_queue_admission_policy",
        "reporting.development_agent_activity_timeline",
        "reporting.roadmap_next_unit",
        "reporting.roadmap_unit_authority",
        "reporting.roadmap_task_catalog",
    )
    for module in _module_imports():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_no_gh_or_git_cli_calls() -> None:
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


def test_module_imports_only_canonical_upstream() -> None:
    """A21a may only import from A20b (read-only) to expose its
    cross-reference module version on the projection."""
    allowed = {"reporting.roadmap_task_units"}
    for module in _module_imports():
        if module.startswith("reporting."):
            assert module in allowed, module


def test_module_imports_cleanly() -> None:
    importlib.reload(rus)
    assert callable(rus.collect_snapshot)
    assert callable(rus.write_outputs)
    assert callable(rus.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rus.SCHEMA_VERSION, str) and rus.SCHEMA_VERSION
    assert isinstance(rus.MODULE_VERSION, str) and rus.MODULE_VERSION
    assert rus.MODULE_VERSION.endswith("A21a")
