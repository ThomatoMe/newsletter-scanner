"""Fetcher pro Google Trends (pytrends). Celý modul je zabalený v try/except."""

from datetime import datetime, timezone

from src.fetchers.base import BaseFetcher, FetchedItem

# Pytrends je nestabilní – importujeme s fallbackem
try:
    from pytrends.request import TrendReq

    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False


class GoogleTrendsFetcher(BaseFetcher):
    """Stahuje trending data z Google Trends. Pokud pytrends selže, vrací prázdný seznam."""

    @property
    def source_name(self) -> str:
        return "google_trends"

    def fetch(self) -> list[FetchedItem]:
        if not PYTRENDS_AVAILABLE:
            self.logger.warning("pytrends není nainstalován – přeskakuji Google Trends")
            return []

        geo: str = self.config.get("geo", "US")
        keyword_groups: list[list[str]] = self.config.get("keyword_groups", [])

        items: list[FetchedItem] = []
        now = datetime.now(tz=timezone.utc)

        # Trending vyhledávání
        try:
            self._rate_limit()
            pytrends = TrendReq(hl="en-US", tz=360)
            trending_df = pytrends.trending_searches(pn="united_states")

            for _, row in trending_df.iterrows():
                keyword = str(row.iloc[0])
                items.append(
                    FetchedItem(
                        title=keyword,
                        description=f"Trending search: {keyword}",
                        source=self.source_name,
                        source_detail="trending_searches",
                        published=now,
                    )
                )
        except Exception as e:
            self.logger.warning("Google Trends trending_searches selhalo: %s", e)

        # Related queries pro každou skupinu klíčových slov
        for group in keyword_groups:
            try:
                self._rate_limit()
                pytrends = TrendReq(hl="en-US", tz=360)
                pytrends.build_payload(group, timeframe="now 7-d", geo=geo)

                related = pytrends.related_queries()
                for kw, data in related.items():
                    if data is None:
                        continue

                    # Top related queries
                    top_df = data.get("top")
                    if top_df is not None and not top_df.empty:
                        for _, row in top_df.head(10).iterrows():
                            query_text = str(row.get("query", ""))
                            value = int(row.get("value", 0))
                            items.append(
                                FetchedItem(
                                    title=query_text,
                                    description=f"Related to: {kw}",
                                    source=self.source_name,
                                    source_detail=f"related_top:{kw}",
                                    published=now,
                                    score=value,
                                )
                            )

                    # Rising related queries
                    rising_df = data.get("rising")
                    if rising_df is not None and not rising_df.empty:
                        for _, row in rising_df.head(10).iterrows():
                            query_text = str(row.get("query", ""))
                            value = int(row.get("value", 0))
                            items.append(
                                FetchedItem(
                                    title=query_text,
                                    description=f"Rising related to: {kw}",
                                    source=self.source_name,
                                    source_detail=f"related_rising:{kw}",
                                    published=now,
                                    score=value,
                                    tags=["rising"],
                                )
                            )
            except Exception as e:
                self.logger.warning("Google Trends related_queries pro %s selhalo: %s", group, e)

        self.logger.info("Google Trends: získáno %d položek", len(items))
        return items
