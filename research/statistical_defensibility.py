"""Deterministic statistical defensibility helpers for research reporting.

The functions in this module are pure and perform no I/O.
"""

import math
from typing import Callable

import numpy as np

EULER_GAMMA = 0.5772156649015329

_LOWER_TAIL_BREAK = 0.02425
_UPPER_TAIL_BREAK = 1.0 - _LOWER_TAIL_BREAK
_ACKLAM_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_ACKLAM_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_ACKLAM_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_ACKLAM_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    n_obs: int,
    skew: float,
    kurt: float,
    benchmark_sharpe: float = 0.0,
) -> float | None:
    """Return the Probabilistic Sharpe Ratio under the Bailey/Lopez de Prado approximation.

    Assumptions:
    - return observations are IID for the horizon used to estimate the Sharpe ratio
    - `n_obs` is the number of return observations used to estimate `observed_sharpe`
    - `skew` and `kurt` are the sample third and Pearson fourth moments of those returns

    Parameters:
    - `observed_sharpe`: the observed Sharpe ratio of the strategy under test
    - `n_obs`: count of return observations used in the estimate
    - `skew`: sample skewness of the return observations
    - `kurt`: sample Pearson kurtosis of the return observations
    - `benchmark_sharpe`: null-hypothesis Sharpe ratio, defaulting to `0.0`

    Return semantics:
    - returns a probability in `[0.0, 1.0]`
    - returns `None` when there are too few observations or the denominator is non-positive

    References:
    - Bailey, D. H. and Lopez de Prado, M. "The Sharpe Ratio Efficient Frontier"
    - Bailey, D. H. and Lopez de Prado, M. "The Deflated Sharpe Ratio"
    """
    if n_obs is None or n_obs <= 1:
        return None

    denominator_term = 1.0 - (skew * observed_sharpe) + (((kurt - 1.0) / 4.0) * (observed_sharpe ** 2))
    if denominator_term <= 0.0:
        return None

    z_score = ((observed_sharpe - benchmark_sharpe) * math.sqrt(n_obs - 1)) / math.sqrt(denominator_term)
    return _standard_normal_cdf(z_score)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_obs: int,
    skew: float,
    kurt: float,
    n_trials: int,
    var_of_trial_sharpes: float,
) -> float | None:
    """Return the canonical Deflated Sharpe Ratio for a multiple-testing scope.

    Assumptions:
    - the Probabilistic Sharpe Ratio assumptions hold
    - `n_trials` is the explicit count of tested variants in the multiple-testing scope
    - `var_of_trial_sharpes` approximates the variance of Sharpe ratios across those trials

    Parameters:
    - `observed_sharpe`: observed Sharpe ratio for the selected strategy
    - `n_obs`: count of return observations used to estimate `observed_sharpe`
    - `skew`: sample skewness of the return observations
    - `kurt`: sample Pearson kurtosis of the return observations
    - `n_trials`: explicit multiple-testing trial count; must be positive
    - `var_of_trial_sharpes`: variance estimate for Sharpe ratios across the trial scope

    Return semantics:
    - returns a probability in `[0.0, 1.0]`
    - returns `None` when the underlying Probabilistic Sharpe Ratio is undefined
    - raises `ValueError` when `n_trials` is missing or non-positive

    References:
    - Bailey, D. H. and Lopez de Prado, M. "The Deflated Sharpe Ratio"
    """
    if n_trials is None or n_trials <= 0:
        raise ValueError("n_trials must be supplied explicitly and be greater than zero")
    if var_of_trial_sharpes < 0.0:
        raise ValueError("var_of_trial_sharpes must be non-negative")

    benchmark_sharpe = _expected_max_trial_sharpe(n_trials=n_trials, var_of_trial_sharpes=var_of_trial_sharpes)
    return probabilistic_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_obs=n_obs,
        skew=skew,
        kurt=kurt,
        benchmark_sharpe=benchmark_sharpe,
    )


