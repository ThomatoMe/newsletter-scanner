"""AI sumarizace témat pomocí Claude API (Anthropic)."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class TopicSummarizer:
    """Generuje AI souhrny témat a návrhy článků pomocí Claude API."""

    def __init__(self, config: dict):
        ai_config = config.get("ai", {})
        self.enabled: bool = ai_config.get("enabled", False)
        self.api_key: str = ai_config.get("anthropic_api_key", "")
        self.model: str = ai_config.get("model", "claude-sonnet-4-5-20250929")
        self.max_tokens: int = ai_config.get("max_tokens", 1024)
        self.client: Optional[object] = None

        if self.enabled and ANTHROPIC_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def summarize_topic_group(
        self,
        topic_label: str,
        articles: list[dict],
        category: str = "",
    ) -> dict:
        """Vygeneruje souhrn pro skupinu článků pod jedním tématem.

        Args:
            topic_label: Název tématu/clusteru (např. "AI marketing automation")
            articles: Seznam článků [{"title": str, "url": str, "source": str, "description": str}]
            category: Kategorie (Marketing, AI, Analytics)

        Returns:
            {"summary": str, "why_it_matters": str, "article_idea": str, "article_angle": str}
        """
        if not self.client:
            return self._fallback_summary(topic_label, articles)

        # Sestavení kontextu z článků
        articles_text = "\n".join(
            f"- {a.get('title', '')} ({a.get('source', '')})"
            for a in articles[:15]
        )

        prompt = f"""Jsi expert na digital marketing, AI a data analytics. Analyzuj toto téma a související články.

TÉMA: {topic_label}
KATEGORIE: {category}

ČLÁNKY:
{articles_text}

Odpověz ve strukturovaném formátu (česky):

SOUHRN (2-3 věty):
Co se aktuálně děje v tomto tématu? Jaký je hlavní trend nebo událost?

PROČ JE TO DŮLEŽITÉ (1-2 věty):
Proč by to mělo zajímat digital marketing/analytics profesionála?

NÁVRH ČLÁNKU - TITULEK:
Navrhni titulek pro LinkedIn příspěvek nebo článek, který by mohl napsat analytik/konzultant.

NÁVRH ČLÁNKU - ÚHEL:
Jaký úhel pohledu zvolit? Co konkrétně rozebrat? (2-3 věty)"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text
            return self._parse_response(text)

        except Exception as e:
            logger.warning("Claude API volání selhalo pro '%s': %s", topic_label, e)
            return self._fallback_summary(topic_label, articles)

    def summarize_all_clusters(
        self,
        clusters: list[dict],
        items: list,
        categories_map: dict[int, list[dict]],
    ) -> list[dict]:
        """Vygeneruje souhrny pro všechny clustery.

        Args:
            clusters: Výstup z TopicClusterer
            items: Původní FetchedItem seznam
            categories_map: Mapování item index -> categories

        Returns:
            Obohacené clustery s AI souhrny
        """
        if not self.enabled:
            logger.info("AI sumarizace je vypnutá")
            return clusters

        if not self.client:
            logger.warning("Claude API klient není k dispozici (chybí API klíč nebo knihovna)")
            return clusters

        for cluster in clusters:
            # Sesbírat články z clusteru
            articles = []
            cluster_categories: set[str] = set()

            for idx in cluster.get("item_indices", []):
                if idx < len(items):
                    item = items[idx]
                    articles.append(
                        {
                            "title": item.title,
                            "url": item.url,
                            "source": item.source,
                            "description": item.description[:200],
                        }
                    )
                    # Kategorie z mapy
                    for cat in categories_map.get(idx, []):
                        cluster_categories.add(cat.get("display_name", ""))

            category_str = ", ".join(sorted(cluster_categories)) if cluster_categories else ""

            # AI souhrn
            summary = self.summarize_topic_group(
                topic_label=cluster.get("label", ""),
                articles=articles,
                category=category_str,
            )

            cluster["ai_summary"] = summary
            logger.debug("AI souhrn pro cluster '%s': hotovo", cluster.get("label", ""))

        logger.info("AI sumarizace dokončena pro %d clusterů", len(clusters))
        return clusters

    def generate_newsletter_intro(self, clusters: list[dict], metadata: dict) -> str:
        """Vygeneruje úvodní odstavec pro newsletter."""
        if not self.client:
            return ""

        cluster_labels = [c.get("label", "") for c in clusters[:10]]
        total_items = metadata.get("total_items", 0)
        sources = metadata.get("sources_used", [])

        prompt = f"""Jsi editor denního newsletteru o trendech v digital marketingu, AI a analytics.

Dnes bylo analyzováno {total_items} článků z těchto zdrojů: {', '.join(sources)}.

Hlavní témata dne:
{chr(10).join(f'- {label}' for label in cluster_labels)}

Napiš krátký úvodní odstavec (3-4 věty, česky) pro denní newsletter. Buď stručný, věcný a zajímavý. Zaměř se na to, co je dnes nejzajímavější a proč. Nepoužívej emoji."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()

        except Exception as e:
            logger.warning("Generování newsletter intro selhalo: %s", e)
            return ""

    def _parse_response(self, text: str) -> dict:
        """Rozparsuje strukturovanou odpověď z Claude."""
        result = {
            "summary": "",
            "why_it_matters": "",
            "article_idea": "",
            "article_angle": "",
        }

        sections = {
            "SOUHRN": "summary",
            "PROČ JE TO DŮLEŽITÉ": "why_it_matters",
            "NÁVRH ČLÁNKU - TITULEK": "article_idea",
            "NÁVRH ČLÁNKU - ÚHEL": "article_angle",
        }

        current_key = None
        current_lines: list[str] = []

        for line in text.split("\n"):
            line_stripped = line.strip()

            # Kontrola, zda řádek začíná nějakou sekcí
            matched = False
            for section_name, key in sections.items():
                if line_stripped.upper().startswith(section_name):
                    # Uložit předchozí sekci
                    if current_key:
                        result[current_key] = "\n".join(current_lines).strip()
                    current_key = key
                    current_lines = []
                    # Pokud je na řádku i text za dvojtečkou
                    after_colon = line_stripped.split(":", 1)
                    if len(after_colon) > 1 and after_colon[1].strip():
                        current_lines.append(after_colon[1].strip())
                    matched = True
                    break

            if not matched and current_key:
                current_lines.append(line_stripped)

        # Uložit poslední sekci
        if current_key:
            result[current_key] = "\n".join(current_lines).strip()

        return result

    def _fallback_summary(self, topic_label: str, articles: list[dict]) -> dict:
        """Fallback souhrn bez AI – jen přehled článků."""
        top_titles = [a.get("title", "") for a in articles[:5]]
        return {
            "summary": f"Téma '{topic_label}' – {len(articles)} souvisejících článků.",
            "why_it_matters": "",
            "article_idea": "",
            "article_angle": "",
            "top_articles": top_titles,
        }
