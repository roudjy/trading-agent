"""
STRATEGIE FUNCTIES voor backtesting.
Elke factory geeft een func(df) → pd.Series[int] terug.
Waarden: 1=long, -1=short, 0=geen positie.
Signaal wordt door engine.shift(1) gezet → geen lookahead bias.
"""
import logging
from typing import Optional
from agent.brain.regime_detector import RegimeDetector, Regime

import numpy as np
import pandas as pd
import ta

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

    detector = RegimeDetector(config)

    def func(df: pd.DataFrame) -> pd.Series:
        close = df['close'].astype(float)

        if len(close) < periode + 50:
            return pd.Series(0, index=df.index)

        bb = ta.volatility.BollingerBands(close, window=periode, window_dev=std)
        upper = bb.bollinger_hband()
        lower = bb.bollinger_lband()
        midden = bb.bollinger_mavg()

        sig = pd.Series(0, index=df.index)
        prijzen = close.values

        lookback = detector.lookback
        start_idx = max(periode + 1, lookback + 1)

        for i in range(start_idx, len(df)):
            window = prijzen[i - (lookback + 1):i]

            regime_result = detector._analyseer(
                symbool="tmp",
                prijzen=window,
                data={}
            )

            regime = regime_result.regime

            if regime not in [Regime.ZIJWAARTS, Regime.HOGE_VOLATILITEIT]:
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
