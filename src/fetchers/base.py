"""Abstraktní bázová třída pro všechny fetchery a jednotný datový model."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import time
import logging


@dataclass
class FetchedItem:
    """Jednotný formát pro položku z libovolného zdroje."""

    title: str
    description: str = ""
    url: str = ""
    source: str = ""            # Název zdroje (google_news, reddit, ...)
    source_detail: str = ""     # Subreddit, newsletter název, atd.
    published: Optional[datetime] = None
    score: int = 0              # Upvotes, points
    tags: list[str] = field(default_factory=list)


class BaseFetcher(ABC):
    """Bázová třída – každý fetcher musí implementovat fetch() a source_name."""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rate_limit_seconds: float = config.get("rate_limit", 2.0)
        self._last_request_time: float = 0.0

    def _rate_limit(self) -> None:
        """Jednoduchý rate limiter – čeká mezi requesty."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_time = time.time()

    @abstractmethod
    def fetch(self) -> list[FetchedItem]:
        """Stáhne data ze zdroje. Vrací seznam FetchedItem."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unikátní název zdroje (např. 'google_news')."""
        ...
