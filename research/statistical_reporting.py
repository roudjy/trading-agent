"""Pure helpers for statistical defensibility sidecar assembly."""

import json
import math

import numpy as np

from research.registry import count_param_combinations, iter_strategy_families
from research.statistical_defensibility import (
    bootstrap_metric_ci,
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
)

BOOTSTRAP_CI = 0.95
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 1337
RANKING_METRIC = "sharpe"
DSR_REGIME_UNAVAILABLE = (
    "regime_count_not_supplied: canonical DSR requires explicit regime_count "
    "to be passed via research.evaluation.regime_count - no default applied"
)


def regime_count_settings(research_config: dict) -> tuple[int | None, str]:
    evaluation_config = research_config.get("evaluation") or {}
    regime_count = evaluation_config.get("regime_count")
    if regime_count is None:
        return None, "unsupplied"
    if not isinstance(regime_count, int) or regime_count <= 0:
        raise ValueError("research.evaluation.regime_count must be a positive integer when supplied explicitly")
    return regime_count, "explicit"


def build_statistical_defensibility_payload(
    evaluations: list[dict],
    as_of_utc,
    intervals: list[str],
    market_count: int,
    regime_count: int | None,
    regime_count_source: str,
) -> dict:
    family_accounts = _family_accounts(intervals, market_count, regime_count, regime_count_source)
    members_by_family = {key: [] for key in family_accounts}

    for evaluation in evaluations:
        report = evaluation["evaluation_report"]
        samples = report.get("evaluation_samples")
        if not isinstance(samples, dict):
            raise RuntimeError("evaluation_report.evaluation_samples is missing or malformed")
        daily_returns = samples.get("daily_returns")
        if not isinstance(daily_returns, list) or not daily_returns:
            raise RuntimeError("evaluation_report.evaluation_samples.daily_returns is missing or empty")

        sample_stats = (report.get("sample_statistics") or {}).get("daily_returns") or _sample_moments(daily_returns)
        n_obs = int(sample_stats["count"])
        skew = float(sample_stats["skew"])
        kurt = float(sample_stats["kurt"])
        interval = evaluation["interval"]
        bootstrap_ci = {
            "sharpe": bootstrap_metric_ci(
                daily_returns,
                lambda values, current_interval=interval: _sharpe_from_returns(values, current_interval),
                n_resamples=BOOTSTRAP_RESAMPLES,
                ci=BOOTSTRAP_CI,
                seed=BOOTSTRAP_SEED,
            ),
            "max_drawdown": bootstrap_metric_ci(
                daily_returns,
                _max_drawdown_from_returns,
                n_resamples=BOOTSTRAP_RESAMPLES,
                ci=BOOTSTRAP_CI,
                seed=BOOTSTRAP_SEED,
            ),
        }
        psr = probabilistic_sharpe_ratio(
            observed_sharpe=float(evaluation["row"]["sharpe"]),
            n_obs=n_obs,
            skew=skew,
            kurt=kurt,
        )
        family_key = (evaluation["family"], interval)
        variance_of_trial_sharpes = _variance_of_family_sharpes(evaluations, family_key)
        dsr_canonical, dsr_unavailable_reason = _canonical_dsr(
            observed_sharpe=float(evaluation["row"]["sharpe"]),
            n_obs=n_obs,
            skew=skew,
            kurt=kurt,
            regime_count=regime_count,
            trial_count_total=family_accounts[family_key]["trial_count_total"],
            var_of_trial_sharpes=variance_of_trial_sharpes,
        )
        members_by_family[family_key].append(
            {
                "strategy_name": evaluation["row"]["strategy_name"],
                "asset": evaluation["row"]["asset"],
                "selected_params": evaluation["selected_params"],
                "psr": psr,
                "psr_benchmark_sharpe": 0.0,
                "dsr_legacy_field_in_public_row": float(evaluation["row"]["deflated_sharpe"]),
                "dsr_canonical": dsr_canonical,
                "dsr_unavailable_reason": dsr_unavailable_reason,
                "bootstrap_seed": BOOTSTRAP_SEED,
                "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
                "bootstrap_ci": bootstrap_ci,
                "noise_warning": _noise_warning(psr, dsr_canonical, bootstrap_ci),
            }
        )

    families = []
    for key in sorted(family_accounts):
        family_payload = dict(family_accounts[key])
        family_payload["members"] = sorted(
            members_by_family[key],
            key=lambda member: (
                member["strategy_name"],
                member["asset"],
                json.dumps(member["selected_params"], sort_keys=True),
            ),
        )
        families.append(family_payload)

    return {
        "version": "v1",
        "generated_at_utc": as_of_utc.isoformat(),
        "ranking_metric": RANKING_METRIC,
        "experiment_family_scope": ["family", "interval"],
        "families": families,
    }


