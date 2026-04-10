"""Pure execution-layer types and broker interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, Optional, Protocol, runtime_checkable

from automation import live_gate


class LiveGateClosedError(RuntimeError):
    """Raised when live execution is requested while the live gate is closed."""


@dataclass
class OrderIntent:
    instrument_id: str
    side: Literal["buy", "sell"]
    size: float
    limit_price: Optional[float]
    venue: str
    client_tag: Optional[str]

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if not self.venue.strip():
            raise ValueError("venue must not be empty")
        if self.size <= 0:
            raise ValueError("size must be positive")


@dataclass(frozen=True)
class Fill:
    instrument_id: str
    side: Literal["buy", "sell"]
    size: float
    intended_price: float
    fill_price: float
    slippage_bps: float
    fee_ccy: str
    fee_amount: float
    timestamp_utc: datetime
    venue: str


@runtime_checkable
class BrokerProtocol(Protocol):
    name: str

    def place_paper_order(self, intent: OrderIntent, market_snapshot: Mapping) -> Fill:
        ...

    def place_live_order(self, intent: OrderIntent, market_snapshot: Mapping) -> Fill:
        ...


class PaperBrokerBase(ABC):
    """Thin base class for paper brokers with shared live-gate enforcement."""

    name: str

    @abstractmethod
    def place_paper_order(self, intent: OrderIntent, market_snapshot: Mapping) -> Fill:
        """Place a paper order against a supplied market snapshot."""

    def place_live_order(self, intent: OrderIntent, market_snapshot: Mapping) -> Fill:
        if not live_gate.is_live_armed():
            raise LiveGateClosedError(f"Live trading is not armed for venue={intent.venue}")
        raise NotImplementedError("Live broker implementations are out of scope for Phase 3")
