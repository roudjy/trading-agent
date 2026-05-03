"""Unit tests for ``reporting.agent_audit_summary``.

Properties under test:

* read-only — neither view writes to the ledger or any other path;
* events are sorted by ``sequence_id`` ascending in the timeline view;
* missing actor / branch / head_sha / session degrade to ``"unknown"``;
* unknown chain status never reports ``"intact"`` and never ``"ok"``;
* credential-pattern strings are redacted out of every projection;
* sensitive-path fragments raise from ``assert_no_secrets``;
* malformed lines are *counted*, never raised — the CLI keeps working;
* ``target_path`` is **never** surfaced verbatim — only its parent
  directory is exposed via ``target_dir``;
* the CLI emits valid JSON in JSON mode and a non-empty text table in
  table mode, exit code 0 in both cases;
* frozen contracts (``research_latest.json``, ``strategy_matrix.csv``)
  are not opened or modified.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

import pytest

from reporting import agent_audit, agent_audit_summary

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
def ledger_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect both writers and the summary path-resolver to ``tmp_path``."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr(agent_audit, "_LEDGER_DIR", logs_dir)
    monkeypatch.setattr(agent_audit_summary, "REPO_ROOT", tmp_path)
    return agent_audit.current_ledger_path()


def _seed_two_events(ledger_path: Path) -> None:
    """Append one ok and one blocked event so each test can rely on a
    canonical two-event fixture without re-stating it."""
    agent_audit.append_event(
        {
            "event": "tool_use",
            "tool": "Edit",
            "outcome": "ok",
            "actor": "claude:audit_emit",
            "session_id": "sess-A",
            "branch": "feat/x",
            "head_sha": "abc123" * 6 + "abcd",
            "command_summary": "should-not-leak",
            "target_path": "dashboard/api_observability.py",
        }
    )
    agent_audit.append_event(
        {
            "event": "blocked",
            "tool": "Write",
            "outcome": "blocked_by_hook",
            "block_reason": "no_touch_path matched 'VERSION'",
            "actor": "claude:hook",
            "session_id": "sess-A",
            "branch": "feat/x",
            "head_sha": "abc123" * 6 + "abcd",
            "command_summary": "DO_NOT_LEAK_payload",
            "target_path": "VERSION",
        }
    )


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------


def test_views_do_not_mutate_the_ledger(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    before = _file_sha256(ledger_path)
    agent_audit_summary.collect_timeline(ledger_path, limit=10)
    agent_audit_summary.collect_groups(ledger_path)
    after = _file_sha256(ledger_path)
    assert before == after, "summary views modified the ledger"


# ---------------------------------------------------------------------------
# Timeline shape & ordering
# ---------------------------------------------------------------------------


def test_timeline_events_sorted_by_sequence_id(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    seqs = [r["sequence_id"] for r in snap["rows"]]
    assert seqs == sorted(seqs)
    assert seqs == [0, 1]


def test_timeline_redacts_target_path_to_directory_only(
    ledger_path: Path,
) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    flat = json.dumps(snap)
    # The full path must not appear anywhere in the projection.
    assert "api_observability.py" not in flat
    # But the parent directory ("dashboard") should be there as target_dir.
    target_dirs = [r["target_dir"] for r in snap["rows"]]
    assert "dashboard" in target_dirs


def test_timeline_omits_command_and_diff_payloads(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    flat = json.dumps(snap)
    assert "DO_NOT_LEAK_payload" not in flat
    assert "should-not-leak" not in flat
    # No keys named command_summary / diff_summary / target_path should
    # appear inside any row.
    for row in snap["rows"]:
        assert "command_summary" not in row
        assert "diff_summary" not in row
        assert "target_path" not in row


def test_timeline_filter_by_actor(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_timeline(
        ledger_path, limit=10, actor="claude:hook"
    )
    assert all(r["actor"] == "claude:hook" for r in snap["rows"])
    assert len(snap["rows"]) == 1


def test_timeline_filter_by_outcome(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_timeline(
        ledger_path, limit=10, outcome="blocked_by_hook"
    )
    assert all(r["outcome"] == "blocked_by_hook" for r in snap["rows"])
    assert len(snap["rows"]) == 1


def test_timeline_limit_returns_only_last_n(ledger_path: Path) -> None:
    for i in range(5):
        agent_audit.append_event(
            {"event": "tool_use", "outcome": "ok", "actor": f"claude:test{i}"}
        )
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=2)
    seqs = [r["sequence_id"] for r in snap["rows"]]
    assert seqs == [3, 4]


# ---------------------------------------------------------------------------
# Missing field handling — never "ok", always "unknown"
# ---------------------------------------------------------------------------


def test_missing_optional_fields_become_unknown(ledger_path: Path) -> None:
    # Append an event with several fields explicitly absent. The writer
    # fills `actor` with `claude:unknown` if not given, but branch /
    # head_sha / session_id pass through as None and must surface as
    # "unknown" in the projection.
    agent_audit.append_event({"event": "tool_use", "outcome": "ok"})
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    row = snap["rows"][0]
    assert row["branch"] == "unknown"
    assert row["head_sha"] == "unknown"
    assert row["session_id"] == "unknown"
    assert row["target_dir"] == "unknown"


def test_chain_status_never_ok_when_file_missing(ledger_path: Path) -> None:
    # File never created.
    missing = ledger_path.parent / "agent_audit.1999-01-01.jsonl"
    snap = agent_audit_summary.collect_timeline(missing, limit=10)
    assert snap["chain_status"] == "not_available"
    assert snap["chain_status"] != "ok"


def test_chain_status_intact_when_chain_intact(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_groups(ledger_path)
    assert snap["chain_status"] == "intact"
    assert snap["first_corrupt_index"] is None


def test_chain_status_broken_when_chain_broken(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    # Corrupt the first event.
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["event_sha256"] = "0" * 64
    lines[0] = json.dumps(first, sort_keys=True)
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    snap = agent_audit_summary.collect_groups(ledger_path)
    assert snap["chain_status"] == "broken"
    assert snap["first_corrupt_index"] == 0


# ---------------------------------------------------------------------------
# Malformed input safety
# ---------------------------------------------------------------------------


def test_malformed_lines_are_counted_not_raised(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    # Append two malformed lines: one non-JSON, one wrong-shape JSON.
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write("not-json{{{\n")
        f.write(json.dumps({"hello": "world"}) + "\n")  # missing schema
    timeline = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    groups = agent_audit_summary.collect_groups(ledger_path)
    assert timeline["malformed_line_count"] == 2
    assert groups["malformed_line_count"] == 2
    assert timeline["ledger_event_count"] == 2  # the two valid events


# ---------------------------------------------------------------------------
# Group view aggregates
# ---------------------------------------------------------------------------


def test_groups_aggregates_by_actor_outcome_branch_session(
    ledger_path: Path,
) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_groups(ledger_path)
    assert snap["by_actor"] == {"claude:audit_emit": 1, "claude:hook": 1}
    assert snap["by_outcome"] == {"blocked_by_hook": 1, "ok": 1}
    assert snap["by_branch"] == {"feat/x": 2}
    assert snap["by_session"] == {"sess-A": 2}
    # Sorted iteration — keys appear in deterministic order.
    assert list(snap["by_actor"].keys()) == sorted(snap["by_actor"].keys())


# ---------------------------------------------------------------------------
# Secret-redaction safety
# ---------------------------------------------------------------------------


def test_assert_no_secrets_passes_on_clean_snapshot(ledger_path: Path) -> None:
    _seed_two_events(ledger_path)
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    agent_audit_summary.assert_no_secrets(snap)  # must not raise


def test_assert_no_secrets_catches_credential_pattern() -> None:
    leaky = {"some": "ghp_AAAAAAAAAAAAAAAAAAAAAAAAA"}
    with pytest.raises(AssertionError, match="credential-like"):
        agent_audit_summary.assert_no_secrets(leaky)


def test_assert_no_secrets_allows_no_touch_path_references() -> None:
    """v3.15.15.25.1: ``config/config.yaml`` (and the other entries in
    ``KNOWN_NO_TOUCH_PATH_REFERENCES``) are NO-TOUCH paths whose
    *contents* must never be surfaced, but whose *names* are
    legitimate evidence in ``affected_files`` / ``forbidden_actions``
    metadata. The guard must not trip on path-shaped strings — the
    previous broader substring check halted the approval inbox
    runtime on every proposal that referenced a no-touch path.
    """
    for path_ref in agent_audit_summary.KNOWN_NO_TOUCH_PATH_REFERENCES:
        agent_audit_summary.assert_no_secrets({"x": path_ref})  # must not raise

    # Also accept paths embedded in larger strings — proposals
    # commonly inline these in summaries.
    agent_audit_summary.assert_no_secrets(
        {"summary": "edits config/config.yaml are forbidden"}
    )
    agent_audit_summary.assert_no_secrets(
        {"affected_files": ["config/config.yaml", "SECURITY.md"]}
    )


def test_assert_no_secrets_still_catches_anthropic_key() -> None:
    leaky = {"x": "leak: sk-ant-AAAAAAAA1234"}
    with pytest.raises(AssertionError, match="credential-like"):
        agent_audit_summary.assert_no_secrets(leaky)


def test_assert_no_secrets_still_catches_aws_key() -> None:
    leaky = {"x": "AKIAEXAMPLE12345"}
    with pytest.raises(AssertionError, match="credential-like"):
        agent_audit_summary.assert_no_secrets(leaky)


def test_assert_no_secrets_still_catches_pem_block() -> None:
    leaky = {"x": "-----BEGIN PRIVATE KEY-----"}
    with pytest.raises(AssertionError, match="credential-like"):
        agent_audit_summary.assert_no_secrets(leaky)


def test_assert_no_secrets_still_catches_github_pat() -> None:
    leaky = {"x": "github_pat_AAAAAAAAAAAA"}
    with pytest.raises(AssertionError, match="credential-like"):
        agent_audit_summary.assert_no_secrets(leaky)


def test_credential_string_in_event_is_scrubbed_in_projection(
    ledger_path: Path,
) -> None:
    # Inject a credential-shaped value into an event field that the
    # projection keeps. The writer will already redact some patterns,
    # but for fields that bypass writer redaction (e.g. block_reason),
    # the projection must still scrub.
    agent_audit.append_event(
        {
            "event": "blocked",
            "tool": "Bash",
            "outcome": "blocked_by_hook",
            "block_reason": "fake leak ghp_QQQQQQQQQQQQQQQQQQQQQQ here",
            "actor": "claude:hook",
        }
    )
    snap = agent_audit_summary.collect_timeline(ledger_path, limit=10)
    flat = json.dumps(snap)
    assert "ghp_QQQQQQQQQQQQQQQQQQQQQQ" not in flat
    assert "[REDACTED]" in flat


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_json_mode_returns_zero_and_valid_json(
    ledger_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_two_events(ledger_path)
    rc = agent_audit_summary.main(
        ["--path", str(ledger_path), "--view", "both", "--format", "json", "--indent", "0"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "timeline" in parsed
    assert "groups" in parsed


def test_cli_table_mode_renders_header_and_rows(
    ledger_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_two_events(ledger_path)
    rc = agent_audit_summary.main(
        ["--path", str(ledger_path), "--view", "timeline", "--format", "table"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "sequence_id" in out
    assert "actor" in out
    assert "claude:hook" in out


def test_cli_returns_zero_on_missing_ledger(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "nope.jsonl"
    rc = agent_audit_summary.main(
        ["--path", str(missing), "--view", "groups", "--format", "json"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["groups"]["chain_status"] == "not_available"
    assert parsed["groups"]["ledger_event_count"] == 0


# ---------------------------------------------------------------------------
# Frozen-contract integrity
# ---------------------------------------------------------------------------


def test_collect_views_do_not_touch_frozen_contracts() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    research_latest = repo_root / "research" / "research_latest.json"
    strategy_matrix = repo_root / "research" / "strategy_matrix.csv"

    before_a = _existence_and_sha(research_latest)
    before_b = _existence_and_sha(strategy_matrix)

    # Use today's real ledger if it exists; either way, the test must
    # not write to the frozen contracts.
    today = (
        repo_root
        / "logs"
        / f"agent_audit.{_dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d')}.jsonl"
    )
    timeline = agent_audit_summary.collect_timeline(today, limit=5)
    groups = agent_audit_summary.collect_groups(today)
    agent_audit_summary.assert_no_secrets({"timeline": timeline, "groups": groups})

    after_a = _existence_and_sha(research_latest)
    after_b = _existence_and_sha(strategy_matrix)
    assert before_a == after_a, "research_latest.json was modified"
    assert before_b == after_b, "strategy_matrix.csv was modified"

    # And neither contract path appears in either view.
    flat = json.dumps({"timeline": timeline, "groups": groups})
    assert "research_latest.json" not in flat
    assert "strategy_matrix.csv" not in flat
