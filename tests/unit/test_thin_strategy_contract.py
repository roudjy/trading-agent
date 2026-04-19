"""Unit tests for the thin strategy contract v1.0 (transitional).

Covers:
- declare_thin metadata stamping
- build_features_for resolution and missing-column failure
- validate_thin_strategy_output shape/dtype/index checks
- determinism across repeated calls
- an AST scan that forbids thin strategy bodies from reading raw
  OHLCV columns off df (only df.index is allowed)

The AST guard is the architectural teeth of the v1.0 contract: it
enforces that data access flows through `features` rather than through
the DataFrame. Legacy strategies are not scanned, since they still
use the func(df) signature; only callables produced by declare_thin
opt into the stricter rule.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Mapping

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.thin_strategy import (
    FeatureRequirement,
    THIN_CONTRACT_VERSION,
    build_features_for,
    declare_thin,
    is_thin_strategy,
    validate_thin_strategy_output,
)
from tests._harness_helpers import build_ohlcv_frame


def _toy_thin_factory():
    requirements = [FeatureRequirement(name="sma", params={"window": 5})]

    def raw(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        sma = features["sma"]
        sig = pd.Series(0, index=df.index)
        sig[sma > 0] = 1
        return sig

    return declare_thin(raw, feature_requirements=requirements)


def test_declare_thin_stamps_contract_version() -> None:
    func = _toy_thin_factory()

    assert is_thin_strategy(func)
    assert func._thin_contract_version == THIN_CONTRACT_VERSION
    assert func._sizing_spec is None


def test_declare_thin_rejects_unknown_feature() -> None:
    def raw(df, features):
        return pd.Series(0, index=df.index)

    with pytest.raises(ValueError, match="unknown feature"):
        declare_thin(raw, feature_requirements=[FeatureRequirement("bogus", {})])


def test_build_features_for_resolves_registered_primitive() -> None:
    frame = build_ohlcv_frame(length=30, seed=11)
    reqs = [FeatureRequirement(name="sma", params={"window": 5})]

    out = build_features_for(reqs, frame)

    assert set(out.keys()) == {"sma"}
    assert out["sma"].index.equals(frame.index)
    assert out["sma"].iloc[:4].isna().all()


def test_build_features_for_respects_alias() -> None:
    frame = build_ohlcv_frame(length=30, seed=13)
    reqs = [FeatureRequirement(name="ema", params={"span": 10}, alias="trend")]

    out = build_features_for(reqs, frame)

    assert list(out.keys()) == ["trend"]
    assert out["trend"].index.equals(frame.index)


def test_build_features_for_raises_on_missing_column() -> None:
    frame = build_ohlcv_frame(length=30, seed=17)[["open", "high", "low", "volume"]]
    reqs = [FeatureRequirement(name="sma", params={"window": 5})]

    with pytest.raises(KeyError, match="missing"):
        build_features_for(reqs, frame)


def test_validate_thin_strategy_output_accepts_int_and_float_series() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    ok_int = pd.Series([0, 1, -1, 0, 1], index=idx, dtype=np.int64)
    ok_float = pd.Series([0.0, 0.5, -0.5, 0.0, 1.0], index=idx, dtype=np.float64)

    validate_thin_strategy_output(ok_int, idx)
    validate_thin_strategy_output(ok_float, idx)


def test_validate_thin_strategy_output_rejects_index_mismatch() -> None:
    idx_a = pd.date_range("2024-01-01", periods=5, freq="D")
    idx_b = pd.date_range("2024-01-02", periods=5, freq="D")
    sig = pd.Series([0, 1, 0, 1, 0], index=idx_a)

    with pytest.raises(ValueError, match="index"):
        validate_thin_strategy_output(sig, idx_b)


def test_validate_thin_strategy_output_rejects_non_series() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D")

    with pytest.raises(ValueError, match="pd.Series"):
        validate_thin_strategy_output([0, 1, 0], idx)  # type: ignore[arg-type]


def test_validate_thin_strategy_output_rejects_non_numeric_dtype() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    sig = pd.Series(["a", "b", "c"], index=idx)

    with pytest.raises(ValueError, match="dtype"):
        validate_thin_strategy_output(sig, idx)


def test_thin_strategy_output_is_deterministic_across_calls() -> None:
    frame = build_ohlcv_frame(length=60, seed=19)
    strategy = _toy_thin_factory()
    features = build_features_for(strategy._feature_requirements, frame)

    first = strategy(frame, features)
    second = strategy(frame, features)

    pd.testing.assert_series_equal(first, second)
    assert first.to_numpy(copy=True).tobytes() == second.to_numpy(copy=True).tobytes()


def test_declare_thin_accepts_sizing_spec_as_opaque_dict() -> None:
    def raw(df, features):
        return pd.Series(0, index=df.index)

    func = declare_thin(
        raw,
        feature_requirements=[],
        sizing_spec={"regime": "fixed_unit", "target_vol": 0.1},
    )

    assert func._sizing_spec == {"regime": "fixed_unit", "target_vol": 0.1}


def _read_strategy_body_ast(func) -> ast.AST:
    source = textwrap.dedent(inspect.getsource(func))
    return ast.parse(source)


class _DfColumnAccessVisitor(ast.NodeVisitor):
    """Flags any df[...] or df.<attr> access except df.index."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        target = node.value
        if isinstance(target, ast.Name) and target.id == "df":
            self.violations.append(
                f"df[] subscript at line {node.lineno}"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        target = node.value
        if isinstance(target, ast.Name) and target.id == "df":
            if node.attr != "index":
                self.violations.append(
                    f"df.{node.attr} access at line {node.lineno}"
                )
        self.generic_visit(node)


def test_thin_strategy_body_reads_only_df_index() -> None:
    """AST scan: the toy thin factory's body must not touch df columns."""

    def raw(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        sma = features["sma"]
        sig = pd.Series(0, index=df.index)
        sig[sma > 0] = 1
        return sig

    tree = _read_strategy_body_ast(raw)
    visitor = _DfColumnAccessVisitor()
    visitor.visit(tree)

    assert not visitor.violations, (
        "thin strategy body referenced df beyond df.index: "
        f"{visitor.violations}"
    )


def test_ast_scanner_flags_direct_column_access() -> None:
    """The scanner must actually catch violations when present."""

    def offender(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        close = df["close"]
        return pd.Series(0, index=close.index)

    tree = _read_strategy_body_ast(offender)
    visitor = _DfColumnAccessVisitor()
    visitor.visit(tree)

    assert any("df[]" in msg for msg in visitor.violations)


def test_ast_scanner_flags_attribute_access() -> None:
    def offender(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        close = df.close
        return pd.Series(0, index=close.index)

    tree = _read_strategy_body_ast(offender)
    visitor = _DfColumnAccessVisitor()
    visitor.visit(tree)

    assert any("df.close" in msg for msg in visitor.violations)


def test_feature_requirements_stay_in_sync_with_body_usage() -> None:
    """A thin strategy must actually consume every feature it declares."""

    def raw(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        sma = features["sma"]
        sig = pd.Series(0, index=df.index)
        sig[sma > 0] = 1
        return sig

    declared = [FeatureRequirement(name="sma", params={"window": 5})]
    aliases = {req.resolved_alias() for req in declared}

    source = textwrap.dedent(inspect.getsource(raw))
    used = {
        ast.literal_eval(node.slice)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "features"
        and isinstance(node.slice, ast.Constant)
    }

    assert used == aliases
