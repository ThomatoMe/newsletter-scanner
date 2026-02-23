"""JSON/CSV persistence pro surová data, zpracované topiky a reporty."""

import csv
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DataStore:
    """Ukládání a načítání dat v JSON/CSV formátu."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.reports_dir = self.data_dir / "reports"

        # Zajistit, že adresáře existují
        for d in [self.raw_dir, self.processed_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _today(self) -> str:
        """Vrátí dnešní datum jako string YYYY-MM-DD."""
        return date.today().isoformat()

    def _json_serializer(self, obj: Any) -> Any:
        """Serializátor pro JSON (datetime apod.)."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Typ {type(obj)} není serializovatelný")

    def save_raw(self, items: list[dict], source: str) -> Path:
        """Uloží surová data jako JSON. Soubor: {date}_{source}.json"""
        filename = f"{self._today()}_{source}.json"
        filepath = self.raw_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2, default=self._json_serializer)

        logger.info("Surová data uložena: %s (%d položek)", filepath, len(items))
        return filepath

    def save_processed(self, topics: list[dict]) -> Path:
        """Uloží zpracované topiky jako JSON. Soubor: {date}_topics.json"""
        filename = f"{self._today()}_topics.json"
        filepath = self.processed_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(topics, f, ensure_ascii=False, indent=2, default=self._json_serializer)

        logger.info("Zpracované topiky uloženy: %s (%d topiků)", filepath, len(topics))
        return filepath

    def save_report_json(self, report: dict) -> Path:
        """Uloží report jako JSON."""
        filename = f"{self._today()}_report.json"
        filepath = self.reports_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=self._json_serializer)

        logger.info("JSON report uložen: %s", filepath)
        return filepath

    def save_report_csv(self, topics: list[dict]) -> Path:
        """Uloží report jako CSV."""
        filename = f"{self._today()}_report.csv"
        filepath = self.reports_dir / filename

        headers = [
            "keyword",
            "category",
            "trend_score",
            "frequency_score",
            "recency_score",
            "mention_count",
            "sources",
            "latest_date",
        ]

        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()

            for topic in topics:
                # Zploštění kategorií
                categories = topic.get("categories", [])
                category_str = ", ".join(
                    c.get("display_name", c.get("category", ""))
                    for c in categories
                    if isinstance(c, dict)
                )

                sources = topic.get("sources", [])
                sources_str = ", ".join(sources) if isinstance(sources, list) else str(sources)

                row = {
                    "keyword": topic.get("keyword", ""),
                    "category": category_str,
                    "trend_score": topic.get("trend_score", 0),
                    "frequency_score": topic.get("frequency_score", 0),
                    "recency_score": topic.get("recency_score", 0),
                    "mention_count": topic.get("mention_count", 0),
                    "sources": sources_str,
                    "latest_date": topic.get("latest_date", ""),
                }
                writer.writerow(row)

        logger.info("CSV report uložen: %s (%d řádků)", filepath, len(topics))
        return filepath

    def load_latest_processed(self) -> Optional[list[dict]]:
        """Načte poslední zpracovaná data (podle datumu v názvu souboru)."""
        files = sorted(self.processed_dir.glob("*_topics.json"), reverse=True)

        if not files:
            logger.warning("Žádná zpracovaná data nenalezena v %s", self.processed_dir)
            return None

        filepath = files[0]
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info("Načtena zpracovaná data: %s (%d topiků)", filepath, len(data))
        return data
