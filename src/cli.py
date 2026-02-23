"""CLI rozhraní pro LinkedIn Topic Scanner."""

import io
import logging
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import click
from rich.console import Console

# Oprava Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from src.config_loader import load_config, load_keywords
from src.fetchers.base import FetchedItem
from src.fetchers.google_news import GoogleNewsFetcher
from src.fetchers.google_trends import GoogleTrendsFetcher
from src.fetchers.hackernews import HackerNewsFetcher
from src.fetchers.linkedin_rss import LinkedInRSSFetcher
from src.fetchers.reddit import RedditFetcher
from src.processing.categorizer import TopicCategorizer
from src.processing.clustering import TopicClusterer
from src.processing.extractor import KeywordExtractor
from src.processing.scorer import TrendScorer
from src.processing.summarizer import TopicSummarizer
from src.reporting.console import ConsoleReporter
from src.reporting.email_report import EmailReporter
from src.reporting.export import ReportExporter
from src.storage.bigquery_dedup import BigQueryDedup
from src.storage.fetch_cache import FetchCache
from src.storage.history import HistoryTracker
from src.storage.store import DataStore

# Kořenový adresář projektu
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

console = Console()

# Registry fetcherů
FETCHER_REGISTRY = {
    "google_news": GoogleNewsFetcher,
    "reddit": RedditFetcher,
    "hackernews": HackerNewsFetcher,
    "google_trends": GoogleTrendsFetcher,
    "linkedin_rss": LinkedInRSSFetcher,
}


