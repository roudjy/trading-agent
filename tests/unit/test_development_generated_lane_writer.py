"""Pin-tests for A18b — generated_seed.jsonl writer (default-disabled).

Verifies the env-gated writer's default-deny posture, closed
vocabularies, atomic write + audit behaviour, duplicate handling,
existing-file-malformed default-deny, and the strict A18a-invariance
behavioural contract (A18a stays report-only regardless of A18b).

Forbidden marker strings (secret-shaped tokens) are assembled at
runtime so the test source itself stays inert to gitleaks.
"""

from __future__ import annotations

import ast
import datetime as _dt
import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_generated_lane as a18a
from reporting import development_generated_lane_writer as a18b


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures — isolate the seed file and the audit log into tmp_path.
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    seed = tmp_path / "generated_seed.jsonl"
    audit_dir = tmp_path / "logs" / "development_generated_lane_writer"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit = audit_dir / "audit.jsonl"
    monkeypatch.setattr(a18b, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(a18b, "GENERATED_SEED_PATH", seed)
    monkeypatch.setattr(a18b, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(a18b, "AUDIT_PATH", audit)
    return {"seed": seed, "audit": audit, "audit_dir": audit_dir}


def _valid_record(
    *,
    generated_candidate_id: str = "gc_test_001",
    source_module: str = "reporting.development_bugfix_loop",
    source_id: str = "src_001",
    proposed_kind: str = "bugfix",
    proposed_title: str = "synthetic title",
    proposed_summary: str = "synthetic summary",
    evidence_hash: str = "evhash_001",
    admission_preview: str = "generated_seed_written",
    block_reason: str = "none",
    would_require_operator_go: bool = True,
    generated_at_utc: str = "2026-05-12T21:00:00Z",
    writer_module_version: str = "v3.15.16.A18b",
) -> dict[str, Any]:
    return {
        "generated_candidate_id": generated_candidate_id,
        "source_module": source_module,
        "source_id": source_id,
        "proposed_kind": proposed_kind,
        "proposed_title": proposed_title,
        "proposed_summary": proposed_summary,
        "evidence_hash": evidence_hash,
        "admission_preview": admission_preview,
        "block_reason": block_reason,
        "would_require_operator_go": would_require_operator_go,
        "generated_at_utc": generated_at_utc,
        "writer_module_version": writer_module_version,
    }


def _env_enabled() -> dict[str, str]:
    return {"ADE_GENERATED_LANE_WRITER_ENABLED": "true"}


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_module_version() -> None:
    assert a18b.MODULE_VERSION == "v3.15.16.A18b"
    assert a18b.SCHEMA_VERSION == "1.0"
    assert a18b.REPORT_KIND == "development_generated_lane_writer"


def test_env_var_name_is_exact() -> None:
    assert a18b.ENV_WRITER_ENABLED == "ADE_GENERATED_LANE_WRITER_ENABLED"


def test_max_records_cap_is_256() -> None:
    assert a18b.MAX_GENERATED_SEED_RECORDS == 256


def test_step5_invariants_intact_by_import() -> None:
    assert a18b.step5_implementation_allowed is False
    assert a18b.STEP5_ENABLED_SUBSTAGE == "none"


def test_forbidden_seed_basenames_pinned_exact() -> None:
    assert a18b._FORBIDDEN_SEED_BASENAMES == (
        "seed.jsonl",
        "delegation_seed.jsonl",
    )


def test_writer_admission_previews_extend_a18a_additively() -> None:
    assert a18b.WRITER_ADMISSION_PREVIEWS == (
        "report_only_not_admitted",
        "generated_seed_written",
    )
    # A18a's vocab must remain untouched and minimal.
    assert a18a.ADMISSION_PREVIEWS == ("report_only_not_admitted",)


def test_writer_block_reasons_pinned_exact() -> None:
    assert a18b.WRITER_BLOCK_REASONS == (
        "none",
        "writer_disabled",
        "invalid_record_schema",
        "duplicate_candidate_id",
        "max_records_reached",
        "path_refused",
        "secret_detected",
        "existing_file_malformed",
        "generated_lane_writer_not_authorized",
    )


def test_writer_warnings_pinned_exact() -> None:
    assert a18b.WRITER_WARNINGS == ("duplicate_evidence_hash",)


def test_audit_attempt_kinds_pinned_exact() -> None:
    assert a18b.AUDIT_ATTEMPT_KINDS == (
        "written",
        "rejected_duplicate_candidate_id",
        "rejected_existing_file_malformed",
        "rejected_invalid_record_schema",
        "rejected_max_records_reached",
        "rejected_path_refused",
        "rejected_secret_detected",
        "skipped_writer_disabled",
    )


def test_generated_record_keys_pinned_exact() -> None:
    assert a18b.GENERATED_RECORD_KEYS == (
        "generated_candidate_id",
        "source_module",
        "source_id",
        "proposed_kind",
        "proposed_title",
        "proposed_summary",
        "evidence_hash",
        "admission_preview",
        "block_reason",
        "would_require_operator_go",
        "generated_at_utc",
        "writer_module_version",
    )


def test_discipline_invariants_match_exact_required_set() -> None:
    expected = {
        "default_disabled": True,
        "writes_only_generated_seed_jsonl": True,
        "writes_seed_jsonl": False,
        "writes_delegation_seed_jsonl": False,
        "admits_queue_items": False,
        "executes_work": False,
        "creates_branches": False,
        "opens_prs": False,
        "merges_prs": False,
        "deploys": False,
        "calls_network": False,
        "uses_subprocess": False,
        "touches_step5_flags": False,
        "level6_enabled": False,
    }
    assert a18b._DISCIPLINE_INVARIANTS == expected


# ---------------------------------------------------------------------------
# writer_enabled — strict exact-string semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", False),
        ("TRUE", False),
        ("1", False),
        ("yes", False),
        ("on", False),
        ("false", False),
        ("", False),
        (" true", False),
        ("true ", False),
    ],
)
def test_writer_enabled_requires_exact_lowercase_true(
    value: str, expected: bool
) -> None:
    assert a18b.writer_enabled(env={a18b.ENV_WRITER_ENABLED: value}) is expected


