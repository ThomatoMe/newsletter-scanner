"""Fetcher pro Google News RSS."""

from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser

from src.fetchers.base import BaseFetcher, FetchedItem

# Šablona URL pro Google News RSS vyhledávání
_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"


class GoogleNewsFetcher(BaseFetcher):
    """Stahuje články z Google News RSS na základě vyhledávacích dotazů."""

    @property
    def source_name(self) -> str:
        return "google_news"

    def fetch(self) -> list[FetchedItem]:
        queries: list[str] = self.config.get("queries", [])
        if not queries:
            self.logger.warning("Žádné vyhledávací dotazy nakonfigurovány")
            return []

        seen_urls: set[str] = set()
        items: list[FetchedItem] = []

        for query in queries:
            self._rate_limit()
            url = _RSS_URL.format(query=quote_plus(query))
            self.logger.debug("Stahuji Google News RSS: %s", query)

            try:
                feed = feedparser.parse(url)
            except Exception as e:
                self.logger.error("Chyba při parsování RSS pro '%s': %s", query, e)
                continue

            for entry in feed.entries:
                link = getattr(entry, "link", "")
                if link in seen_urls:
                    continue
                seen_urls.add(link)

                # Parsování data publikace
                published = None
                if hasattr(entry, "published"):
                    try:
                        published = parsedate_to_datetime(entry.published)
                    except Exception:
                        pass

                items.append(
                    FetchedItem(
                        title=getattr(entry, "title", ""),
                        description=getattr(entry, "summary", ""),
                        url=link,
                        source=self.source_name,
                        source_detail=query,
                        published=published,
                    )
                )

        self.logger.info("Google News: staženo %d položek z %d dotazů", len(items), len(queries))
        return items
