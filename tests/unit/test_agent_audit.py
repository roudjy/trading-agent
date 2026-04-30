"""Tests for reporting.agent_audit — hash-chain integrity and redaction.

Covers v3.15.15.12.5 / v3.15.15.12.7. The hash-chain invariants are the
linchpin of agent auditability; if these fail, the chain is no longer
tamper-evident.
"""

from __future__ import annotations

import json
from pathlib import Path

from reporting import agent_audit


def _make_event(actor="claude:test", **extra):
    base = {
        "actor": actor,
        "event": "tool_use",
        "tool": "Edit",
        "outcome": "ok",
    }
    base.update(extra)
    return base


def test_append_creates_file_and_initial_event(tmp_path: Path):
    agent_audit.append_event(_make_event(target_path="x.py"), base_dir=tmp_path)
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    rec = json.loads(text.strip())
    assert rec["sequence_id"] == 0
    assert rec["prev_event_sha256"] is None
    assert rec["event_sha256"]


def test_chain_links_two_events(tmp_path: Path):
    e1 = agent_audit.append_event(_make_event(tool="Edit"), base_dir=tmp_path)
    e2 = agent_audit.append_event(_make_event(tool="Bash"), base_dir=tmp_path)
    assert e2["sequence_id"] == 1
    assert e2["prev_event_sha256"] == e1["event_sha256"]


def test_verify_chain_ok(tmp_path: Path):
    for _ in range(5):
        agent_audit.append_event(_make_event(), base_dir=tmp_path)
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    ok, idx = agent_audit.verify_chain(p)
    assert ok, f"expected OK, got idx={idx}"
    assert idx is None


def test_verify_chain_detects_tamper(tmp_path: Path):
    for i in range(4):
        agent_audit.append_event(_make_event(target_path=f"f{i}.py"), base_dir=tmp_path)
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[2])
    rec["target_path"] = "tampered.py"
    lines[2] = json.dumps(rec, sort_keys=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, idx = agent_audit.verify_chain(p)
    assert not ok
    assert idx == 2


def test_verify_chain_detects_deletion(tmp_path: Path):
    for i in range(4):
        agent_audit.append_event(_make_event(target_path=f"f{i}.py"), base_dir=tmp_path)
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    del lines[1]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, idx = agent_audit.verify_chain(p)
    assert not ok
    assert idx is not None and idx >= 1


def test_redaction_anthropic_key(tmp_path: Path):
    leak = "sk-ant-" + "A" * 60
    rec = agent_audit.append_event(
        _make_event(command_summary=f"echo {leak}"), base_dir=tmp_path
    )
    assert leak not in rec["command_summary"]
    assert "[REDACTED]" in rec["command_summary"]
    assert rec["redacted"] is True


def test_redaction_long_hex(tmp_path: Path):
    hex_blob = "a1b2c3d4" * 10  # 80 chars hex
    rec = agent_audit.append_event(
        _make_event(command_summary=f"key={hex_blob}"), base_dir=tmp_path
    )
    assert hex_blob not in rec["command_summary"]
    assert rec["redacted"] is True


def test_diff_summary_extra_keys_dropped(tmp_path: Path):
    rec = agent_audit.append_event(
        _make_event(
            diff_summary={
                "lines_added": 1,
                "lines_removed": 0,
                "content_sha256": "deadbeef",
                "secret_payload": "must-be-stripped",
            }
        ),
        base_dir=tmp_path,
    )
    assert "secret_payload" not in rec["diff_summary"]
    assert rec["redacted"] is True


def test_iter_events_returns_in_order(tmp_path: Path):
    for i in range(3):
        agent_audit.append_event(_make_event(target_path=f"f{i}.py"), base_dir=tmp_path)
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    seen = list(agent_audit.iter_events(p))
    assert [e["sequence_id"] for e in seen] == [0, 1, 2]


def test_iter_events_empty_file(tmp_path: Path):
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    p.touch()
    assert list(agent_audit.iter_events(p)) == []


def test_canonical_bytes_excludes_event_sha256():
    rec = {
        "sequence_id": 0,
        "event_sha256": "ignored_during_canon",
        "actor": "claude:test",
    }
    canon = agent_audit._canonical_bytes(rec)
    assert b"ignored_during_canon" not in canon
    assert b'"actor":"claude:test"' in canon


def test_session_id_preserved(tmp_path: Path):
    rec = agent_audit.append_event(
        _make_event(session_id="abc-123"),
        base_dir=tmp_path,
    )
    assert rec["session_id"] == "abc-123"


def test_locked_handle_avoids_windows_permission_error(tmp_path: Path):
    # Regression for the v3.15.15.12.3 fix where _read_last_event opened
    # a second handle while holding the file lock — this raised
    # PermissionError on Windows. Now reads from the locked handle.
    for _ in range(3):
        agent_audit.append_event(_make_event(), base_dir=tmp_path)
    p = agent_audit.current_ledger_path(base_dir=tmp_path)
    ok, _ = agent_audit.verify_chain(p)
    assert ok
