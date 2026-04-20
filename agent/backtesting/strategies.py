"""
STRATEGIE FUNCTIES voor backtesting.
Elke factory geeft een func(df) → pd.Series[int] terug.
Waarden: 1=long, -1=short, 0=geen positie.
Signaal wordt door engine.shift(1) gezet → geen lookahead bias.

Thin contract note (v3.5): Tier 1 baselines (SMA crossover,
zscore mean reversion, pairs zscore) are wrapped with
declare_thin and take (df, features). Their bodies read only
df.index and the features mapping - all indicator computation
flows through agent/backtesting/features.py primitives. Legacy
factories below still use func(df); migration is staged per the
v3.5 plan.
"""
import logging
from typing import Mapping, Optional

import numpy as np
import pandas as pd
import ta

from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin

log = logging.getLogger(__name__)


# ── RSI Mean Reversion ────────────────────────────────────────────────────────

def rsi_strategie(koop_drempel: float = 28, short_drempel: float = 72,
                  periode: int = 14):
    """RSI oversold/overbought mean reversion."""
    def func(df: pd.DataFrame) -> pd.Series:
        close = df['close'].astype(float)
        if len(close) < periode + 1:
            return pd.Series(0, index=df.index)
        rsi = ta.momentum.RSIIndicator(close, window=periode).rsi()
        sig = pd.Series(0, index=df.index)
        sig[rsi < koop_drempel]  = 1
        sig[rsi > short_drempel] = -1
        return sig
    return func


# ── Fear & Greed ──────────────────────────────────────────────────────────────

def fear_greed_strategie(fear_drempel: float = 25, greed_drempel: float = 75,
                         fng_df: Optional[pd.DataFrame] = None):
    """
    Koop bij extreme fear (laag getal), short bij extreme greed.
    fng_df: DataFrame met kolommen ['datum', 'waarde'] (van alternative.me).
    """
    def func(df: pd.DataFrame) -> pd.Series:
        sig = pd.Series(0, index=df.index)
        if fng_df is None or fng_df.empty:
            return sig
        # Align op datum
        # Normalize beide indexes naar UTC-naieve datum (geen tz-conflict)
        fng_idx = pd.DatetimeIndex(fng_df['datum']).normalize()
        if fng_idx.tz is not None:
            fng_idx = fng_idx.tz_convert('UTC').tz_localize(None)
        df_idx = df.index.normalize()
        if df_idx.tz is not None:
            df_idx = df_idx.tz_convert('UTC').tz_localize(None)
        fng_series = pd.Series(fng_df['waarde'].values, index=fng_idx)
        fng = fng_series.reindex(df_idx, method='ffill')
        fng.index = df.index  # herstel originele index
        sig[fng < fear_drempel]  = 1
        sig[fng > greed_drempel] = -1
        return sig
    return func


