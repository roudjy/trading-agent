"""Tests for research._sidecar_io (v3.12 canonical sidecar helper)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research._sidecar_io import (
    CANONICAL_JSON_KWARGS,
    SchemaContractError,
    require_schema_version,
    serialize_canonical,
    write_sidecar_atomic,
)


def test_canonical_kwargs_are_deterministic_by_design() -> None:
    assert CANONICAL_JSON_KWARGS["sort_keys"] is True
    assert CANONICAL_JSON_KWARGS["ensure_ascii"] is False
    assert CANONICAL_JSON_KWARGS["indent"] == 2
    assert CANONICAL_JSON_KWARGS["separators"] == (",", ": ")


def test_serialize_canonical_is_stable_across_dict_orderings() -> None:
    a = {"z": 1, "a": 2, "m": {"q": 3, "b": 4}}
    b = {"m": {"b": 4, "q": 3}, "a": 2, "z": 1}
    assert serialize_canonical(a) == serialize_canonical(b)


def test_serialize_canonical_has_trailing_newline_and_lf() -> None:
    out = serialize_canonical({"a": 1})
    assert out.endswith("\n")
    assert "\r\n" not in out


def test_serialize_canonical_preserves_unicode_verbatim() -> None:
    payload = {"name": "trend_café"}
    out = serialize_canonical(payload)
    assert "café" in out
    assert "\\u00e9" not in out


def test_write_sidecar_atomic_writes_canonical_bytes(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    payload = {"schema_version": "1.0", "b": 2, "a": 1}

    write_sidecar_atomic(target, payload)

    raw = target.read_bytes()
    expected = serialize_canonical(payload).encode("utf-8")
    assert raw == expected


def test_write_sidecar_atomic_creates_missing_parent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "artifact.json"
    write_sidecar_atomic(target, {"k": "v"})
    assert target.exists()
    # round-trip loads cleanly
    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "v"}


def test_write_sidecar_atomic_leaves_no_tmp_file(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    write_sidecar_atomic(target, {"k": "v"})
    # no leftover .tmp siblings
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_write_sidecar_atomic_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    write_sidecar_atomic(target, {"version": 1})
    write_sidecar_atomic(target, {"version": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}


def test_require_schema_version_passes_on_match() -> None:
    require_schema_version({"schema_version": "2.0"}, "2.0")


def test_require_schema_version_raises_on_mismatch() -> None:
    with pytest.raises(SchemaContractError):
        require_schema_version({"schema_version": "1.0"}, "2.0")


def test_require_schema_version_raises_on_missing_field() -> None:
    with pytest.raises(SchemaContractError):
        require_schema_version({}, "1.0")


def test_write_sidecar_atomic_byte_equal_across_repeated_writes(tmp_path: Path) -> None:
    target_a = tmp_path / "a.json"
    target_b = tmp_path / "b.json"
    payload = {"items": [{"z": 9, "a": 1}, {"a": 2, "z": 8}]}

    write_sidecar_atomic(target_a, payload)
    write_sidecar_atomic(target_b, payload)

    assert target_a.read_bytes() == target_b.read_bytes()
