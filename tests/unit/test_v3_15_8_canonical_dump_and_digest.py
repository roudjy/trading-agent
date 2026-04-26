"""v3.15.8 — canonical sample dump uses ``allow_nan=False``; the
digest is deterministic, hash-randomness immune, and changes when
the underlying samples change.
"""

from __future__ import annotations

import json
import math

import pytest

from research.candidate_pipeline import (
    _canonical_param_dump,
    _compute_sampled_parameter_digest,
    _json_safe_param_value,
)


def test_json_safe_param_value_coerces_nan_and_inf_to_none() -> None:
    assert _json_safe_param_value(float("nan")) is None
    assert _json_safe_param_value(float("inf")) is None
    assert _json_safe_param_value(float("-inf")) is None


def test_json_safe_param_value_keeps_primitives() -> None:
    for value in (None, 0, 1, -42, 1.5, "hello", True, False):
        assert _json_safe_param_value(value) == value


def test_canonical_dump_rejects_unsanitised_nan() -> None:
    """Direct unsanitised NaN must raise; this proves
    ``allow_nan=False`` is in effect.
    """
    with pytest.raises(ValueError):
        json.dumps({"x": float("nan")}, allow_nan=False)


def test_canonical_dump_rejects_inf() -> None:
    with pytest.raises(ValueError):
        json.dumps({"x": float("inf")}, allow_nan=False)


def test_canonical_dump_with_sanitised_nan_succeeds() -> None:
    samples = [{"a": _json_safe_param_value(float("nan"))}]
    dump = _canonical_param_dump(samples)
    assert "NaN" not in dump
    # round-trip
    assert json.loads(dump) == [{"a": None}]


def test_digest_is_stable_across_repeated_calls() -> None:
    samples = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    first = _compute_sampled_parameter_digest(samples)
    for _ in range(10):
        assert _compute_sampled_parameter_digest(samples) == first


def test_digest_is_independent_of_dict_key_insertion_order() -> None:
    a = _compute_sampled_parameter_digest([{"a": 1, "b": 2}])
    b = _compute_sampled_parameter_digest([{"b": 2, "a": 1}])
    assert a == b


def test_digest_changes_when_sample_values_change() -> None:
    base = _compute_sampled_parameter_digest([{"a": 1}])
    altered = _compute_sampled_parameter_digest([{"a": 2}])
    assert base != altered


def test_digest_changes_when_a_sample_is_added() -> None:
    base = _compute_sampled_parameter_digest([{"a": 1}])
    longer = _compute_sampled_parameter_digest([{"a": 1}, {"a": 2}])
    assert base != longer


def test_digest_is_hex_lowercase_sha1() -> None:
    digest = _compute_sampled_parameter_digest([{"a": 1}])
    assert len(digest) == 40
    assert digest == digest.lower()
    int(digest, 16)  # raises if not hex


def test_canonical_dump_is_compact_and_sorted() -> None:
    dump = _canonical_param_dump([{"b": 2, "a": 1}])
    assert dump == '[{"a":1,"b":2}]'


def test_canonical_dump_handles_non_finite_after_sanitisation() -> None:
    samples = [{"a": _json_safe_param_value(math.nan)}]
    # must not raise
    _canonical_param_dump(samples)
