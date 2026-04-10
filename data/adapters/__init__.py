"""Adapter protocols and implementations for the canonical data layer."""

from data.adapters.base import MacroAdapter, MarketAdapter
from data.adapters.yfinance_adapter import YFinanceMarketAdapter

__all__ = ["MacroAdapter", "MarketAdapter", "YFinanceMarketAdapter"]
