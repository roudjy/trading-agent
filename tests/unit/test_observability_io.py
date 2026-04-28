"""Unit tests for research.diagnostics.io read helpers."""

from __future__ import annotations

import json
from pathlib import Path

from research.diagnostics.io import (
    JsonReadResult,
    JsonlTailResult,
    read_json_safe,
    read_jsonl_tail_safe,
)


def test_read_json_safe_absent(tmp_path: Path):
    result = read_json_safe(tmp_path / "missing.json")
    assert isinstance(result, JsonReadResult)
    assert result.state == "absent"
    assert result.payload is None
    assert result.size_bytes is None


def test_read_json_safe_valid(tmp_path: Path):
    p = tmp_path / "valid.json"
    p.write_text(json.dumps({"a": 1}), encoding="utf-8")
    result = read_json_safe(p)
    assert result.state == "valid"
    assert result.payload == {"a": 1}
    assert result.size_bytes is not None and result.size_bytes > 0
    assert result.modified_at_unix is not None


def test_read_json_safe_empty(tmp_path: Path):
    p = tmp_path / "empty.json"
    p.write_text("   \n", encoding="utf-8")
    result = read_json_safe(p)
    assert result.state == "empty"
    assert result.payload is None


def test_read_json_safe_invalid(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    result = read_json_safe(p)
    assert result.state == "invalid_json"
    assert result.payload is None
    assert result.error_message  # non-empty


def test_read_jsonl_tail_absent(tmp_path: Path):
    result = read_jsonl_tail_safe(
        tmp_path / "missing.jsonl",
        max_lines=10,
        max_tail_bytes=1024,
    )
    assert isinstance(result, JsonlTailResult)
    assert result.state == "absent"
    assert result.events == []


def test_read_jsonl_tail_basic(tmp_path: Path):
    p = tmp_path / "ev.jsonl"
    lines = [json.dumps({"i": i}) for i in range(5)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = read_jsonl_tail_safe(p, max_lines=10, max_tail_bytes=1024)
    assert result.state == "valid"
    assert [e["i"] for e in result.events] == [0, 1, 2, 3, 4]
    assert result.lines_consumed == 5
    assert result.parse_errors == 0
    assert result.truncated is False
    assert result.partial_trailing_line_dropped is False


def test_read_jsonl_tail_bounded_drops_oldest(tmp_path: Path):
    p = tmp_path / "ev.jsonl"
    lines = [json.dumps({"i": i}) for i in range(20)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = read_jsonl_tail_safe(p, max_lines=5, max_tail_bytes=4096)
    assert result.state == "valid"
    assert [e["i"] for e in result.events] == [15, 16, 17, 18, 19]
    assert result.truncated is True


def test_read_jsonl_tail_drops_partial_trailing_line(tmp_path: Path):
    p = tmp_path / "ev.jsonl"
    # Last "line" lacks a trailing newline — simulating an in-flight write.
    p.write_text(
        json.dumps({"i": 1}) + "\n" + json.dumps({"i": 2}) + "\n" + '{"i": 3',
        encoding="utf-8",
    )
    result = read_jsonl_tail_safe(p, max_lines=10, max_tail_bytes=4096)
    assert result.partial_trailing_line_dropped is True
    assert [e["i"] for e in result.events] == [1, 2]


def test_read_jsonl_tail_skips_malformed_lines_and_counts_them(tmp_path: Path):
    p = tmp_path / "ev.jsonl"
    p.write_text(
        json.dumps({"i": 1})
        + "\n"
        + "garbage\n"
        + json.dumps({"i": 2})
        + "\n",
        encoding="utf-8",
    )
    result = read_jsonl_tail_safe(p, max_lines=10, max_tail_bytes=4096)
    assert result.state == "valid"
    assert [e["i"] for e in result.events] == [1, 2]
    assert result.parse_errors == 1
    assert result.partial_trailing_line_dropped is False