def laad_fear_greed(limit: int = 1000) -> Optional[pd.DataFrame]:
    """Haal Fear & Greed index op via alternative.me (gratis, geen key)."""
    import aiohttp, asyncio

    async def _fetch():
        import aiohttp
        try:
            async with aiohttp.ClientSession() as ses:
                async with ses.get(
                    f'https://api.alternative.me/fng/?limit={limit}&format=json',
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    data = await r.json()
            records = data.get('data', [])
            rows = []
            for rec in records:
                try:
                    rows.append({
                        'datum': pd.Timestamp(int(rec['timestamp']), unit='s'),
                        'waarde': int(rec['value'])
                    })
                except (KeyError, ValueError):
                    continue
            return pd.DataFrame(rows).sort_values('datum').reset_index(drop=True)
        except Exception as e:
            log.error(f"Fear&Greed ophalen mislukt: {e}")
            return pd.DataFrame()

    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


# ── Bollinger Breakout ────────────────────────────────────────────────────────

def bollinger_strategie(periode: int = 20, std: float = 2.0):
    """
    Mean reversion strategie:
    - long onder de onderband
    - short boven de bovenband
    - exit bij terugkeer naar de middenband
    """
    def func(df: pd.DataFrame) -> pd.Series:
        close = df['close'].astype(float)
        if len(close) < periode + 1:
            return pd.Series(0, index=df.index)

        bb = ta.volatility.BollingerBands(close, window=periode, window_dev=std)
        upper = bb.bollinger_hband()
        lower = bb.bollinger_lband()
        midden = bb.bollinger_mavg()

        sig = pd.Series(0, index=df.index)

        # Entries: mean reversion
        sig[close < lower] = 1
        sig[close > upper] = -1

        # Exit bij terugkeer richting middenband
        sig[(close >= midden) & (sig.shift(1) == 1)] = 0
        sig[(close <= midden) & (sig.shift(1) == -1)] = 0

        return sig

    return func

def bollinger_regime_strategie(config: dict,
                               periode: int = 20,
                               std: float = 2.0):
    """
    Bollinger mean reversion + regime filter:
    - Alleen traden in zijwaartse / hoge volatiliteit markten
    """

    regime_config = config["strategie"]["regime_detectie"]
    lookback = regime_config["lookback_periode"]

    def func(df: pd.DataFrame) -> pd.Series:
        close = df['close'].astype(float)
        regime_ok = (
            df["_mr_regime_ok"]
            if "_mr_regime_ok" in df.columns
            else pd.Series(False, index=df.index)
        )

        if len(close) < periode + 50:
            return pd.Series(0, index=df.index)

        bb = ta.volatility.BollingerBands(close, window=periode, window_dev=std)
        upper = bb.bollinger_hband()
        lower = bb.bollinger_lband()
        midden = bb.bollinger_mavg()

        sig = pd.Series(0, index=df.index)

        start_idx = max(periode + 1, lookback + 1)

        for i in range(start_idx, len(df)):
            if not bool(regime_ok.iloc[i]):
                continue

            prijs = close.iloc[i]

            # Mean reversion met bevestiging (reversal candle)
            if (
                prijs < lower.iloc[i]
                and close.iloc[i] > close.iloc[i - 1]
            ):
                sig.iloc[i] = 1

            elif (
                prijs > upper.iloc[i]
                and close.iloc[i] < close.iloc[i - 1]
            ):
                sig.iloc[i] = -1

            # Exit bij terugkeer naar middenband
            if sig.iloc[i - 1] == 1 and prijs >= midden.iloc[i]:
                sig.iloc[i] = 0
            elif sig.iloc[i - 1] == -1 and prijs <= midden.iloc[i]:
                sig.iloc[i] = 0

        return sig

    func._mr_regime_config = {
        "lookback_periode": lookback,
        "volatiliteit_drempel": regime_config["volatiliteit_drempel"],
    }
    return func

# ─ Trend Pullback Strategie ──────────────────$

def trend_pullback_strategie(ema_kort: int = 20,
                             ema_lang: int = 100,
                             pullback_buffer: float = 0.01,
                             slope_lookback: int = 5,
                             vol_lookback: int = 20,
                             max_volatility: float = 0.03):
    """
    Simpele trend pullback strategie:
    - alleen long
    - trend actief als EMA kort > EMA lang
    - extra filter: EMA lang moet stijgen
    - extra filter: volatiliteit mag niet te hoog zijn
    - entry als prijs terugvalt richting EMA kort
    - exit als trend breekt
    """

    def func(df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)

        min_bars = max(ema_kort, ema_lang, vol_lookback) + slope_lookback + 5
        if len(close) < min_bars:
            return pd.Series(0, index=df.index)

        ema_fast = close.ewm(span=ema_kort, adjust=False).mean()
        ema_slow = close.ewm(span=ema_lang, adjust=False).mean()
        ema_slope = ema_slow.diff(slope_lookback)

        returns = close.pct_change()
        rolling_vol = returns.rolling(vol_lookback).std()

        sig = pd.Series(0, index=df.index)

        trend_up = ema_fast > ema_slow
        trend_sterk = ema_slope > 0
        dichtbij_fast_ema = close <= (ema_fast * (1 + pullback_buffer))
        boven_slow = close > ema_slow
        vol_ok = rolling_vol <= max_volatility

        sig[trend_up & trend_sterk & dichtbij_fast_ema & boven_slow & vol_ok] = 1

        # exit wanneer trend breekt
        sig[ema_fast <= ema_slow] = 0

        return sig

    return func

#--- Trend Pullback TP SL Strategie ----$

def trend_pullback_tp_sl_strategie(ema_kort: int = 20,
                                   ema_lang: int = 100,
                                   pullback_buffer: float = 0.02,
                                   slope_lookback: int = 3,
                                   vol_lookback: int = 20,
                                   max_volatility: float = 0.03,
                                   take_profit: float = 0.04,
                                   stop_loss: float = 0.02):
    """
    Trend pullback variant met eenvoudige TP/SL-logica in het signaal.
    Alleen long.
    """

    def func(df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype(float)

        min_bars = max(ema_kort, ema_lang, vol_lookback) + slope_lookback + 5
        if len(close) < min_bars:
            return pd.Series(0, index=df.index)

        ema_fast = close.ewm(span=ema_kort, adjust=False).mean()
        ema_slow = close.ewm(span=ema_lang, adjust=False).mean()
        ema_slope = ema_slow.diff(slope_lookback)

        returns = close.pct_change()
        rolling_vol = returns.rolling(vol_lookback).std()

        sig = pd.Series(0, index=df.index)

        trend_up = ema_fast > ema_slow
        trend_sterk = ema_slope > 0
        dichtbij_fast_ema = close <= (ema_fast * (1 + pullback_buffer))
        boven_slow = close > ema_slow
        vol_ok = rolling_vol <= max_volatility

        sig[trend_up & trend_sterk & dichtbij_fast_ema & boven_slow & vol_ok] = 1

        return sig

    func._trend_pullback_tp_sl_config = {
        "ema_kort": ema_kort,
        "ema_lang": ema_lang,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
    }
    return func

#--- Breakout Momentum Strategie -----$

def breakout_momentum_strategie(lookback: int = 20,
                                ema_exit: int = 10):
    """
    Simpele breakout momentum strategie:
    - alleen long
    - entry als close boven hoogste high van vorige lookback-bars breekt
    - exit als close onder korte EMA zakt
    """

    def func(df: pd.DataFrame) -> pd.Series:
        if "close" not in df.columns or "high" not in df.columns:
            return pd.Series(0, index=df.index)

        close = df["close"].astype(float)
        high = df["high"].astype(float)

        min_bars = max(lookback, ema_exit) + 5
        if len(close) < min_bars:
            return pd.Series(0, index=df.index)

        hoogste_high = high.rolling(window=lookback).max().shift(1)
        ema_kort = close.ewm(span=ema_exit, adjust=False).mean()

        sig = pd.Series(0, index=df.index)

        breakout = close > hoogste_high
        trend_ok = close > ema_kort

        sig[breakout & trend_ok] = 1
        sig[close < ema_kort] = 0

        return sig

    return func

# ── Earnings Drift ────────────────────────────────────────────────────────────

def earnings_strategie(pct_drempel: float = 0.05, positie_duur: int = 5):
    """
    Post-earnings drift: koop dag NA een sterke earnings-dag (+5%),
    exit na positie_duur handelsdagen.
    """
    def func(df: pd.DataFrame) -> pd.Series:
        close = df['close'].astype(float)
        dagret = close.pct_change()
        # Earnings-dag proxy: dagreturn >= drempel (shift 1 = gisteren was earnings)
        sig = pd.Series(0, index=df.index)
        triggered = dagret.shift(1) >= pct_drempel

        i = 0
        idx = list(df.index)
        while i < len(idx):
            if triggered.iloc[i]:
                # Houd positie voor positie_duur dagen
                for j in range(i, min(i + positie_duur, len(idx))):
                    sig.iloc[j] = 1
                i += positie_duur
            else:
                i += 1
        return sig
    return func


# ── Opening Range Breakout (dagdata proxy) ────────────────────────────────────

def orb_strategie(gap_drempel: float = 0.005, positie_duur: int = 1):
    """
    ORB-proxy met dagdata: long als open > vorige dag's high * (1+gap).
    Positie gesloten aan einde dag (positie_duur=1 dag).
    Alleen geldig voor aandelen (15:30-16:00 range approximatie).
    """
    def func(df: pd.DataFrame) -> pd.Series:
        if 'open' not in df.columns or 'high' not in df.columns:
            return pd.Series(0, index=df.index)
        open_prijs  = df['open'].astype(float)
        vorige_high = df['high'].astype(float).shift(1)
        vorige_low  = df['low'].astype(float).shift(1)

        sig = pd.Series(0, index=df.index)
        sig[open_prijs > vorige_high * (1 + gap_drempel)]  = 1
        sig[open_prijs < vorige_low  * (1 - gap_drempel)] = -1
        return sig
    return func


# ── Polymarket Expiry ─────────────────────────────────────────────────────────

def polymarket_expiry_strategie():
    """
    Polymarket high-certainty expiry: geen historische data beschikbaar.
    Altijd lege signalen — backtest niet uitvoerbaar.
    """
    def func(df: pd.DataFrame) -> pd.Series:
        return pd.Series(0, index=df.index)
    return func


# ── SMA Crossover (Trend Following) ───────────────────────────────────────

def sma_crossover_strategie(fast_window: int = 20, slow_window: int = 50):
    """
    Classical SMA crossover trend-following strategy.
    Long when fast SMA > slow SMA, flat otherwise.
    Long-only per tier 1 baseline (orchestrator_brief §4.1).

    Thin contract v1.0: body reads only df.index and features.
    """
    def func(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        sma_fast = features["sma_fast"]
        sma_slow = features["sma_slow"]
        min_bars = max(fast_window, slow_window) + 1
        sig = pd.Series(0, index=df.index)
        if len(df.index) < min_bars or fast_window >= slow_window:
            return sig
        sig[sma_fast > sma_slow] = 1
        return sig

    return declare_thin(
        func,
        feature_requirements=[
            FeatureRequirement(name="sma", params={"window": fast_window}, alias="sma_fast"),
            FeatureRequirement(name="sma", params={"window": slow_window}, alias="sma_slow"),
        ],
    )


# ── Z-Score Mean Reversion ────────────────────────────────────────────────

def zscore_mean_reversion_strategie(lookback: int = 20,
                                    entry_z: float = 2.0,
                                    exit_z: float = 0.5):
    """
    Classical price z-score mean reversion (orchestrator_brief §4.2).
    Long when z <= -entry_z, short when z >= +entry_z,
    flat when |z| <= exit_z (flatten-on-threshold exit).

    Thin contract v1.0: body reads only df.index and features.
    """
    def func(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        sig = pd.Series(0, index=df.index)
        if len(df.index) < lookback + 1 or entry_z <= exit_z:
            return sig
        z = features["z"]
        sig[z <= -entry_z] = 1
        sig[z >= entry_z] = -1
        sig[z.abs() <= exit_z] = 0
        return sig

    return declare_thin(
        func,
        feature_requirements=[
            FeatureRequirement(name="zscore", params={"lookback": lookback}, alias="z"),
        ],
    )


# ── Pairs Trading Z-Score (Statistical Arbitrage) ─────────────────────────

def pairs_zscore_strategie(lookback: int = 30,
                           entry_z: float = 2.0,
                           exit_z: float = 0.5,
                           hedge_ratio: float = 1.0):
    """
    Pairs trading z-score strategy (orchestrator_brief §4.3).
    Requires a DataFrame with BOTH 'close' and 'close_ref' columns.
    Spread = close - hedge_ratio * close_ref.
    Long pair when spread z <= -entry_z (long close, short close_ref).
    Short pair when spread z >= +entry_z (short close, long close_ref).
    Flat when |z| <= exit_z.

    Thin contract v1.0 (scaffolded; pairs remains enabled=False in
    v3.5 per registry). Body reads only df.index + features. The
    multi-asset loader that populates 'close_ref' lands in v3.6+.
    """
    def func(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series:
        sig = pd.Series(0, index=df.index)
        if len(df.index) < lookback + 1 or entry_z <= exit_z:
            return sig
        if "z" not in features:
            return sig
        z = features["z"]
        sig[z <= -entry_z] = 1
        sig[z >= entry_z] = -1
        sig[z.abs() <= exit_z] = 0
        return sig

    return declare_thin(
        func,
        feature_requirements=[
            FeatureRequirement(
                name="spread_zscore",
                params={"hedge_ratio": hedge_ratio, "lookback": lookback},
                alias="z",
            ),
        ],
    )
