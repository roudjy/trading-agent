"""Unit tests for ``reporting.governance_status``.

Properties under test:

* the snapshot is a JSON-serialisable dict with a stable key shape;
* missing inputs degrade to ``"unknown"`` / ``"not_available"`` rather
  than ``"ok"``;
* unknown audit-ledger / autonomy-ladder state never surfaces as
  ``"intact"`` or as a numeric ``max_available_level``;
* nothing in the snapshot leaks credentials or sensitive path
  fragments;
* the CLI prints the same JSON ``collect_status()`` returns and exits
  zero;
* frozen contracts (``research/research_latest.json`` and
  ``research/strategy_matrix.csv``) are not opened by either path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reporting import agent_audit, governance_status

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _existence_and_sha(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return (False, None)
    return (True, _file_sha256(path))


@pytest.fixture
def isolated_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every governance_status path constant into ``tmp_path``.

    Each test that uses this fixture starts from an empty governance
    layer; tests opt-in to specific files (settings.json, hooks, etc.).
    """
    repo = tmp_path
    (repo / ".claude").mkdir()
    (repo / ".claude" / "hooks").mkdir()
    (repo / ".claude" / "agents").mkdir()
    (repo / "docs" / "governance").mkdir(parents=True)
    (repo / "logs").mkdir()

    monkeypatch.setattr(governance_status, "REPO_ROOT", repo)
    monkeypatch.setattr(governance_status, "VERSION_FILE", repo / "VERSION")
    monkeypatch.setattr(
        governance_status, "SETTINGS_FILE", repo / ".claude" / "settings.json"
    )
    monkeypatch.setattr(
        governance_status, "HOOKS_DIR", repo / ".claude" / "hooks"
    )
    monkeypatch.setattr(
        governance_status, "AGENTS_DIR", repo / ".claude" / "agents"
    )
    monkeypatch.setattr(
        governance_status,
        "LADDER_DOC",
        repo / "docs" / "governance" / "autonomy_ladder.md",
    )
    monkeypatch.setattr(governance_status, "LEDGER_DIR", repo / "logs")
    # Redirect agent_audit's ledger writer too, so a synthesised ledger
    # ends up where governance_status looks for it.
    monkeypatch.setattr(agent_audit, "_LEDGER_DIR", repo / "logs")
    # Make git calls deterministic — return None.
    monkeypatch.setattr(governance_status, "_git_branch", lambda: None)
    monkeypatch.setattr(governance_status, "_git_head_sha", lambda: None)
    return repo


# ---------------------------------------------------------------------------
# Shape & determinism
# ---------------------------------------------------------------------------


def test_snapshot_has_stable_top_level_shape(isolated_repo: Path) -> None:
    snap = governance_status.collect_status()
    expected_keys = {
        "schema_version",
        "report_kind",
        "last_evaluation_at_utc",
        "version",
        "git",
        "policy",
        "hooks",
        "autonomy",
        "audit_ledger_today",
        "autonomous_mode",
    }
    assert set(snap.keys()) == expected_keys
    assert snap["schema_version"] == 1
    assert snap["report_kind"] == "governance_status"


def test_snapshot_is_json_serialisable(isolated_repo: Path) -> None:
    snap = governance_status.collect_status()
    encoded = json.dumps(snap, sort_keys=True)
    assert json.loads(encoded) == snap


def test_two_back_to_back_calls_only_differ_in_timestamp(
    isolated_repo: Path,
) -> None:
    a = governance_status.collect_status()
    b = governance_status.collect_status()
    a.pop("last_evaluation_at_utc")
    b.pop("last_evaluation_at_utc")
    assert a == b


# ---------------------------------------------------------------------------
# Empty / missing inputs degrade to unknown
# ---------------------------------------------------------------------------


def test_empty_repo_reports_not_available_or_unknown_not_ok(
    isolated_repo: Path,
) -> None:
    snap = governance_status.collect_status()

    # Hooks: settings.json missing => layer_state must be 'not_available'.
    assert snap["hooks"]["layer_state"] == "not_available"

    # Autonomy: ladder doc missing => 'unknown' on every field.
    autonomy = snap["autonomy"]
    assert autonomy["max_available_level"] == "unknown"
    assert autonomy["available_levels"] == "unknown"
    assert autonomy["level_6_status"] == "unknown"

    # Ledger: file missing => not_available, no chain claim.
    ledger = snap["audit_ledger_today"]
    assert ledger["status"] == "not_available"
    assert ledger["last_event"] is None
    assert ledger["event_count"] == 0
    assert ledger["allowed_count"] == 0
    assert ledger["blocked_count"] == 0

    # Autonomous-mode is *never* reported as 'ok'.
    assert snap["autonomous_mode"]["status"] == "not_machine_enforceable"

    # Version file missing.
    assert snap["version"]["file_version"] is None

    # Defensive: no top-level field uses the literal string 'ok' as its
    # status when the underlying state is missing. This catches any
    # future regression where a contributor types `"ok"` reflexively.
    flat = json.dumps(snap)
    assert '"status": "ok"' not in flat
    assert '"layer_state": "ok"' not in flat


