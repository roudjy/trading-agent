"""Minimal market data fetcher stub used for imports and test patching."""


class MarketDataFetcher:
    def __init__(self, config: dict):
        self.config = config

    async def haal_alles_op(self) -> dict:
        return {}
