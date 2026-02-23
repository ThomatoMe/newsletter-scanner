"""Fetcher pro HackerNews API (Firebase)."""

from datetime import datetime, timezone

import requests

from src.fetchers.base import BaseFetcher, FetchedItem

_BASE_URL = "https://hacker-news.firebaseio.com/v0"
_TOP_STORIES_URL = f"{_BASE_URL}/topstories.json"
_ITEM_URL = f"{_BASE_URL}/item/{{id}}.json"
_TIMEOUT = 10


class HackerNewsFetcher(BaseFetcher):
    """Stahuje top stories z HackerNews a filtruje dle relevance."""

    @property
    def source_name(self) -> str:
        return "hackernews"

    def _is_relevant(self, title: str, keywords: list[str]) -> bool:
        """Kontroluje, zda titulek obsahuje alespoň jedno klíčové slovo."""
        title_lower = title.lower()
        return any(kw.lower() in title_lower for kw in keywords)

    def fetch(self) -> list[FetchedItem]:
        max_stories: int = self.config.get("max_stories", 200)
        keywords: list[str] = self.config.get("relevance_keywords", [])

        # Stažení seznamu top story IDs
        try:
            resp = requests.get(_TOP_STORIES_URL, timeout=_TIMEOUT)
            resp.raise_for_status()
            story_ids: list[int] = resp.json()[:max_stories]
        except Exception as e:
            self.logger.error("Chyba při stahování HN top stories: %s", e)
            return []

        items: list[FetchedItem] = []

        for story_id in story_ids:
            self._rate_limit()

            try:
                resp = requests.get(
                    _ITEM_URL.format(id=story_id), timeout=_TIMEOUT
                )
                resp.raise_for_status()
                story = resp.json()
            except Exception as e:
                self.logger.debug("Chyba při stahování HN story %d: %s", story_id, e)
                continue

            if not story or story.get("type") != "story":
                continue

            title = story.get("title", "")

            # Filtrování dle relevance (pokud jsou klíčová slova nastavena)
            if keywords and not self._is_relevant(title, keywords):
                continue

            # Převod Unix timestamp na datetime
            published = None
            if "time" in story:
                published = datetime.fromtimestamp(story["time"], tz=timezone.utc)

            items.append(
                FetchedItem(
                    title=title,
                    description="",
                    url=story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                    source=self.source_name,
                    source_detail="hackernews",
                    published=published,
                    score=story.get("score", 0),
                )
            )

        self.logger.info("HackerNews: staženo %d relevantních položek z %d stories", len(items), len(story_ids))
        return items
