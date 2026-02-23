"""Cache posledního běhu – přeskočení již stažených článků podle data."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class FetchCache:
    """Ukládá timestamp posledního úspěšného stažení per zdroj.

    Při dalším běhu fetchery přeskočí články starší než poslední run.
    Soubor: data/fetch_cache.json
    """

    def __init__(self, data_dir: Path):
        self.cache_file = Path(data_dir) / "fetch_cache.json"
        self._cache: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        """Načte cache z JSON souboru."""
        if not self.cache_file.exists():
            return {}

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Chyba při načítání fetch cache: %s", e)
            return {}

    def save(self) -> None:
        """Uloží cache do JSON souboru."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def get_last_run(self, source_name: str) -> datetime | None:
        """Vrátí datetime posledního běhu pro daný zdroj (nebo None)."""
        ts = self._cache.get(source_name)
        if not ts:
            return None

        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    def update(self, source_name: str) -> None:
        """Zaznamená aktuální čas jako poslední běh pro daný zdroj."""
        self._cache[source_name] = datetime.now(tz=timezone.utc).isoformat()
        self.save()
        logger.debug("Fetch cache aktualizován: %s", source_name)

    def filter_new_items(self, items: list, source_name: str) -> list:
        """Odfiltruje články starší než poslední běh.

        Args:
            items: Seznam FetchedItem objektů
            source_name: Název zdroje (pro lookup v cache)

        Returns:
            Seznam FetchedItem novějších než poslední běh
        """
        last_run = self.get_last_run(source_name)
        if not last_run:
            # První běh – vrátíme vše
            return items

        new_items = []
        skipped = 0

        for item in items:
            if item.published is None:
                # Nemá datum – ponecháme (raději víc než míň)
                new_items.append(item)
            elif item.published > last_run:
                new_items.append(item)
            else:
                skipped += 1

        if skipped > 0:
            logger.info(
                "Fetch cache %s: %d nových, %d přeskočeno (starší než %s)",
                source_name,
                len(new_items),
                skipped,
                last_run.strftime("%Y-%m-%d %H:%M"),
            )

        return new_items