def _annualization_factor(interval: str) -> int:
    return {
        "1d": 252,
        "1h": 24 * 365,
        "4h": 6 * 365,
        "15m": 4 * 24 * 365,
        "5m": 12 * 24 * 365,
    }.get(interval, 252)


def _canonical_dsr(
    observed_sharpe: float,
    n_obs: int,
    skew: float,
    kurt: float,
    regime_count: int | None,
    trial_count_total: int,
    var_of_trial_sharpes: float,
) -> tuple[float | None, str | None]:
    if regime_count is None:
        return None, DSR_REGIME_UNAVAILABLE

    dsr_canonical = deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_obs=n_obs,
        skew=skew,
        kurt=kurt,
        n_trials=trial_count_total,
        var_of_trial_sharpes=var_of_trial_sharpes,
    )
    if dsr_canonical is None:
        return None, (
            "insufficient_daily_return_moments: canonical DSR could not be "
            "computed from the supplied daily return sample moments"
        )
    return dsr_canonical, None


def _family_accounts(intervals: list[str], market_count: int, regime_count: int | None, regime_count_source: str) -> dict:
    accounts = {}
    for family, strategies in iter_strategy_families():
        param_total = sum(count_param_combinations(strategy) for strategy in strategies)
        trial_count_total = param_total * market_count
        trial_formula = "param_combinations_total * market_count"
        if regime_count is not None:
            trial_count_total *= regime_count
            trial_formula = "param_combinations_total * market_count * regime_count"
        for interval in intervals:
            accounts[(family, interval)] = {
                "family": family,
                "interval": interval,
                "strategy_variant_count": len(strategies),
                "param_combinations_total": param_total,
                "market_count": market_count,
                "regime_count": regime_count,
                "regime_count_source": regime_count_source,
                "trial_count_total": trial_count_total,
                "trial_count_formula": trial_formula,
            }
    return accounts


def _max_drawdown_from_returns(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    equity = np.cumprod(1.0 + samples)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / np.where(peak > 0.0, peak, 1.0)
    return float(abs(drawdown.min())) if drawdown.size else 0.0


def _noise_warning(psr: float | None, dsr_canonical: float | None, bootstrap_ci: dict[str, dict[str, float]]) -> dict:
    criteria = {
        "psr_missing": psr is None,
        "psr_below_0_95": psr is not None and psr < 0.95,
        "dsr_canonical_below_0": dsr_canonical is not None and dsr_canonical < 0.0,
        "bootstrap_sharpe_ci_low_nonpositive": bootstrap_ci["sharpe"]["low"] <= 0.0,
    }
    fired = [name for name, passed in criteria.items() if passed]
    return {
        "is_likely_noise": bool(fired),
        "reason": ", ".join(fired) if fired else "no_noise_criteria_triggered",
        "criteria": criteria,
    }


def _sample_moments(samples: list[float]) -> dict[str, float]:
    array = np.asarray(samples, dtype=float)
    if array.size == 0:
        raise ValueError("daily_returns samples are required for statistical defensibility reporting")

    mean = float(array.mean())
    std = float(array.std())
    if std == 0.0:
        skew = 0.0
        kurt = 3.0
    else:
        centered = (array - mean) / std
        skew = float(np.mean(centered ** 3))
        kurt = float(np.mean(centered ** 4))
    return {"count": int(array.size), "mean": mean, "std": std, "skew": skew, "kurt": kurt}


def _sharpe_from_returns(samples: np.ndarray, interval: str) -> float:
    std = float(samples.std())
    if samples.size <= 1 or std == 0.0:
        return 0.0
    return float((samples.mean() / std) * math.sqrt(_annualization_factor(interval)))


def _variance_of_family_sharpes(evaluations: list[dict], family_key: tuple[str, str]) -> float:
    family_sharpes = [
        float(member["row"]["sharpe"])
        for member in evaluations
        if (member["family"], member["interval"]) == family_key
    ]
    return float(np.var(family_sharpes)) if family_sharpes else 0.0