def test_missing_some_hooks_reports_degraded_with_per_hook_inventory(
    isolated_repo: Path,
) -> None:
    settings = isolated_repo / ".claude" / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    (isolated_repo / ".claude" / "hooks" / "deny_no_touch.py").write_text(
        "# stub", encoding="utf-8"
    )

    snap = governance_status.collect_status()
    hooks = snap["hooks"]
    assert hooks["layer_state"] == "degraded"
    inventory = hooks["inventory"]
    assert inventory["deny_no_touch.py"] == "present"
    assert inventory["deny_dangerous_bash.py"] == "missing"


def test_full_hook_set_reports_installed(isolated_repo: Path) -> None:
    (isolated_repo / ".claude" / "settings.json").write_text(
        "{}", encoding="utf-8"
    )
    for name in governance_status.EXPECTED_HOOKS:
        (isolated_repo / ".claude" / "hooks" / name).write_text(
            "# stub", encoding="utf-8"
        )
    snap = governance_status.collect_status()
    assert snap["hooks"]["layer_state"] == "installed"


# ---------------------------------------------------------------------------
# Autonomy ladder parser
# ---------------------------------------------------------------------------


_LADDER_FIXTURE = """\
# Autonomy Ladder

| Level | Capability | Status in this project |
|---|---|---|
| 0 | **Plan / read only**. | Always available |
| 1 | **Docs + tests + frontend**. | Available after v3.15.15.12.3 active |
| 2 | **Observability + CI**. | Available after v3.15.15.12.4 active |
| 3 | **Backend non-core**. | **NOT enabled** in this version. |
| 4 | **Merge recommendation**. | Locked. Requires >=30 days. |
| 5 | **Deploy recommendation**. | Locked. Requires >=60 days. |
| 6 | **Autonomous merge / deploy**. | **Permanently disabled** in this project. |

## Per-agent caps (current)

| Agent | Cap |
|---|---|
| product-owner | 1 |
"""


def test_autonomy_ladder_parses_available_levels(isolated_repo: Path) -> None:
    (isolated_repo / "docs" / "governance" / "autonomy_ladder.md").write_text(
        _LADDER_FIXTURE, encoding="utf-8"
    )
    snap = governance_status.collect_status()
    autonomy = snap["autonomy"]
    assert autonomy["available_levels"] == [0, 1, 2]
    assert autonomy["max_available_level"] == 2
    assert autonomy["level_6_status"] == "permanently_disabled"


def test_autonomy_ladder_with_unparseable_doc_reports_unknown(
    isolated_repo: Path,
) -> None:
    (isolated_repo / "docs" / "governance" / "autonomy_ladder.md").write_text(
        "no table here", encoding="utf-8"
    )
    snap = governance_status.collect_status()
    autonomy = snap["autonomy"]
    assert autonomy["max_available_level"] == "unknown"
    assert autonomy["available_levels"] == "unknown"
    assert autonomy["level_6_status"] == "unknown"


# ---------------------------------------------------------------------------
# Audit ledger summary
# ---------------------------------------------------------------------------


def test_intact_ledger_reports_intact_with_redacted_tail(
    isolated_repo: Path,
) -> None:
    # Two events: one allowed, one blocked. The blocked event carries
    # ``command_summary`` and ``target_path`` that we must NOT surface
    # in ``last_event``.
    agent_audit.append_event(
        {
            "event": "tool_use",
            "tool": "Edit",
            "outcome": "ok",
            "actor": "claude:test",
            "command_summary": "should not leak",
            "target_path": "should/not/leak.py",
        }
    )
    agent_audit.append_event(
        {
            "event": "blocked",
            "tool": "Write",
            "outcome": "blocked_by_hook",
            "block_reason": "no_touch_path matched 'VERSION'",
            "actor": "claude:hook",
            "command_summary": "secret-looking-thing-DO_NOT_LEAK",
            "target_path": "VERSION",
        }
    )
    snap = governance_status.collect_status()
    ledger = snap["audit_ledger_today"]
    assert ledger["status"] == "intact"
    assert ledger["event_count"] == 2
    assert ledger["allowed_count"] == 1
    assert ledger["blocked_count"] == 1
    assert ledger["other_count"] == 0
    last = ledger["last_event"]
    assert last is not None
    assert last["sequence_id"] == 1
    assert last["outcome"] == "blocked_by_hook"
    assert last["tool"] == "Write"
    assert last["block_reason"] == "no_touch_path matched 'VERSION'"

    # Redacted tail must NOT contain user-controlled strings.
    flat = json.dumps(snap)
    assert "should/not/leak.py" not in flat
    assert "should not leak" not in flat
    assert "DO_NOT_LEAK" not in flat


