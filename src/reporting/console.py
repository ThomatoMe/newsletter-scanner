"""Formátovaný výstup do konzole pomocí Rich."""

import logging
from datetime import date

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)

# Barvy pro kategorie
CATEGORY_COLORS = {
    "marketing_digital": "cyan",
    "ai_ml": "magenta",
    "data_analytics": "green",
    "other": "white",
}


class ConsoleReporter:
    """Vypisuje formátovaný report do konzole."""

    def __init__(self, config: dict):
        console_config = config.get("console", {})
        self.top_n: int = console_config.get("top_n", 15)
        self.show_sources: bool = console_config.get("show_sources", True)
        self.console = Console()

    def print_report(
        self,
        topics: list[dict],
        clusters: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Vypíše kompletní report do konzole."""
        self.console.print()

        # Hlavička
        self._print_header(metadata or {}, len(topics))

        # Top trending topiky
        self._print_top_topics(topics)

        # Rozdělení podle kategorií
        self._print_categories(topics)

        # Clustery (pokud jsou)
        if clusters:
            self._print_clusters(clusters)

        self.console.print()

    def _print_header(self, metadata: dict, topic_count: int) -> None:
        """Vypíše hlavičku reportu."""
        scan_date = metadata.get("scan_date", date.today().isoformat())
        sources_used = metadata.get("sources_used", [])
        total_items = metadata.get("total_items", 0)

        header_text = (
            f"[bold]LinkedIn Topic Scanner[/bold]\n"
            f"Datum: {scan_date}\n"
            f"Celkem položek: {total_items} | Extrahováno topiků: {topic_count}\n"
            f"Zdroje: {', '.join(sources_used) if sources_used else 'N/A'}"
        )

        self.console.print(Panel(header_text, title="SCAN REPORT", border_style="blue"))

    def _print_top_topics(self, topics: list[dict]) -> None:
        """Vypíše tabulku top trending topiků."""
        table = Table(title=f"Top {self.top_n} Trending Topics", border_style="blue")
        table.add_column("#", style="dim", width=4)
        table.add_column("Keyword", style="bold", min_width=20)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Category", min_width=15)
        table.add_column("Mentions", justify="right", width=8)

        if self.show_sources:
            table.add_column("Sources", min_width=15)

        for i, topic in enumerate(topics[: self.top_n], 1):
            # Kategorie s barvou
            categories = topic.get("categories", [])
            if categories:
                primary = categories[0]
                cat_name = primary.get("display_name", primary.get("category", ""))
                cat_key = primary.get("category", "other")
                color = CATEGORY_COLORS.get(cat_key, "white")
                cat_str = f"[{color}]{cat_name}[/{color}]"
            else:
                cat_str = "[dim]Other[/dim]"

            # Score s barevným indikátorem
            score = topic.get("trend_score", 0)
            if score >= 0.5:
                score_str = f"[green]{score:.3f}[/green]"
            elif score >= 0.3:
                score_str = f"[yellow]{score:.3f}[/yellow]"
            else:
                score_str = f"{score:.3f}"

            row = [
                str(i),
                topic.get("keyword", ""),
                score_str,
                cat_str,
                str(topic.get("mention_count", 0)),
            ]

            if self.show_sources:
                sources = topic.get("sources", [])
                row.append(", ".join(sources))

            table.add_row(*row)

        self.console.print(table)

    def _print_categories(self, topics: list[dict]) -> None:
        """Vypíše přehled podle kategorií."""
        # Agregace
        cat_topics: dict[str, list[dict]] = {}
        for topic in topics:
            for cat in topic.get("categories", []):
                cat_key = cat.get("category", "other")
                cat_topics.setdefault(cat_key, []).append(topic)

        table = Table(title="Topics by Category", border_style="green")
        table.add_column("Category", style="bold", min_width=20)
        table.add_column("Count", justify="right", width=8)
        table.add_column("Top Keywords", min_width=40)

        for cat_key, cat_items in sorted(cat_topics.items(), key=lambda x: len(x[1]), reverse=True):
            color = CATEGORY_COLORS.get(cat_key, "white")
            # Display name z prvního topiku
            display_name = cat_key
            if cat_items and cat_items[0].get("categories"):
                for c in cat_items[0]["categories"]:
                    if c.get("category") == cat_key:
                        display_name = c.get("display_name", cat_key)
                        break

            top_kws = [t.get("keyword", "") for t in cat_items[:5]]

            table.add_row(
                f"[{color}]{display_name}[/{color}]",
                str(len(cat_items)),
                ", ".join(top_kws),
            )

        self.console.print(table)

    def _print_clusters(self, clusters: list[dict]) -> None:
        """Vypíše přehled clusterů."""
        table = Table(title="Topic Clusters", border_style="yellow")
        table.add_column("#", style="dim", width=4)
        table.add_column("Label", style="bold", min_width=25)
        table.add_column("Size", justify="right", width=8)
        table.add_column("Top Terms", min_width=30)

        for i, cluster in enumerate(clusters, 1):
            table.add_row(
                str(i),
                cluster.get("label", ""),
                str(cluster.get("size", 0)),
                ", ".join(cluster.get("top_terms", [])[:5]),
            )

        self.console.print(table)