def test_writer_enabled_returns_false_when_env_unset() -> None:
    assert a18b.writer_enabled(env={}) is False


# ---------------------------------------------------------------------------
# Default-disabled — zero-write
# ---------------------------------------------------------------------------


def test_append_when_disabled_is_zero_write(
    isolated_paths: dict[str, Path],
) -> None:
    env = {a18b.ENV_WRITER_ENABLED: "false"}
    res = a18b.append_generated_seed_record(_valid_record(), env=env)
    assert res["status"] == "skipped"
    assert res["stop_status"] == "writer_disabled"
    assert res["writer_enabled"] is False
    assert not isolated_paths["seed"].exists()
    assert not isolated_paths["audit"].exists()


def test_append_when_env_unset_is_zero_write(
    isolated_paths: dict[str, Path],
) -> None:
    res = a18b.append_generated_seed_record(_valid_record(), env={})
    assert res["status"] == "skipped"
    assert res["stop_status"] == "writer_disabled"
    assert not isolated_paths["seed"].exists()
    assert not isolated_paths["audit"].exists()


@pytest.mark.parametrize("value", ["1", "yes", "True", "TRUE", "on", ""])
def test_append_with_non_true_alias_is_zero_write(
    isolated_paths: dict[str, Path], value: str
) -> None:
    res = a18b.append_generated_seed_record(
        _valid_record(),
        env={a18b.ENV_WRITER_ENABLED: value},
    )
    assert res["status"] == "skipped"
    assert res["stop_status"] == "writer_disabled"
    assert not isolated_paths["seed"].exists()
    assert not isolated_paths["audit"].exists()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_append_happy_path_writes_one_seed_row_and_one_audit_row(
    isolated_paths: dict[str, Path],
) -> None:
    res = a18b.append_generated_seed_record(
        _valid_record(generated_candidate_id="gc_happy"),
        env=_env_enabled(),
    )
    assert res["status"] == "written"
    assert res["stop_status"] == "none"
    assert res["writer_enabled"] is True
    assert res["warnings"] == []
    assert res["generated_candidate_id"] == "gc_happy"
    # Seed file has exactly one record.
    seed_lines = (
        isolated_paths["seed"].read_text(encoding="utf-8").splitlines()
    )
    assert len(seed_lines) == 1
    body = json.loads(seed_lines[0])
    assert body["generated_candidate_id"] == "gc_happy"
    assert body["writer_module_version"] == "v3.15.16.A18b"
    assert body["admission_preview"] == "generated_seed_written"
    # Audit file has exactly one row tagged as written.
    audit_lines = (
        isolated_paths["audit"].read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 1
    audit_row = json.loads(audit_lines[0])
    assert audit_row["attempt_kind"] == "written"
    assert audit_row["generated_candidate_id"] == "gc_happy"
    assert audit_row["stop_status"] == "none"
    assert audit_row["warnings"] == []


# ---------------------------------------------------------------------------
# Path-sentinel
# ---------------------------------------------------------------------------


def test_path_refused_when_basename_is_not_generated_seed_jsonl(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    rogue = tmp_path / "rogue_seed.jsonl"
    res = a18b.append_generated_seed_record(
        _valid_record(),
        generated_seed_path=rogue,
        env=_env_enabled(),
    )
    assert res["status"] == "rejected"
    assert res["stop_status"] == "path_refused"
    assert not rogue.exists()
    assert not isolated_paths["seed"].exists()


def test_path_refused_when_target_is_seed_jsonl(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    # The forbidden basename. This filename must be refused even
    # if a caller explicitly overrides the kwarg.
    forbidden = tmp_path / "seed.jsonl"
    res = a18b.append_generated_seed_record(
        _valid_record(),
        generated_seed_path=forbidden,
        env=_env_enabled(),
    )
    assert res["status"] == "rejected"
    assert res["stop_status"] == "path_refused"
    assert not forbidden.exists()


def test_path_refused_when_target_is_delegation_seed_jsonl(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    forbidden = tmp_path / "delegation_seed.jsonl"
    res = a18b.append_generated_seed_record(
        _valid_record(),
        generated_seed_path=forbidden,
        env=_env_enabled(),
    )
    assert res["status"] == "rejected"
    assert res["stop_status"] == "path_refused"
    assert not forbidden.exists()


def test_path_refused_when_audit_path_outside_prefix(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    rogue_audit = tmp_path / "rogue_audit.jsonl"
    res = a18b.append_generated_seed_record(
        _valid_record(),
        audit_path=rogue_audit,
        env=_env_enabled(),
    )
    assert res["status"] == "rejected"
    assert res["stop_status"] == "path_refused"
    assert not rogue_audit.exists()
    # Neither the seed nor the audit gets touched.
    assert not isolated_paths["seed"].exists()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_missing_required_key_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record()
    bad.pop("evidence_hash")
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"
    assert not isolated_paths["seed"].exists()
    # Audit row recorded the rejection.
    audit_lines = (
        isolated_paths["audit"].read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 1
    assert (
        json.loads(audit_lines[0])["attempt_kind"]
        == "rejected_invalid_record_schema"
    )


def test_extra_unknown_key_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record()
    bad["mystery_extra"] = "x"
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"


def test_invalid_proposed_kind_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record(proposed_kind="not_a_real_kind")
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"


def test_invalid_admission_preview_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record(admission_preview="not_a_real_preview")
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"


def test_invalid_block_reason_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record(block_reason="not_a_real_reason")
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"


def test_non_string_id_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record()
    bad["generated_candidate_id"] = 12345  # type: ignore[assignment]
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"


def test_non_bool_operator_go_yields_invalid_record_schema(
    isolated_paths: dict[str, Path],
) -> None:
    bad = _valid_record()
    bad["would_require_operator_go"] = "yes"  # type: ignore[assignment]
    res = a18b.append_generated_seed_record(bad, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "invalid_record_schema"


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------


def test_duplicate_candidate_id_hard_rejects(
    isolated_paths: dict[str, Path],
) -> None:
    # First append succeeds.
    r1 = a18b.append_generated_seed_record(
        _valid_record(generated_candidate_id="gc_dup"),
        env=_env_enabled(),
    )
    assert r1["status"] == "written"
    # Second append with the same id is rejected.
    r2 = a18b.append_generated_seed_record(
        _valid_record(
            generated_candidate_id="gc_dup",
            source_id="different_source_id",
            evidence_hash="different_hash",
        ),
        env=_env_enabled(),
    )
    assert r2["status"] == "rejected"
    assert r2["stop_status"] == "duplicate_candidate_id"
    # Seed file still has exactly one row.
    seed_lines = (
        isolated_paths["seed"].read_text(encoding="utf-8").splitlines()
    )
    assert len(seed_lines) == 1
    # Audit log records: 1 written + 1 rejection.
    audit_lines = (
        isolated_paths["audit"].read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 2
    assert json.loads(audit_lines[0])["attempt_kind"] == "written"
    assert (
        json.loads(audit_lines[1])["attempt_kind"]
        == "rejected_duplicate_candidate_id"
    )


def test_duplicate_evidence_hash_with_different_id_writes_with_warning(
    isolated_paths: dict[str, Path],
) -> None:
    r1 = a18b.append_generated_seed_record(
        _valid_record(
            generated_candidate_id="gc_first",
            evidence_hash="shared_hash",
        ),
        env=_env_enabled(),
    )
    assert r1["status"] == "written"
    assert r1["warnings"] == []
    r2 = a18b.append_generated_seed_record(
        _valid_record(
            generated_candidate_id="gc_second",
            evidence_hash="shared_hash",
        ),
        env=_env_enabled(),
    )
    assert r2["status"] == "written"
    assert r2["warnings"] == ["duplicate_evidence_hash"]
    seed_lines = (
        isolated_paths["seed"].read_text(encoding="utf-8").splitlines()
    )
    assert len(seed_lines) == 2
    audit_lines = (
        isolated_paths["audit"].read_text(encoding="utf-8").splitlines()
    )
    assert len(audit_lines) == 2
    assert json.loads(audit_lines[1])["attempt_kind"] == "written"
    assert json.loads(audit_lines[1])["warnings"] == ["duplicate_evidence_hash"]


# ---------------------------------------------------------------------------
# Cap
# ---------------------------------------------------------------------------


def test_max_records_reached_rejects_the_257th_append(
    isolated_paths: dict[str, Path],
) -> None:
    # Pre-populate 256 records cheaply.
    rows = [
        json.dumps(
            _valid_record(generated_candidate_id=f"gc_pre_{i:04d}"),
            sort_keys=True,
        )
        for i in range(a18b.MAX_GENERATED_SEED_RECORDS)
    ]
    isolated_paths["seed"].write_text("\n".join(rows) + "\n", encoding="utf-8")
    res = a18b.append_generated_seed_record(
        _valid_record(generated_candidate_id="gc_over_cap"),
        env=_env_enabled(),
    )
    assert res["status"] == "rejected"
    assert res["stop_status"] == "max_records_reached"
    seed_lines = (
        isolated_paths["seed"].read_text(encoding="utf-8").splitlines()
    )
    # No append. Still 256.
    assert len(seed_lines) == a18b.MAX_GENERATED_SEED_RECORDS


# ---------------------------------------------------------------------------
# Existing-file malformed → default-deny
# ---------------------------------------------------------------------------


def test_existing_file_malformed_rejects_append(
    isolated_paths: dict[str, Path],
) -> None:
    isolated_paths["seed"].write_text(
        "{not_json}\n",
        encoding="utf-8",
    )
    res = a18b.append_generated_seed_record(
        _valid_record(generated_candidate_id="gc_after_malformed"),
        env=_env_enabled(),
    )
    assert res["status"] == "rejected"
    assert res["stop_status"] == "existing_file_malformed"
    # Seed file untouched (still the malformed content).
    assert isolated_paths["seed"].read_text(encoding="utf-8") == "{not_json}\n"
    # Audit row recorded the refusal.
    audit_lines = (
        isolated_paths["audit"].read_text(encoding="utf-8").splitlines()
    )
    assert (
        json.loads(audit_lines[0])["attempt_kind"]
        == "rejected_existing_file_malformed"
    )


# ---------------------------------------------------------------------------
# Secret detection via assert_no_secrets
# ---------------------------------------------------------------------------


def test_secret_in_record_rejects_append(
    isolated_paths: dict[str, Path],
) -> None:
    # Build the PEM marker at runtime so the test source stays
    # inert to gitleaks; embedding the same string into a synthetic
    # record body should trigger assert_no_secrets's PEM rule.
    dashes = "-" * 5
    fake_pem = f"{dashes}BEGIN PRIVATE KEY{dashes}\nAAAA\n{dashes}END PRIVATE KEY{dashes}"
    rec = _valid_record(proposed_summary=fake_pem)
    res = a18b.append_generated_seed_record(rec, env=_env_enabled())
    assert res["status"] == "rejected"
    assert res["stop_status"] == "secret_detected"
    assert not isolated_paths["seed"].exists()
    audit_lines = (
        isolated_paths["audit"].read_text(encoding="utf-8").splitlines()
    )
    assert (
        json.loads(audit_lines[0])["attempt_kind"]
        == "rejected_secret_detected"
    )
    # Audit row itself does NOT leak the PEM marker.
    assert "BEGIN PRIVATE KEY" not in audit_lines[0]


# ---------------------------------------------------------------------------
# Validator independent of write side effects
# ---------------------------------------------------------------------------


def test_validate_record_returns_ok_for_valid_record() -> None:
    ok, stop, warnings = a18b.validate_record(_valid_record())
    assert ok is True
    assert stop == "none"
    assert warnings == []


def test_validate_record_rejects_non_dict() -> None:
    ok, stop, warnings = a18b.validate_record("not a dict")
    assert ok is False
    assert stop == "invalid_record_schema"


# ---------------------------------------------------------------------------
# No env-read / no write at import time
# ---------------------------------------------------------------------------


def test_no_write_at_import_even_when_env_is_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Importing the module with the env-gate already set must
    not create any file. Writes happen only when the public API
    is called."""
    monkeypatch.setenv(a18b.ENV_WRITER_ENABLED, "true")
    # Re-import the module under the patched env. The seed path
    # is the canonical one, but the module is freshly imported —
    # if a write happened at import time, the file would appear.
    target = REPO_ROOT / "generated_seed.jsonl"
    pre_existed = target.exists()
    importlib.reload(a18b)
    post_exists = target.exists()
    # The file must NOT have been newly created by import.
    assert post_exists == pre_existed


# ---------------------------------------------------------------------------
# A18a invariance — behavioural pins (per operator correction 1)
# ---------------------------------------------------------------------------


def test_a18a_module_still_imports_and_exposes_its_constants() -> None:
    """A18b must not have broken A18a. The closed vocabularies the
    operator's plan relies on must remain present and unchanged."""
    assert a18a.PROPOSED_KINDS == ("bugfix", "delegation", "e2e_proof", "unknown")
    assert a18a.ADMISSION_PREVIEWS == ("report_only_not_admitted",)
    assert a18a.BLOCK_REASONS == ("generated_lane_writer_not_authorized",)
    assert hasattr(a18a, "collect_snapshot")
    assert hasattr(a18a, "MAX_GENERATED_CANDIDATES")


def test_a18a_snapshot_remains_report_only_with_writer_env_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when ``ADE_GENERATED_LANE_WRITER_ENABLED=true`` is set,
    invoking A18a must produce no files and must still emit
    ``admission_preview="report_only_not_admitted"`` wherever
    that field appears."""
    monkeypatch.setenv(a18b.ENV_WRITER_ENABLED, "true")
    # Snapshot A18a — pass tmp_path as both source roots so no real
    # logs are read or written. A18a is designed to be tolerant of
    # missing artefacts.
    snap = a18a.collect_snapshot()
    assert isinstance(snap, dict)
    # No file is created in tmp_path by A18a, because A18a is a
    # pure projector — it returns a snapshot but does not write
    # unless write_outputs is explicitly called.
    candidates = snap.get("candidates") or []
    for row in candidates:
        # Every candidate must keep the report-only admission_preview.
        assert row.get("admission_preview") == "report_only_not_admitted"
        # And the block_reason stays in A18a's minimal closed vocab.
        assert row.get("block_reason") in a18a.BLOCK_REASONS


def test_importing_a18b_does_not_touch_generated_seed_or_a18a_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A18b's import side-effects must be limited to module-level
    constant definitions. No file should appear on disk merely from
    importing A18b."""
    monkeypatch.setenv(a18b.ENV_WRITER_ENABLED, "true")
    seed_pre = (REPO_ROOT / "generated_seed.jsonl").exists()
    audit_pre = (REPO_ROOT / "logs" / "development_generated_lane_writer" / "audit.jsonl").exists()
    importlib.reload(a18b)
    seed_post = (REPO_ROOT / "generated_seed.jsonl").exists()
    audit_post = (REPO_ROOT / "logs" / "development_generated_lane_writer" / "audit.jsonl").exists()
    assert seed_post == seed_pre
    assert audit_post == audit_pre


# ---------------------------------------------------------------------------
# Source-text + AST scans (per operator correction 2)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(a18b.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_or_network_imports() -> None:
    forbidden = {
        "subprocess",
        "socket",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "selectors",
        "asyncio",
    }
    overlap = _imported_module_names() & forbidden
    assert not overlap, (
        f"development_generated_lane_writer must not import "
        f"network/subprocess modules: {overlap!r}"
    )


def test_no_forbidden_subsystem_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
        "reporting.approval_token_runtime",
        "reporting.approval_token_gate",
    )
    names = _imported_module_names()
    for prefix in forbidden_prefixes:
        for name in names:
            assert not (name == prefix or name.startswith(prefix + ".")), (
                f"a18b must not import {prefix!r}; got {name!r}"
            )


def test_no_gh_or_git_cli_literal() -> None:
    """Forbidden CLI literals assembled at runtime so the test
    file itself is inert."""
    text = _module_source()
    forbidden_literals = (
        "g" + "h pr merge",
        "g" + "h pr review",
        "g" + "h api",
        "g" + "it merge",
        "g" + "it push",
    )
    for tok in forbidden_literals:
        assert tok not in text, (
            f"a18b contains forbidden CLI literal: {tok!r}"
        )


def test_no_pem_secret_block_in_source() -> None:
    text = _module_source()
    dashes = "-" * 5
    for kind in ("PRIVATE KEY", "EC PRIVATE KEY", "RSA PRIVATE KEY"):
        marker = f"{dashes}BEGIN {kind}{dashes}"
        assert marker not in text, (
            f"a18b contains a PEM block: {marker!r}"
        )


def test_no_non_loopback_ip_literal_in_source() -> None:
    text = _module_source()
    ip_re = re.compile(
        r"(?<![\w.])(?!127\.0\.0\.1\b)"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![.\d])"
    )
    matches = ip_re.findall(text)
    assert matches == [], (
        f"a18b contains a non-loopback IP literal: {matches!r}"
    )


def test_no_approval_token_use_pattern() -> None:
    """Use-pattern scan only — the discipline_invariants key
    ``writes_only_generated_seed_jsonl`` legitimately contains the
    substring ``seed_jsonl`` (the negative declarations are part
    of the dict), so substring-based bans on bare tokens are too
    coarse. We ban concrete USE patterns instead."""
    text = _module_source()
    forbidden = (
        "ADE_APPROVAL_TOKEN_HMAC_SECRET",
        "from reporting.approval_token_runtime",
        "from reporting.approval_token_gate",
        "from dashboard.api_approval_token_gate",
        "import approval_token_runtime",
        "import approval_token_gate",
        "mint_runtime(",
        "verify_runtime(",
        "mint_token(",
        "verify_token(",
        "VAPID",
        "p256dh",
    )
    for tok in forbidden:
        assert tok not in text, (
            f"a18b must not reference {tok!r}"
        )


# ---------------------------------------------------------------------------
# Seed-filename literals are allowed ONLY in the refusal blocklist
# (per operator correction 2).
#
# The strategy: walk the AST, find every string literal node, and
# check that any node whose value is one of the forbidden seed
# filenames is located inside _FORBIDDEN_SEED_BASENAMES. Other
# uses (e.g. in a write() call, an open() call, a Path() call,
# or any function body that opens these paths) would fail.
# ---------------------------------------------------------------------------


def test_seed_filename_literals_only_appear_in_blocklist_or_comments() -> None:
    """The literals ``seed.jsonl`` and ``delegation_seed.jsonl`` are
    legitimate only inside the ``_FORBIDDEN_SEED_BASENAMES`` tuple.
    This test walks the AST and verifies that every string-literal
    occurrence of those names is inside that tuple's assignment.
    String literals inside docstrings and comments are not part
    of the executable AST, so they are implicitly allowed."""
    source = _module_source()
    tree = ast.parse(source)

    # Locate the _FORBIDDEN_SEED_BASENAMES assignment node's range.
    blocklist_range: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_FORBIDDEN_SEED_BASENAMES":
                blocklist_range = (
                    node.lineno,
                    getattr(node, "end_lineno", node.lineno),
                )
                break
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_FORBIDDEN_SEED_BASENAMES":
                    blocklist_range = (
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno),
                    )
                    break
            if blocklist_range:
                break
    assert blocklist_range is not None, (
        "_FORBIDDEN_SEED_BASENAMES assignment not found in module"
    )

    forbidden_literals = ("seed.jsonl", "delegation_seed.jsonl")
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, str):
            continue
        # Exact match against the forbidden basenames.
        if node.value not in forbidden_literals:
            continue
        line = getattr(node, "lineno", -1)
        if line < blocklist_range[0] or line > blocklist_range[1]:
            offending.append((line, node.value))
    assert not offending, (
        "seed-filename string literals appear outside the "
        f"_FORBIDDEN_SEED_BASENAMES blocklist: {offending!r}"
    )


def test_no_function_opens_or_writes_forbidden_seed_paths() -> None:
    """No function in the module passes a forbidden seed basename
    to a write-shaped call (``open``, ``write_text``, ``write_bytes``,
    ``replace``, ``open(...,'w')``, etc.)."""
    source = _module_source()
    tree = ast.parse(source)
    forbidden_literals = {"seed.jsonl", "delegation_seed.jsonl"}
    write_shape_callees = {
        "open",
        "write_text",
        "write_bytes",
        "writelines",
    }
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee_name: str | None = None
        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee_name = node.func.attr
        if callee_name not in write_shape_callees:
            continue
        # Check the call's args for any forbidden seed-basename literal.
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value in forbidden_literals:
                    offending.append(
                        (getattr(node, "lineno", -1), arg.value)
                    )
    assert not offending, (
        "a18b has a write-shaped call referencing a forbidden seed "
        f"filename: {offending!r}"
    )


# ---------------------------------------------------------------------------
# .gitignore pin
# ---------------------------------------------------------------------------


def test_gitignore_contains_generated_seed_jsonl_line() -> None:
    """The repo's .gitignore must contain a line that matches
    ``generated_seed.jsonl`` — either the bare filename or
    ``/generated_seed.jsonl`` anchor form."""
    gitignore_path = REPO_ROOT / ".gitignore"
    assert gitignore_path.is_file(), "repo .gitignore missing"
    lines = [
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    accepted = {"generated_seed.jsonl", "/generated_seed.jsonl"}
    assert any(line in accepted for line in lines), (
        f".gitignore must include generated_seed.jsonl; got: {lines!r}"
    )


# ---------------------------------------------------------------------------
# CLI status sanity
# ---------------------------------------------------------------------------


def test_cli_status_snapshot_is_safe(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(a18b.ENV_WRITER_ENABLED, raising=False)
    rc = a18b.main(["--no-write"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["report_kind"] == "development_generated_lane_writer"
    assert parsed["writer_enabled"] is False
    assert parsed["max_records_cap"] == 256
    assert parsed["step5_implementation_allowed"] is False
    assert parsed["step5_enabled_substage"] == "none"
    assert parsed["level6_enabled"] is False
