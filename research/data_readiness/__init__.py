"""Fail-closed fundamental data readiness surfaces for equity-factor research."""

from research.data_readiness.factor_field_coverage import build_factor_field_coverage
from research.data_readiness.factor_field_coverage_manifest import write_outputs as write_factor_field_coverage_outputs
from research.data_readiness.fundamental_readiness import build_fundamental_readiness

__all__ = [
    "build_factor_field_coverage",
    "build_fundamental_readiness",
    "write_factor_field_coverage_outputs",
]
