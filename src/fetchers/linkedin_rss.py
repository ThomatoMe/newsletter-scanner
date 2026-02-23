"""Fetcher pro LinkedIn Newsletter RSS (experimentální)."""

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from src.fetchers.base import BaseFetcher, FetchedItem


class LinkedInRSSFetcher(BaseFetcher):
    """Stahuje LinkedIn newsletter RSS feedy. Experimentální – disabled by default."""

    @property
    def source_name(self) -> str:
        return "linkedin_rss"

    def fetch(self) -> list[FetchedItem]:
        urls: list[str] = self.config.get("newsletter_urls", [])

        if not urls:
            self.logger.debug("Žádné LinkedIn newsletter URLs nakonfigurovány – přeskakuji")
            return []

        items: list[FetchedItem] = []
        seen_urls: set[str] = set()

        for feed_url in urls:
            self._rate_limit()
            self.logger.debug("Stahuji LinkedIn RSS: %s", feed_url)

            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                self.logger.error("Chyba při parsování LinkedIn RSS %s: %s", feed_url, e)
                continue

            feed_title = getattr(feed.feed, "title", feed_url)

            for entry in feed.entries:
                link = getattr(entry, "link", "")
                if link in seen_urls:
                    continue
                seen_urls.add(link)

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
                        source_detail=feed_title,
                        published=published,
                    )
                )

        self.logger.info("LinkedIn RSS: staženo %d položek z %d feedů", len(items), len(urls))
        return items
