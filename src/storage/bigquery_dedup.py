"""Deduplikace článků přes BigQuery – ukládá URL již poslaných článků."""

import hashlib
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from google.cloud import bigquery

    BQ_AVAILABLE = True
except ImportError:
    BQ_AVAILABLE = False


# SQL pro vytvoření tabulky (spustí se automaticky při prvním běhu)
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{dataset}.sent_articles` (
    url_hash STRING NOT NULL,
    url STRING,
    title STRING,
    source STRING,
    sent_date DATE,
    cluster_label STRING
)
PARTITION BY sent_date
OPTIONS(
    description='Již odeslané články z Newsletter Scanneru'
)
"""


class BigQueryDedup:
    """Sleduje již odeslané články v BigQuery pro deduplikaci."""

    def __init__(self, config: dict):
        bq_config = config.get("bigquery", {})
        self.enabled: bool = bq_config.get("enabled", False)
        self.project: str = bq_config.get("project", "")
        self.dataset: str = bq_config.get("dataset", "newsletter_scanner")
        self.client: Optional[object] = None

        if self.enabled and BQ_AVAILABLE and self.project:
            try:
                self.client = bigquery.Client(project=self.project)
                self._ensure_table()
                logger.info("BigQuery deduplikace aktivní: %s.%s", self.project, self.dataset)
            except Exception as e:
                logger.error("BigQuery inicializace selhala: %s", e)
                self.client = None

    def _ensure_table(self) -> None:
        """Vytvoří dataset a tabulku pokud neexistují."""
        if not self.client:
            return

        # Vytvoření datasetu
        dataset_ref = bigquery.DatasetReference(self.project, self.dataset)
        try:
            self.client.get_dataset(dataset_ref)
        except Exception:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "EU"
            self.client.create_dataset(dataset, exists_ok=True)
            logger.info("BigQuery dataset vytvořen: %s", self.dataset)

        # Vytvoření tabulky
        sql = _CREATE_TABLE_SQL.format(dataset=f"{self.project}.{self.dataset}")
        self.client.query(sql).result()

    def _url_hash(self, url: str) -> str:
        """Vytvoří hash z URL pro rychlé porovnání."""
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def get_sent_urls(self, days: int = 7) -> set[str]:
        """Vrátí set URL hashů článků odeslaných za posledních N dní."""
        if not self.client:
            return set()

        sql = f"""
        SELECT url_hash
        FROM `{self.project}.{self.dataset}.sent_articles`
        WHERE sent_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
        """

        try:
            result = self.client.query(sql).result()
            hashes = {row.url_hash for row in result}
            logger.info("BigQuery: načteno %d již odeslaných článků", len(hashes))
            return hashes
        except Exception as e:
            logger.warning("BigQuery čtení selhalo: %s", e)
            return set()

    def was_sent_today(self) -> bool:
        """Zkontroluje, jestli už byl dnes odeslán newsletter."""
        if not self.client:
            return False

        sql = f"""
        SELECT COUNT(*) as cnt
        FROM `{self.project}.{self.dataset}.sent_articles`
        WHERE sent_date = CURRENT_DATE()
        """

        try:
            result = self.client.query(sql).result()
            count = list(result)[0].cnt
            if count > 0:
                logger.info("BigQuery: dnes už bylo odesláno %d článků – přeskakuji", count)
                return True
            return False
        except Exception as e:
            logger.warning("BigQuery kontrola dnešního odeslání selhala: %s", e)
            return False

    def filter_new(self, items: list, days: int = 7) -> list:
        """Odfiltruje již odeslané články. Vrací jen nové.

        Args:
            items: Seznam FetchedItem objektů
            days: Kolik dní zpětně kontrolovat

        Returns:
            Seznam FetchedItem, které ještě nebyly odeslány
        """
        if not self.client:
            return items

        sent_hashes = self.get_sent_urls(days)
        if not sent_hashes:
            return items

        new_items = []
        skipped = 0
        for item in items:
            if self._url_hash(item.url) not in sent_hashes:
                new_items.append(item)
            else:
                skipped += 1

        logger.info(
            "Deduplikace: %d nových, %d přeskočeno (již odesláno)",
            len(new_items),
            skipped,
        )
        return new_items

    def mark_sent(self, items: list, clusters: list) -> None:
        """Označí články jako odeslané v BigQuery.

        Args:
            items: FetchedItem objekty, které byly odeslány
            clusters: Clustery (pro přiřazení cluster_label)
        """
        if not self.client:
            return

        # Sestavení mapování item_index -> cluster_label
        index_to_cluster: dict[int, str] = {}
        for cluster in clusters:
            label = cluster.get("label", "")
            for idx in cluster.get("item_indices", []):
                index_to_cluster[idx] = label

        # Sestavení řádků pro insert
        rows = []
        today = datetime.now().strftime("%Y-%m-%d")

        for i, item in enumerate(items):
            if not item.url:
                continue
            rows.append(
                {
                    "url_hash": self._url_hash(item.url),
                    "url": item.url[:1000],
                    "title": (item.title or "")[:500],
                    "source": item.source,
                    "sent_date": today,
                    "cluster_label": index_to_cluster.get(i, ""),
                }
            )

        if not rows:
            return

        # Batch insert
        table_ref = f"{self.project}.{self.dataset}.sent_articles"
        try:
            errors = self.client.insert_rows_json(table_ref, rows)
            if errors:
                logger.warning("BigQuery insert chyby: %s", errors[:3])
            else:
                logger.info("BigQuery: uloženo %d odeslaných článků", len(rows))
        except Exception as e:
            logger.error("BigQuery insert selhal: %s", e)
