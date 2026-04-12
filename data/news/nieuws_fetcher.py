"""Minimal news fetcher stub used for imports and test patching."""


class NieuwsFetcher:
    def __init__(self, config: dict):
        self.config = config

    async def update(self) -> None:
        return None
