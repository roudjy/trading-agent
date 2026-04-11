"""Minimal bot detector stub used for imports and test patching."""


class BotPatroon:
    """Stub representation of an identified bot pattern."""

    def __init__(self, naam: str = "", kenmerken: dict | None = None):
        self.naam = naam
        self.kenmerken = kenmerken or {}


class BotDetector:
    def __init__(self, config: dict):
        self.config = config
        self.herkende_patronen = {}

    async def scan(self) -> dict:
        return self.herkende_patronen