def test_broken_ledger_reports_broken_with_first_corrupt_index(
    isolated_repo: Path,
) -> None:
    agent_audit.append_event({"event": "tool_use", "outcome": "ok"})
    agent_audit.append_event({"event": "tool_use", "outcome": "ok"})
    # Corrupt the first event's hash field.
    path = agent_audit.current_ledger_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["event_sha256"] = "0" * 64
    lines[0] = json.dumps(first, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    snap = governance_status.collect_status()
    ledger = snap["audit_ledger_today"]
    assert ledger["status"] == "broken"
    assert ledger["first_corrupt_index"] == 0


def test_unreadable_ledger_reports_unreadable_or_broken(
    isolated_repo: Path,
) -> None:
    path = agent_audit.current_ledger_path()
    path.write_text("not-json{{{\n", encoding="utf-8")
    snap = governance_status.collect_status()
    assert snap["audit_ledger_today"]["status"] in {"unreadable", "broken"}


# ---------------------------------------------------------------------------
# Secrets / sensitive-path safety
# ---------------------------------------------------------------------------


def test_assert_no_secrets_passes_on_empty_snapshot(
    isolated_repo: Path,
) -> None:
    snap = governance_status.collect_status()
    governance_status.assert_no_secrets(snap)  # must not raise


def test_assert_no_secrets_catches_credential_pattern() -> None:
    leaky = {"some": "sk-ant-AAAAAAAAAAAAAAAAAAAAAAAAA"}
    with pytest.raises(AssertionError, match="credential-like"):
        governance_status.assert_no_secrets(leaky)


def test_assert_no_secrets_allows_no_touch_path_references() -> None:
    """v3.15.15.25.1: path-shaped strings are legitimate metadata.
    The previous broader substring check produced false positives
    that halted the autonomous workloop."""
    for path_ref in governance_status.KNOWN_NO_TOUCH_PATH_REFERENCES:
        governance_status.assert_no_secrets({"path": path_ref})  # must not raise
    governance_status.assert_no_secrets(
        {"summary": "edits to config/config.yaml are forbidden"}
    )


def test_assert_no_secrets_still_catches_aws_key() -> None:
    leaky = {"x": "AKIAEXAMPLE12345"}
    with pytest.raises(AssertionError, match="credential-like"):
        governance_status.assert_no_secrets(leaky)


def test_assert_no_secrets_still_catches_pem_block() -> None:
    leaky = {"x": "-----BEGIN PRIVATE KEY-----"}
    with pytest.raises(AssertionError, match="credential-like"):
        governance_status.assert_no_secrets(leaky)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_emits_same_snapshot_shape_as_collect(
    isolated_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = governance_status.main(["--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    expected_keys = {
        "schema_version",
        "report_kind",
        "last_evaluation_at_utc",
        "version",
        "git",
        "policy",
        "hooks",
        "autonomy",
        "audit_ledger_today",
        "autonomous_mode",
    }
    assert set(parsed.keys()) == expected_keys


def test_cli_default_indent_is_pretty(
    isolated_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = governance_status.main([])
    assert rc == 0
    out = capsys.readouterr().out
    # Pretty JSON has newlines + 2-space indent.
    assert "\n  " in out


# ---------------------------------------------------------------------------
# Frozen-contract integrity
# ---------------------------------------------------------------------------


def test_collect_status_does_not_touch_frozen_contracts() -> None:
    """Run on the *real* repo and assert that the two frozen artifacts
    are byte-identical (or equally absent) before and after the call.

    The diagnostic must never write, rewrite, or even create either
    contract. We capture (existed, sha256) before and after and require
    equality — without skipping, so the test is informative whether or
    not the contracts happen to be present in the working tree.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    research_latest = repo_root / "research" / "research_latest.json"
    strategy_matrix = repo_root / "research" / "strategy_matrix.csv"

    before_a = _existence_and_sha(research_latest)
    before_b = _existence_and_sha(strategy_matrix)

    snapshot = governance_status.collect_status()
    governance_status.assert_no_secrets(snapshot)

    after_a = _existence_and_sha(research_latest)
    after_b = _existence_and_sha(strategy_matrix)

    assert before_a == after_a, "research_latest.json was modified or created"
    assert before_b == after_b, "strategy_matrix.csv was modified or created"

    # Neither contract path appears anywhere in the snapshot; downstream
    # consumers cannot stumble onto them through this surface.
    flat = json.dumps(snapshot)
    assert "research_latest.json" not in flat
    assert "strategy_matrix.csv" not in flat
