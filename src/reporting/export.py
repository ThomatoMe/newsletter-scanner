"""JSON a CSV export reportů."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.storage.store import DataStore

logger = logging.getLogger(__name__)


class ReportExporter:
    """Exportuje reporty do JSON a CSV."""

    def __init__(self, store: DataStore):
        self.store = store

    def export_json(self, report: dict) -> Path:
        """Exportuje kompletní report jako JSON."""
        return self.store.save_report_json(report)

    def export_csv(self, topics: list[dict]) -> Path:
        """Exportuje topiky jako CSV."""
        return self.store.save_report_csv(topics)

    def build_report(
        self,
        topics: list[dict],
        clusters: list[dict],
        metadata: dict,
    ) -> dict:
        """Sestaví kompletní report objekt.

        Args:
            topics: Zpracované a scorované topiky
            clusters: Výsledky clusterování
            metadata: Metadata běhu (scan_date, sources_used, total_items, processing_time)
        """
        return {
            "metadata": {
                "scan_date": metadata.get("scan_date", date.today().isoformat()),
                "generated_at": datetime.now().isoformat(),
                "sources_used": metadata.get("sources_used", []),
                "total_items_fetched": metadata.get("total_items", 0),
                "topics_extracted": len(topics),
                "clusters_found": len(clusters),
                "processing_time_seconds": metadata.get("processing_time", 0),
            },
            "topics": topics,
            "clusters": clusters,
        }
