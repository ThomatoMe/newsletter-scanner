"""Načtení a validace YAML konfigurace."""

import os
from pathlib import Path
from typing import Any
import yaml
import logging

logger = logging.getLogger(__name__)

# Výchozí hodnoty konfigurace
DEFAULTS: dict[str, Any] = {
    "general": {
        "language": "english",
        "max_items_per_source": 100,
        "dedup_similarity_threshold": 0.85,
        "data_dir": "data",
    },
    "processing": {
        "extraction_method": "tfidf",
        "top_keywords": 30,
        "ngram_range": [1, 3],
        "min_document_frequency": 2,
        "clustering": {
            "enabled": True,
            "min_clusters": 3,
            "max_clusters": 15,
            "method": "minibatch_kmeans",
        },
    },
    "scoring": {
        "weights": {
            "frequency": 0.30,
            "recency": 0.30,
            "source_diversity": 0.25,
            "engagement": 0.15,
        },
        "recency_decay_hours": 48,
    },
    "reporting": {
        "console": {"top_n": 15, "show_sources": True},
        "export": {"json": True, "csv": True, "output_dir": "data/reports"},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Rekurzivní merge dvou slovníků (override přepíše base)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_dir: Path) -> dict:
    """Načte hlavní konfiguraci z config.yaml a doplní výchozí hodnoty."""
    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        logger.warning("Konfigurační soubor %s nenalezen, používám výchozí hodnoty", config_file)
        return DEFAULTS.copy()

    with open(config_file, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}

    config = _deep_merge(DEFAULTS, user_config)

    # Override z environment proměnných (pro Cloud Run)
    env_app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if env_app_password:
        config.setdefault("email", {})["app_password"] = env_app_password
        logger.info("Gmail App Password načteno z env proměnné")

    logger.info("Konfigurace načtena z %s", config_file)
    return config


def load_keywords(config_dir: Path) -> dict[str, list[str]]:
    """Načte slovníky klíčových slov z keywords.yaml."""
    keywords_file = config_dir / "keywords.yaml"
    if not keywords_file.exists():
        logger.warning("Soubor klíčových slov %s nenalezen", keywords_file)
        return {}

    with open(keywords_file, "r", encoding="utf-8") as f:
        keywords = yaml.safe_load(f) or {}

    # Normalizace na lowercase
    normalized: dict[str, list[str]] = {}
    for category, words in keywords.items():
        if isinstance(words, list):
            normalized[category] = [w.lower().strip() for w in words]

    logger.info("Klíčová slova načtena: %s kategorií", len(normalized))
    return normalized
