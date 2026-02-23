"""Extrakce klíčových slov z textu pomocí TF-IDF (a volitelně KeyBERT)."""

import logging
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from src.fetchers.base import FetchedItem

logger = logging.getLogger(__name__)

# Volitelně: KeyBERT pro lepší výsledky
try:
    from keybert import KeyBERT

    KEYBERT_AVAILABLE = True
except ImportError:
    KEYBERT_AVAILABLE = False


def _clean_text(text: str) -> str:
    """Vyčistí text od HTML tagů, entit a přebytečných mezer."""
    import html

    # Dekódování HTML entit (&nbsp; &amp; atd.)
    text = html.unescape(text)
    # Odstranění HTML tagů
    text = re.sub(r"<[^>]+>", " ", text)
    # Odstranění zbylých HTML atributů a hex kódů (6f6f6f, href, span, font...)
    text = re.sub(r"\b[0-9a-f]{6}\b", " ", text)
    # Odstranění URL
    text = re.sub(r"https?://\S+", " ", text)
    # Odstranění krátkých nesmyslných tokenů (1-2 znaky, které nejsou AI/ML/PR/HR apod.)
    text = re.sub(r"\b[a-z]{1,2}\b(?<!\bai\b)(?<!\bml\b)(?<!\bhr\b)(?<!\bpr\b)(?<!\bux\b)(?<!\bui\b)(?<!\bqa\b)(?<!\bci\b)(?<!\bcd\b)", " ", text)
    # Normalizace mezer
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class KeywordExtractor:
    """Extrahuje klíčová slova z kolekce FetchedItem pomocí TF-IDF."""

    def __init__(self, config: dict):
        self.method: str = config.get("extraction_method", "tfidf")
        self.top_n: int = config.get("top_keywords", 30)
        ngram_range = config.get("ngram_range", [1, 3])
        min_df = config.get("min_document_frequency", 2)

        # Rozšířené stop words – anglické + HTML/RSS artefakty
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

        extra_stops = {
            "nbsp", "amp", "quot", "href", "http", "https", "www", "com",
            "span", "font", "div", "class", "style", "color", "size",
            "reddit", "link", "comments", "submitted", "points", "ago",
        }
        custom_stop_words = list(ENGLISH_STOP_WORDS | extra_stops)

        self.tfidf = TfidfVectorizer(
            max_features=5000,
            stop_words=custom_stop_words,
            ngram_range=tuple(ngram_range),
            min_df=min_df,
            max_df=0.8,
        )

    def extract(self, items: list[FetchedItem]) -> list[dict]:
        """Extrahuje top N klíčových slov z kolekce položek.

        Returns:
            Seznam slovníků: [{"keyword": str, "score": float, "count": int, "source_items": list[int]}]
        """
        if not items:
            return []

        # Sestavení dokumentů (title + description)
        documents = [
            _clean_text(f"{item.title} {item.description}") for item in items
        ]

        # Odfiltrování prázdných dokumentů
        valid_docs = [(i, doc) for i, doc in enumerate(documents) if doc.strip()]
        if len(valid_docs) < 2:
            logger.warning("Příliš málo dokumentů pro TF-IDF (%d)", len(valid_docs))
            return []

        indices = [i for i, _ in valid_docs]
        texts = [doc for _, doc in valid_docs]

        if self.method == "keybert" and KEYBERT_AVAILABLE:
            return self._extract_keybert(texts, indices, items)
        return self._extract_tfidf(texts, indices, items)

    def _extract_tfidf(
        self, documents: list[str], indices: list[int], items: list[FetchedItem]
    ) -> list[dict]:
        """Extrakce pomocí TF-IDF."""
        try:
            tfidf_matrix = self.tfidf.fit_transform(documents)
        except ValueError as e:
            logger.error("TF-IDF fit_transform selhal: %s", e)
            return []

        feature_names = self.tfidf.get_feature_names_out()

        # Agregovaný TF-IDF score přes všechny dokumenty
        aggregated_scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()

        # Počet dokumentů, kde se keyword vyskytuje
        doc_counts = np.asarray((tfidf_matrix > 0).sum(axis=0)).flatten()

        # Mapování keyword -> zdrojové položky
        keyword_items: dict[int, list[int]] = {}
        matrix_array = tfidf_matrix.toarray()
        for doc_idx in range(len(documents)):
            nonzero = matrix_array[doc_idx].nonzero()[0]
            for feat_idx in nonzero:
                keyword_items.setdefault(feat_idx, []).append(indices[doc_idx])

        # Seřazení podle aggregated score
        top_indices = aggregated_scores.argsort()[::-1][: self.top_n]

        results = []
        for idx in top_indices:
            score = float(aggregated_scores[idx])
            if score <= 0:
                break
            results.append(
                {
                    "keyword": str(feature_names[idx]),
                    "score": score,
                    "count": int(doc_counts[idx]),
                    "source_items": keyword_items.get(idx, []),
                }
            )

        logger.info("TF-IDF: extrahováno %d klíčových slov", len(results))
        return results

    def _extract_keybert(
        self, documents: list[str], indices: list[int], items: list[FetchedItem]
    ) -> list[dict]:
        """Extrakce pomocí KeyBERT (pokud dostupný)."""
        try:
            model = KeyBERT()
            # Spojení všech dokumentů
            combined = " ".join(documents)
            keywords = model.extract_keywords(
                combined,
                keyphrase_ngram_range=(1, 3),
                stop_words="english",
                top_n=self.top_n,
            )

            results = []
            for keyword, score in keywords:
                # Spočítání výskytů
                count = sum(1 for doc in documents if keyword.lower() in doc.lower())
                matching_items = [
                    indices[i]
                    for i, doc in enumerate(documents)
                    if keyword.lower() in doc.lower()
                ]
                results.append(
                    {
                        "keyword": keyword,
                        "score": float(score),
                        "count": count,
                        "source_items": matching_items,
                    }
                )

            logger.info("KeyBERT: extrahováno %d klíčových slov", len(results))
            return results

        except Exception as e:
            logger.warning("KeyBERT selhal, fallback na TF-IDF: %s", e)
            return self._extract_tfidf(documents, indices, items)
