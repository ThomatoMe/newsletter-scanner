"""Fetcher pro Reddit RSS feedy."""

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from src.fetchers.base import BaseFetcher, FetchedItem

# Šablona URL pro Reddit RSS
_RSS_URL = "https://www.reddit.com/r/{subreddit}/{sort}/.rss?t={time_filter}&limit={limit}"

# User-Agent pro Reddit (vyžadují neprázdný)
_USER_AGENT = "LinkedInTopicScanner/0.1"


class RedditFetcher(BaseFetcher):
    """Stahuje příspěvky z Reddit RSS feedů."""

    @property
    def source_name(self) -> str:
        return "reddit"

    def fetch(self) -> list[FetchedItem]:
        subreddits: list[str] = self.config.get("subreddits", [])
        sort = self.config.get("sort", "top")
        time_filter = self.config.get("time_filter", "week")
        limit = self.config.get("limit", 50)

        if not subreddits:
            self.logger.warning("Žádné subreddity nakonfigurovány")
            return []

        items: list[FetchedItem] = []
        seen_urls: set[str] = set()

        for subreddit in subreddits:
            self._rate_limit()
            url = _RSS_URL.format(
                subreddit=subreddit,
                sort=sort,
                time_filter=time_filter,
                limit=limit,
            )
            self.logger.debug("Stahuji Reddit RSS: r/%s", subreddit)

            try:
                feed = feedparser.parse(url, agent=_USER_AGENT)
            except Exception as e:
                self.logger.error("Chyba při stahování r/%s: %s", subreddit, e)
                continue

            for entry in feed.entries:
                link = getattr(entry, "link", "")
                if link in seen_urls:
                    continue
                seen_urls.add(link)

                # Parsování data
                published = None
                if hasattr(entry, "published"):
                    try:
                        published = parsedate_to_datetime(entry.published)
                    except Exception:
                        pass

                # Popis (Reddit RSS dává HTML content)
                description = getattr(entry, "summary", "")

                items.append(
                    FetchedItem(
                        title=getattr(entry, "title", ""),
                        description=description,
                        url=link,
                        source=self.source_name,
                        source_detail=f"r/{subreddit}",
                        published=published,
                    )
                )

        self.logger.info("Reddit: staženo %d položek z %d subredditů", len(items), len(subreddits))
        return items
