"""Topic clustering pomocí MiniBatchKMeans."""

import html
import logging
import re

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from src.fetchers.base import FetchedItem

# Rozšířené stop words pro čistší clustering
_EXTRA_STOPS = {
    "nbsp", "amp", "quot", "href", "http", "https", "www", "com",
    "span", "font", "div", "class", "style", "color", "size",
    "reddit", "link", "comments", "submitted", "points", "ago",
}
_CUSTOM_STOP_WORDS = list(ENGLISH_STOP_WORDS | _EXTRA_STOPS)

logger = logging.getLogger(__name__)


class TopicClusterer:
    """Seskupuje položky do tematických clusterů."""

    def __init__(self, config: dict):
        clustering_config = config.get("clustering", {})
        self.enabled: bool = clustering_config.get("enabled", True)
        self.min_clusters: int = clustering_config.get("min_clusters", 3)
        self.max_clusters: int = clustering_config.get("max_clusters", 15)

    def cluster(self, items: list[FetchedItem]) -> list[dict]:
        """Seskupí položky do tematických clusterů.

        Returns:
            Seznam: [{"cluster_id": int, "label": str, "top_terms": list[str],
                       "item_indices": list[int], "size": int}]
        """
        if not self.enabled:
            return []

        if len(items) < self.min_clusters + 1:
            logger.warning(
                "Příliš málo položek pro clustering (%d, minimum %d)",
                len(items),
                self.min_clusters + 1,
            )
            return []

        # Sestavení a čištění dokumentů
        documents = []
        for item in items:
            text = html.unescape(f"{item.title} {item.description}")
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\b[0-9a-f]{6}\b", " ", text)
            text = re.sub(r"https?://\S+", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            documents.append(text)
        valid_docs = [(i, doc) for i, doc in enumerate(documents) if doc.strip()]

        if len(valid_docs) < self.min_clusters + 1:
            return []

        indices = [i for i, _ in valid_docs]
        texts = [doc for _, doc in valid_docs]

        # TF-IDF vektorizace s rozšířenými stop words
        tfidf = TfidfVectorizer(
            max_features=3000,
            stop_words=_CUSTOM_STOP_WORDS,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.85,
        )

        try:
            tfidf_matrix = tfidf.fit_transform(texts)
        except ValueError as e:
            logger.error("TF-IDF pro clustering selhal: %s", e)
            return []

        feature_names = tfidf.get_feature_names_out()

        # Určení optimálního počtu clusterů pomocí silhouette score
        optimal_k = self._find_optimal_k(tfidf_matrix, len(texts))

        # Clustering
        kmeans = MiniBatchKMeans(
            n_clusters=optimal_k,
            random_state=42,
            batch_size=min(256, len(texts)),
            n_init=3,
        )
        labels = kmeans.fit_predict(tfidf_matrix)

        # Extrakce top termů pro každý cluster
        results = []
        order_centroids = kmeans.cluster_centers_.argsort()[:, ::-1]

        for cluster_id in range(optimal_k):
            # Top termy z centroidu
            top_terms = [
                str(feature_names[idx])
                for idx in order_centroids[cluster_id, :5]
            ]

            # Položky v tomto clusteru
            cluster_mask = labels == cluster_id
            item_indices = [indices[i] for i in range(len(labels)) if cluster_mask[i]]

            # Label = top 3 termy spojené čárkou
            label = ", ".join(top_terms[:3])

            results.append(
                {
                    "cluster_id": cluster_id,
                    "label": label,
                    "top_terms": top_terms,
                    "item_indices": item_indices,
                    "size": len(item_indices),
                }
            )

        # Seřazení podle velikosti (největší první)
        results.sort(key=lambda x: x["size"], reverse=True)

        logger.info("Clustering: %d clusterů z %d položek", len(results), len(texts))
        return results

    def _find_optimal_k(self, tfidf_matrix, n_samples: int) -> int:
        """Najde optimální počet clusterů pomocí silhouette score."""
        max_k = min(self.max_clusters, n_samples - 1)
        min_k = min(self.min_clusters, max_k)

        if max_k <= min_k:
            return min_k

        # Pro malé datasety neoptimalizujeme
        if n_samples < 20:
            return min_k

        try:
            from sklearn.metrics import silhouette_score

            best_k = min_k
            best_score = -1.0

            for k in range(min_k, max_k + 1):
                kmeans = MiniBatchKMeans(
                    n_clusters=k, random_state=42, n_init=2,
                    batch_size=min(256, n_samples),
                )
                labels = kmeans.fit_predict(tfidf_matrix)

                # Silhouette score potřebuje alespoň 2 clustery a 2 vzorky
                if len(set(labels)) < 2:
                    continue

                score = silhouette_score(tfidf_matrix, labels, sample_size=min(500, n_samples))
                if score > best_score:
                    best_score = score
                    best_k = k

            logger.debug("Optimální K=%d (silhouette=%.3f)", best_k, best_score)
            return best_k

        except Exception as e:
            logger.warning("Silhouette score selhal, používám min_clusters=%d: %s", min_k, e)
            return min_k