def _setup_logging(verbose: bool) -> None:
    """Nastaví logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _fetch_all(
    config: dict,
    source_filter: list[str] | None = None,
    fetch_cache: FetchCache | None = None,
) -> tuple[list[FetchedItem], list[str]]:
    """Stáhne data ze všech povolených zdrojů.

    Args:
        config: Konfigurace aplikace
        source_filter: Volitelný filtr zdrojů
        fetch_cache: Cache posledního běhu – přeskočí staré články

    Returns:
        Tuple (seznam položek, seznam použitých zdrojů)
    """
    sources_config = config.get("sources", {})
    all_items: list[FetchedItem] = []
    sources_used: list[str] = []

    for source_name, fetcher_class in FETCHER_REGISTRY.items():
        source_cfg = sources_config.get(source_name, {})

        # Kontrola, zda je zdroj povolený
        if not source_cfg.get("enabled", True):
            continue

        # Filtr zdrojů (pokud zadán)
        if source_filter and source_name not in source_filter:
            continue

        console.print(f"  Stahuji z [bold]{source_name}[/bold]...", end=" ")

        try:
            fetcher = fetcher_class(source_cfg)
            items = fetcher.fetch()

            # Filtrování starých článků přes fetch cache
            if fetch_cache:
                before = len(items)
                items = fetch_cache.filter_new_items(items, source_name)
                skipped = before - len(items)
                if skipped > 0:
                    console.print(
                        f"[green]{len(items)} nových[/green] "
                        f"[dim](přeskočeno {skipped} starých)[/dim]"
                    )
                else:
                    console.print(f"[green]{len(items)} položek[/green]")
                # Aktualizovat cache timestamp pro tento zdroj
                fetch_cache.update(source_name)
            else:
                console.print(f"[green]{len(items)} položek[/green]")

            all_items.extend(items)
            sources_used.append(source_name)
        except Exception as e:
            console.print(f"[red]CHYBA: {e}[/red]")
            logging.getLogger(__name__).error("Fetcher %s selhal: %s", source_name, e)

    return all_items, sources_used


def _process(
    items: list[FetchedItem], config: dict, keywords: dict
) -> tuple[list[dict], list[dict]]:
    """Zpracuje stažené položky (extrakce, kategorizace, scoring, clustering).

    Returns:
        Tuple (seznam scorovaných topiků, seznam clusterů)
    """
    processing_config = config.get("processing", {})
    scoring_config = config.get("scoring", {})
    categories_config = config.get("categories", {})

    # Extrakce klíčových slov
    console.print("  Extrahování klíčových slov...", end=" ")
    extractor = KeywordExtractor(processing_config)
    topics = extractor.extract(items)
    console.print(f"[green]{len(topics)} klíčových slov[/green]")

    if not topics:
        return [], []

    # Kategorizace
    console.print("  Kategorizace topiků...", end=" ")
    categorizer = TopicCategorizer(keywords, categories_config)
    topics = categorizer.categorize_batch(topics, items)
    console.print("[green]hotovo[/green]")

    # Scoring
    console.print("  Scoring trendů...", end=" ")
    scorer = TrendScorer(scoring_config)
    all_sources = {item.source for item in items}
    topics = scorer.score_batch(topics, items, all_sources)
    console.print("[green]hotovo[/green]")

    # Clustering
    clusters: list[dict] = []
    if processing_config.get("clustering", {}).get("enabled", True):
        console.print("  Clustering topiků...", end=" ")
        clusterer = TopicClusterer(processing_config)
        clusters = clusterer.cluster(items)
        console.print(f"[green]{len(clusters)} clusterů[/green]")

    return topics, clusters


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Podrobný výstup (debug logging)")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """LinkedIn Topic Scanner – sledování trending témat v Marketing, AI a Analytics."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@main.command()
@click.option(
    "--sources",
    "-s",
    default=None,
    help="Čárkou oddělené zdroje (google_news,reddit,hackernews,google_trends,linkedin_rss)",
)
@click.option("--no-report", is_flag=True, help="Přeskočit generování reportu")
@click.option("--email", is_flag=True, help="Odeslat report emailem")
@click.option("--dry-run", is_flag=True, help="Jen ověřit konfiguraci bez stahování")
@click.pass_context
def scan(ctx: click.Context, sources: str | None, no_report: bool, email: bool, dry_run: bool) -> None:
    """Stáhne data ze zdrojů a vygeneruje report."""
    start_time = time.time()

    # Načtení konfigurace
    config = load_config(CONFIG_DIR)
    keywords = load_keywords(CONFIG_DIR)
    data_dir = PROJECT_ROOT / config["general"]["data_dir"]

    if dry_run:
        console.print("[yellow]DRY RUN – ověřuji konfiguraci...[/yellow]")
        console.print(f"  Projekt: {PROJECT_ROOT}")
        console.print(f"  Config: {CONFIG_DIR}")
        console.print(f"  Data: {data_dir}")
        console.print(f"  Zdroje: {list(config.get('sources', {}).keys())}")
        console.print(f"  Kategorie klíčových slov: {list(keywords.keys())}")
        console.print("[green]Konfigurace OK[/green]")
        return

    # Filtr zdrojů
    source_filter = [s.strip() for s in sources.split(",")] if sources else None

    # Inicializace fetch cache (přeskakování starých článků)
    fetch_cache = FetchCache(data_dir)

    console.print("[bold blue]FÁZE 1: Sběr dat[/bold blue]")
    items, sources_used = _fetch_all(config, source_filter, fetch_cache)

    if not items:
        console.print("[red]Žádná data nebyla stažena![/red]")
        return

    # Deduplikace – odfiltrování již odeslaných článků
    dedup = BigQueryDedup(config)
    if dedup.enabled and dedup.client:
        dedup_days = config.get("bigquery", {}).get("dedup_days", 7)
        original_count = len(items)
        items = dedup.filter_new(items, days=dedup_days)
        console.print(
            f"  Deduplikace: [green]{len(items)} nových[/green] "
            f"(přeskočeno {original_count - len(items)} již odeslaných)"
        )

    if not items:
        console.print("[yellow]Žádné nové články – vše už bylo odesláno dříve.[/yellow]")
        return

    # Uložení surových dat
    store = DataStore(data_dir)
    for source_name in sources_used:
        source_items = [asdict(i) for i in items if i.source == source_name]
        store.save_raw(source_items, source_name)

    console.print(f"\n[bold blue]FÁZE 2: Zpracování[/bold blue] ({len(items)} položek)")
    topics, clusters = _process(items, config, keywords)

    if not topics:
        console.print("[yellow]Žádné topiky nebyly extrahovány[/yellow]")
        return

    # Uložení zpracovaných dat
    store.save_processed(topics)

    # Aktualizace historie
    history = HistoryTracker(data_dir)
    history.add_run(topics)

    elapsed = time.time() - start_time

    metadata = {
        "scan_date": date.today().isoformat(),
        "sources_used": sources_used,
        "total_items": len(items),
        "processing_time": round(elapsed, 1),
    }

    # AI sumarizace (pokud je zapnutá)
    newsletter_intro = ""
    if config.get("ai", {}).get("enabled", False):
        console.print(f"\n[bold blue]FÁZE 3: AI sumarizace[/bold blue]")
        summarizer = TopicSummarizer(config)

        # Sestavení categories_map (item index -> categories)
        categories_map: dict[int, list[dict]] = {}
        for kw_data in topics:
            for idx in kw_data.get("source_items", []):
                if idx not in categories_map:
                    categories_map[idx] = kw_data.get("categories", [])

        console.print("  Generuji AI souhrny clusterů...", end=" ")
        clusters = summarizer.summarize_all_clusters(clusters, items, categories_map)
        console.print("[green]hotovo[/green]")

        console.print("  Generuji úvod newsletteru...", end=" ")
        newsletter_intro = summarizer.generate_newsletter_intro(clusters, metadata)
        console.print("[green]hotovo[/green]")

    # Report
    if not no_report:
        phase_num = "4" if config.get("ai", {}).get("enabled", False) else "3"
        console.print(f"\n[bold blue]FÁZE {phase_num}: Report[/bold blue]")

        # Konzolový report
        reporter = ConsoleReporter(config.get("reporting", {}))
        reporter.print_report(topics, clusters, metadata)

        # Export
        export_config = config.get("reporting", {}).get("export", {})
        exporter = ReportExporter(store)

        if export_config.get("json", True):
            report_obj = exporter.build_report(topics, clusters, metadata)
            json_path = exporter.export_json(report_obj)
            console.print(f"  JSON report: {json_path}")

        if export_config.get("csv", True):
            csv_path = exporter.export_csv(topics)
            console.print(f"  CSV report: {csv_path}")

        # Email newsletter
        if email or config.get("email", {}).get("enabled", False):
            console.print("  Odesílám newsletter email...", end=" ")
            email_reporter = EmailReporter(config)
            if email_reporter.send_report(clusters, items, metadata, newsletter_intro):
                console.print("[green]odesláno[/green]")
                # Označit odeslané články v BigQuery
                if dedup.enabled and dedup.client:
                    dedup.mark_sent(items, clusters)
                    console.print("  BigQuery: odeslané články uloženy pro deduplikaci")
            else:
                console.print("[red]selhalo (zkontroluj email konfiguraci)[/red]")

    console.print(f"\n[bold green]Hotovo![/bold green] ({elapsed:.1f}s)")


