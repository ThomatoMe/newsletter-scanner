"""Automatická kategorizace topiků do niches (Marketing, AI, Analytics)."""

import logging

logger = logging.getLogger(__name__)


class TopicCategorizer:
    """Řadí klíčová slova do kategorií na základě slovníků."""

    def __init__(self, keywords: dict[str, list[str]], categories_config: dict):
        """
        Args:
            keywords: Slovníky klíčových slov z keywords.yaml (kategorie -> seznam slov)
            categories_config: Konfigurace kategorií s display_name
        """
        self.keywords = keywords
        self.categories_config = categories_config

    def categorize(self, keyword: str, context: str = "") -> list[dict]:
        """Vrací seznam kategorií s confidence score.

        Args:
            keyword: Klíčové slovo k zařazení
            context: Dodatečný kontext (title + description)

        Returns:
            Seznam: [{"category": str, "display_name": str, "confidence": float}]
        """
        keyword_lower = keyword.lower().strip()
        context_lower = context.lower()
        results = []

        for category, word_list in self.keywords.items():
            confidence = 0.0

            # Přesná shoda klíčového slova se slovníkem
            if keyword_lower in word_list:
                confidence += 0.8

            # Částečná shoda – klíčové slovo je podřetězcem slova ze slovníku nebo naopak
            for word in word_list:
                if word in keyword_lower and word != keyword_lower:
                    confidence += 0.4
                    break
                if keyword_lower in word and word != keyword_lower:
                    confidence += 0.3
                    break

            # Kontrola kontextu – kolik slov ze slovníku se vyskytuje v kontextu
            if context_lower:
                context_matches = sum(1 for w in word_list if w in context_lower)
                context_score = min(context_matches * 0.1, 0.5)
                confidence += context_score

            # Minimální práh pro zařazení
            if confidence >= 0.3:
                display_name = self.categories_config.get(category, {}).get(
                    "display_name", category
                )
                results.append(
                    {
                        "category": category,
                        "display_name": display_name,
                        "confidence": min(confidence, 1.0),
                    }
                )

        # Seřazení podle confidence
        results.sort(key=lambda x: x["confidence"], reverse=True)

        # Pokud žádná kategorie – vrátíme "other"
        if not results:
            results.append(
                {
                    "category": "other",
                    "display_name": "Other",
                    "confidence": 0.0,
                }
            )

        return results

    def categorize_batch(
        self, keywords_data: list[dict], items: list
    ) -> list[dict]:
        """Kategorizuje seznam klíčových slov najednou.

        Args:
            keywords_data: Seznam z extractoru [{"keyword": str, "source_items": list[int], ...}]
            items: Původní FetchedItem seznam (pro kontext)

        Returns:
            Obohacená keywords_data se sloupcem "categories"
        """
        for kw_data in keywords_data:
            keyword = kw_data["keyword"]

            # Sestavení kontextu z příslušných položek
            context_parts = []
            for idx in kw_data.get("source_items", []):
                if idx < len(items):
                    item = items[idx]
                    context_parts.append(f"{item.title} {item.description}")
            context = " ".join(context_parts)

            kw_data["categories"] = self.categorize(keyword, context)

        logger.info("Kategorizováno %d klíčových slov", len(keywords_data))
        return keywords_data
