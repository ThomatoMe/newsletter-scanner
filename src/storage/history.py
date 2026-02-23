"""Historické sledování trendů a porovnání mezi běhy."""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class HistoryTracker:
    """Správa historie běhů pro sledování vývoje trendů."""

    def __init__(self, data_dir: Path):
        self.history_file = Path(data_dir) / "history.json"
        self.history: list[dict] = self._load()

    def _load(self) -> list[dict]:
        """Načte historii z JSON souboru."""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Chyba při načítání historie: %s", e)
            return []

    def save(self) -> None:
        """Uloží historii do JSON souboru."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

        logger.info("Historie uložena: %d záznamů", len(self.history))

    def add_run(self, topics: list[dict]) -> None:
        """Přidá záznam o běhu do historie."""
        run_date = date.today().isoformat()

        # Agregace kategorií
        category_counts: dict[str, int] = {}
        for topic in topics:
            for cat in topic.get("categories", []):
                cat_name = cat.get("category", "other")
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

        # Top 10 topiků (keyword + score)
        top_topics = [
            {
                "keyword": t.get("keyword", ""),
                "trend_score": t.get("trend_score", 0),
                "mention_count": t.get("mention_count", 0),
            }
            for t in topics[:10]
        ]

        run_record = {
            "date": run_date,
            "topic_count": len(topics),
            "top_topics": top_topics,
            "categories": category_counts,
        }

        self.history.append(run_record)
        self.save()

        logger.info("Přidán záznam o běhu: %s (%d topiků)", run_date, len(topics))

    def get_trending(self, days: int = 7) -> list[dict]:
        """Vrací topiky s rostoucím trendem za posledních N dní.

        Porovnává frekvenci klíčových slov mezi staršími a novějšími běhy.
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        recent_runs = [r for r in self.history if r["date"] >= cutoff]

        if len(recent_runs) < 2:
            return []

        # Rozdělení na starší a novější polovinu
        mid = len(recent_runs) // 2
        older = recent_runs[:mid]
        newer = recent_runs[mid:]

        # Agregace keyword scores
        def _aggregate_keywords(runs: list[dict]) -> dict[str, float]:
            scores: dict[str, list[float]] = {}
            for run in runs:
                for topic in run.get("top_topics", []):
                    kw = topic.get("keyword", "")
                    scores.setdefault(kw, []).append(topic.get("trend_score", 0))
            return {kw: sum(s) / len(s) for kw, s in scores.items()}

        older_scores = _aggregate_keywords(older)
        newer_scores = _aggregate_keywords(newer)

        # Najít rostoucí trendy
        trending = []
        for kw, new_score in newer_scores.items():
            old_score = older_scores.get(kw, 0)
            if new_score > old_score:
                trending.append(
                    {
                        "keyword": kw,
                        "current_score": new_score,
                        "previous_score": old_score,
                        "change": new_score - old_score,
                        "direction": "rising",
                    }
                )

        trending.sort(key=lambda x: x["change"], reverse=True)
        return trending

    def get_new_topics(self, days: int = 7) -> list[dict]:
        """Vrací topiky, které se poprvé objevily v posledních N dnech."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        recent_runs = [r for r in self.history if r["date"] >= cutoff]
        older_runs = [r for r in self.history if r["date"] < cutoff]

        # Klíčová slova z minulosti
        old_keywords: set[str] = set()
        for run in older_runs:
            for topic in run.get("top_topics", []):
                old_keywords.add(topic.get("keyword", ""))

        # Nová klíčová slova
        new_topics = []
        seen: set[str] = set()
        for run in recent_runs:
            for topic in run.get("top_topics", []):
                kw = topic.get("keyword", "")
                if kw not in old_keywords and kw not in seen:
                    seen.add(kw)
                    new_topics.append(
                        {
                            "keyword": kw,
                            "first_seen": run["date"],
                            "trend_score": topic.get("trend_score", 0),
                        }
                    )

        return new_topics

    def get_runs_count(self) -> int:
        """Vrátí počet záznamů v historii."""
        return len(self.history)