@main.command()
@click.option("--format", "-f", "fmt", type=click.Choice(["console", "json", "csv"]), default="console")
@click.option("--top-n", "-n", default=15, help="Počet topiků k zobrazení")
@click.pass_context
def report(ctx: click.Context, fmt: str, top_n: int) -> None:
    """Vygeneruje report z posledních uložených dat (bez stahování)."""
    config = load_config(CONFIG_DIR)
    data_dir = PROJECT_ROOT / config["general"]["data_dir"]
    store = DataStore(data_dir)

    topics = store.load_latest_processed()
    if not topics:
        console.print("[red]Žádná zpracovaná data nenalezena. Spusťte nejdříve 'lts scan'.[/red]")
        return

    if fmt == "console":
        reporting_config = config.get("reporting", {})
        reporting_config.setdefault("console", {})["top_n"] = top_n
        reporter = ConsoleReporter(reporting_config)
        reporter.print_report(topics[:top_n])
    elif fmt == "json":
        exporter = ReportExporter(store)
        report_obj = exporter.build_report(topics, [], {"scan_date": "from_cache"})
        path = exporter.export_json(report_obj)
        console.print(f"JSON report: {path}")
    elif fmt == "csv":
        exporter = ReportExporter(store)
        path = exporter.export_csv(topics)
        console.print(f"CSV report: {path}")


@main.command()
@click.option("--days", "-d", default=7, help="Počet dní zpětně")
@click.pass_context
def history(ctx: click.Context, days: int) -> None:
    """Zobrazí historické trendy a nové topiky."""
    config = load_config(CONFIG_DIR)
    data_dir = PROJECT_ROOT / config["general"]["data_dir"]
    tracker = HistoryTracker(data_dir)

    runs = tracker.get_runs_count()
    console.print(f"[bold]Historie:[/bold] {runs} běhů zaznamenáno\n")

    if runs < 2:
        console.print("[yellow]Pro zobrazení trendů je potřeba alespoň 2 běhy.[/yellow]")
        return

    # Rostoucí trendy
    trending = tracker.get_trending(days)
    if trending:
        from rich.table import Table

        table = Table(title=f"Rising Topics (posledních {days} dní)", border_style="green")
        table.add_column("Keyword", style="bold")
        table.add_column("Current Score", justify="right")
        table.add_column("Previous Score", justify="right")
        table.add_column("Change", justify="right", style="green")

        for t in trending[:15]:
            table.add_row(
                t["keyword"],
                f"{t['current_score']:.3f}",
                f"{t['previous_score']:.3f}",
                f"+{t['change']:.3f}",
            )
        console.print(table)
    else:
        console.print("[dim]Žádné rostoucí trendy nenalezeny[/dim]")

    # Nové topiky
    new_topics = tracker.get_new_topics(days)
    if new_topics:
        console.print(f"\n[bold]Nové topiky (posledních {days} dní):[/bold]")
        for t in new_topics[:10]:
            console.print(f"  - {t['keyword']} (first seen: {t['first_seen']})")


@main.command("config")
@click.option("--show", is_flag=True, help="Zobrazí aktuální konfiguraci")
@click.option("--validate", is_flag=True, help="Validuje config.yaml")
@click.pass_context
def config_cmd(ctx: click.Context, show: bool, validate: bool) -> None:
    """Správa konfigurace."""
    config = load_config(CONFIG_DIR)

    if show or not validate:
        import yaml

        console.print("[bold]Aktuální konfigurace:[/bold]\n")
        console.print(yaml.dump(config, default_flow_style=False, allow_unicode=True))

    if validate:
        # Kontrola povinných sekcí
        required = ["general", "sources", "processing", "scoring", "categories"]
        missing = [s for s in required if s not in config]
        if missing:
            console.print(f"[red]Chybějící sekce: {', '.join(missing)}[/red]")
        else:
            console.print("[green]Konfigurace je validní.[/green]")

        # Kontrola zdrojů
        sources = config.get("sources", {})
        enabled = [s for s, cfg in sources.items() if cfg.get("enabled", True)]
        console.print(f"Povolené zdroje: {', '.join(enabled)}")


if __name__ == "__main__":
    main()