def bootstrap_metric_ci(
    samples: np.ndarray | list[float],
    metric_fn: Callable[[np.ndarray], float],
    n_resamples: int,
    ci: float = 0.95,
    seed: int = 1337,
) -> dict[str, float]:
    """Return an IID bootstrap confidence interval for a scalar metric.

    Assumptions:
    - samples are one-dimensional observations from a stationary IID process
    - resampling uses replacement on the supplied observations and therefore ignores serial dependence

    Parameters:
    - `samples`: one-dimensional observations, typically day returns
    - `metric_fn`: function mapping a resampled array to a scalar metric
    - `n_resamples`: number of bootstrap resamples; must be positive
    - `ci`: confidence level in `(0.0, 1.0)`
    - `seed`: seed used with `np.random.default_rng(seed)` for deterministic output

    Return semantics:
    - returns `{"low": ..., "high": ..., "ci": ...}`
    - raises `ValueError` for empty samples, invalid dimensions, or invalid settings

    References:
    - Efron, B. and Tibshirani, R. "An Introduction to the Bootstrap"
    """
    sample_array = np.asarray(samples, dtype=float)
    if sample_array.ndim != 1:
        raise ValueError("samples must be one-dimensional")
    if sample_array.size == 0:
        raise ValueError("samples must not be empty")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be greater than zero")
    if not 0.0 < ci < 1.0:
        raise ValueError("ci must be between zero and one")

    alpha = (1.0 - ci) / 2.0
    metrics = np.empty(n_resamples, dtype=float)
    rng = np.random.default_rng(seed)

    for index in range(n_resamples):
        resample = rng.choice(sample_array, size=sample_array.size, replace=True)
        metrics[index] = float(metric_fn(resample))

    return {
        "low": float(np.quantile(metrics, alpha)),
        "high": float(np.quantile(metrics, 1.0 - alpha)),
        "ci": float(ci),
    }


def _expected_max_trial_sharpe(n_trials: int, var_of_trial_sharpes: float) -> float:
    if n_trials <= 1 or var_of_trial_sharpes == 0.0:
        return 0.0

    sigma = math.sqrt(var_of_trial_sharpes)
    first_quantile = _inverse_standard_normal_cdf(1.0 - (1.0 / n_trials))
    second_quantile = _inverse_standard_normal_cdf(1.0 - (1.0 / (n_trials * math.e)))
    return sigma * (((1.0 - EULER_GAMMA) * first_quantile) + (EULER_GAMMA * second_quantile))


def _standard_normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _inverse_standard_normal_cdf(probability: float) -> float:
    if probability <= 0.0 or probability >= 1.0:
        raise ValueError("probability must be between zero and one")

    if probability < _LOWER_TAIL_BREAK:
        q_value = math.sqrt(-2.0 * math.log(probability))
        return (
            (((((_ACKLAM_C[0] * q_value + _ACKLAM_C[1]) * q_value + _ACKLAM_C[2]) * q_value + _ACKLAM_C[3])
            * q_value + _ACKLAM_C[4]) * q_value + _ACKLAM_C[5])
            / ((((_ACKLAM_D[0] * q_value + _ACKLAM_D[1]) * q_value + _ACKLAM_D[2]) * q_value + _ACKLAM_D[3])
            * q_value + 1.0)
        )

    if probability > _UPPER_TAIL_BREAK:
        q_value = math.sqrt(-2.0 * math.log(1.0 - probability))
        return -(
            (((((_ACKLAM_C[0] * q_value + _ACKLAM_C[1]) * q_value + _ACKLAM_C[2]) * q_value + _ACKLAM_C[3])
            * q_value + _ACKLAM_C[4]) * q_value + _ACKLAM_C[5])
            / ((((_ACKLAM_D[0] * q_value + _ACKLAM_D[1]) * q_value + _ACKLAM_D[2]) * q_value + _ACKLAM_D[3])
            * q_value + 1.0)
        )

    q_value = probability - 0.5
    r_value = q_value * q_value
    return (
        (((((_ACKLAM_A[0] * r_value + _ACKLAM_A[1]) * r_value + _ACKLAM_A[2]) * r_value + _ACKLAM_A[3])
        * r_value + _ACKLAM_A[4]) * r_value + _ACKLAM_A[5]) * q_value
        / (((((_ACKLAM_B[0] * r_value + _ACKLAM_B[1]) * r_value + _ACKLAM_B[2]) * r_value + _ACKLAM_B[3])
        * r_value + _ACKLAM_B[4]) * r_value + 1.0)
    )
