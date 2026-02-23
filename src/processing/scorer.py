"""Multi-faktorový scoring trendů."""

import logging
import math
from datetime import datetime, timezone

from src.fetchers.base import FetchedItem

logger = logging.getLogger(__name__)


class TrendScorer:
    """Vypočítá trend score pro klíčová slova na základě více faktorů."""

    def __init__(self, config: dict):
        weights = config.get("weights", {})
        self.w_frequency = weights.get("frequency", 0.30)
        self.w_recency = weights.get("recency", 0.30)
        self.w_diversity = weights.get("source_diversity", 0.25)
        self.w_engagement = weights.get("engagement", 0.15)
        self.decay_hours = config.get("recency_decay_hours", 48)

    def score(
        self,
        keyword: str,
        matching_items: list[FetchedItem],
        total_items: int,
        all_sources: set[str],
    ) -> dict:
        """Vypočítá trend score pro klíčové slovo.

        Args:
            keyword: Klíčové slovo
            matching_items: Položky obsahující toto klíčové slovo
            total_items: Celkový počet položek (pro normalizaci frekvence)
            all_sources: Množina všech zdrojů v datasetu

        Returns:
            Slovník s detailním scoringem
        """
        if not matching_items:
            return {
                "keyword": keyword,
                "trend_score": 0.0,
                "frequency_score": 0.0,
                "recency_score": 0.0,
                "source_diversity_score": 0.0,
                "engagement_score": 0.0,
                "mention_count": 0,
                "sources": [],
                "latest_date": None,
            }

        now = datetime.now(tz=timezone.utc)

        # Frequency score: poměr zmínek vůči celku
        mention_count = len(matching_items)
        frequency_score = min(mention_count / max(total_items, 1), 1.0)

        # Recency score: exponenciální rozpad podle stáří nejnovější položky
        recency_score = 0.0
        latest_date = None
        for item in matching_items:
            if item.published:
                if latest_date is None or item.published > latest_date:
                    latest_date = item.published

        if latest_date:
            # Zajistit timezone-aware porovnání
            if latest_date.tzinfo is None:
                latest_date = latest_date.replace(tzinfo=timezone.utc)
            age_hours = (now - latest_date).total_seconds() / 3600
            recency_score = math.exp(-age_hours / max(self.decay_hours, 1))

        # Source diversity score: kolik různých zdrojů zmiňuje keyword
        unique_sources = {item.source for item in matching_items}
        source_diversity_score = len(unique_sources) / max(len(all_sources), 1)

        # Engagement score: normalizovaný součet score/upvotes
        total_engagement = sum(item.score for item in matching_items if item.score > 0)
        # Normalizace – log scale pro velké hodnoty
        engagement_score = min(math.log1p(total_engagement) / 10.0, 1.0)

        # Vážený celkový score
        trend_score = (
            self.w_frequency * frequency_score
            + self.w_recency * recency_score
            + self.w_diversity * source_diversity_score
            + self.w_engagement * engagement_score
        )

        return {
            "keyword": keyword,
            "trend_score": round(trend_score, 4),
            "frequency_score": round(frequency_score, 4),
            "recency_score": round(recency_score, 4),
            "source_diversity_score": round(source_diversity_score, 4),
            "engagement_score": round(engagement_score, 4),
            "mention_count": mention_count,
            "sources": sorted(unique_sources),
            "latest_date": latest_date.isoformat() if latest_date else None,
        }

    def score_batch(
        self,
        keywords_data: list[dict],
        items: list[FetchedItem],
        all_sources: set[str],
    ) -> list[dict]:
        """Spočítá score pro seznam klíčových slov najednou.

        Args:
            keywords_data: Seznam z extractoru [{"keyword": str, "source_items": list[int], ...}]
            items: Původní FetchedItem seznam
            all_sources: Množina všech zdrojů

        Returns:
            Obohacená keywords_data se scoring poli
        """
        total_items = len(items)

        for kw_data in keywords_data:
            # Sesbírat matching items
            matching = [
                items[idx]
                for idx in kw_data.get("source_items", [])
                if idx < len(items)
            ]

            score_result = self.score(
                kw_data["keyword"], matching, total_items, all_sources
            )

            # Přidat scoring pole do kw_data
            for key in [
                "trend_score",
                "frequency_score",
                "recency_score",
                "source_diversity_score",
                "engagement_score",
                "mention_count",
                "sources",
                "latest_date",
            ]:
                kw_data[key] = score_result[key]

        # Seřazení podle trend_score
        keywords_data.sort(key=lambda x: x.get("trend_score", 0), reverse=True)

        logger.info("Scoring dokončen pro %d klíčových slov", len(keywords_data))
        return keywords_data
