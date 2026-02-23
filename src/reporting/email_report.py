"""Odesílání newsletter-style email reportů přes Gmail SMTP."""

import html
import logging
import re
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# Barvy kategorií
_CAT_COLORS = {
    "marketing_digital": ("#0891b2", "#ecfeff"),
    "ai_ml": ("#7c3aed", "#f5f3ff"),
    "data_analytics": ("#059669", "#ecfdf5"),
    "other": ("#6b7280", "#f9fafb"),
}


def _escape(text: str) -> str:
    """Escapuje HTML znaky v textu."""
    return html.escape(str(text)) if text else ""


class EmailReporter:
    """Odesílá newsletter-style HTML email s AI souhrny a konkrétními články."""

    def __init__(self, config: dict):
        email_config = config.get("email", {})
        self.enabled: bool = email_config.get("enabled", False)
        self.smtp_server: str = email_config.get("smtp_server", "smtp.gmail.com")
        self.smtp_port: int = email_config.get("smtp_port", 587)
        self.sender: str = email_config.get("sender", "")
        self.app_password: str = email_config.get("app_password", "")
        self.recipients: list[str] = email_config.get("recipients", [])

    def send_report(
        self,
        clusters: list[dict],
        items: list,
        metadata: dict,
        newsletter_intro: str = "",
    ) -> bool:
        """Odešle HTML newsletter email.

        Args:
            clusters: Clustery obohacené o ai_summary a articles
            items: Původní FetchedItem seznam (pro články)
            metadata: Metadata běhu
            newsletter_intro: AI-generovaný úvodní odstavec
        """
        if not self.enabled:
            logger.info("Email report je vypnutý")
            return False

        if not self.sender or not self.app_password or not self.recipients:
            logger.error("Chybí email konfigurace (sender, app_password nebo recipients)")
            return False

        subject = f"Trending Topics {date.today().isoformat()} – Marketing, AI & Analytics"
        html_body = self._build_newsletter_html(clusters, items, metadata, newsletter_intro)
        text_body = self._build_newsletter_text(clusters, items, metadata, newsletter_intro)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.app_password)
                server.sendmail(self.sender, self.recipients, msg.as_string())

            logger.info("Newsletter email odeslán na: %s", ", ".join(self.recipients))
            return True

        except Exception as e:
            logger.error("Chyba při odesílání emailu: %s", e)
            return False

    def _build_newsletter_html(
        self,
        clusters: list[dict],
        items: list,
        metadata: dict,
        newsletter_intro: str,
    ) -> str:
        """Sestaví HTML newsletter s tematickými sekcemi."""
        scan_date = metadata.get("scan_date", date.today().isoformat())
        total_items = metadata.get("total_items", 0)
        sources = metadata.get("sources_used", [])

        # Úvodní odstavec
        intro_html = ""
        if newsletter_intro:
            intro_html = f"""
<div style="background:#f8fafc;border-left:4px solid #3b82f6;padding:16px 20px;margin-bottom:28px;border-radius:0 8px 8px 0;">
    <p style="margin:0;font-size:15px;line-height:1.6;color:#334155;">{_escape(newsletter_intro)}</p>
</div>"""

        # Tematické sekce
        sections_html = ""
        for i, cluster in enumerate(clusters[:12]):
            sections_html += self._build_topic_section(cluster, items, i)

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:680px;margin:0 auto;padding:20px;color:#1f2937;background:#ffffff;">

<div style="background:linear-gradient(135deg,#1e40af,#7c3aed);padding:28px 24px;border-radius:12px;color:white;margin-bottom:28px;">
    <h1 style="margin:0 0 6px;font-size:24px;font-weight:700;">Trending Topics</h1>
    <p style="margin:0;opacity:0.9;font-size:15px;">Marketing, AI & Analytics | {scan_date}</p>
    <p style="margin:10px 0 0;opacity:0.7;font-size:13px;">{total_items} zdrojových článků z {', '.join(sources)}</p>
</div>

{intro_html}

{sections_html}

<div style="margin-top:36px;padding:20px;background:#f9fafb;border-radius:8px;font-size:12px;color:#9ca3af;text-align:center;">
    <p style="margin:0;">Generováno nástrojem LinkedIn Topic Scanner</p>
    <p style="margin:4px 0 0;">Zdroje: Google News, Reddit, HackerNews, Google Trends</p>
</div>

</body>
</html>"""

    def _build_topic_section(self, cluster: dict, items: list, index: int) -> str:
        """Sestaví HTML sekci pro jedno téma."""
        label = cluster.get("label", "Téma")
        size = cluster.get("size", 0)
        ai_summary = cluster.get("ai_summary", {})

        # Určení barvy podle první nalezené kategorie
        color, bg_color = "#3b82f6", "#eff6ff"
        for cat_key, (c, bg) in _CAT_COLORS.items():
            # Heuristika: kontrola top_terms proti keywords
            top_terms_str = " ".join(cluster.get("top_terms", []))
            if cat_key == "ai_ml" and any(w in top_terms_str for w in ["ai", "llm", "ml", "generative"]):
                color, bg_color = c, bg
                break
            elif cat_key == "data_analytics" and any(w in top_terms_str for w in ["analytics", "data", "bigquery", "ga4"]):
                color, bg_color = c, bg
                break
            elif cat_key == "marketing_digital" and any(w in top_terms_str for w in ["marketing", "seo", "social", "advertising"]):
                color, bg_color = c, bg
                break

        # AI souhrn
        summary_text = ai_summary.get("summary", "")
        why_matters = ai_summary.get("why_it_matters", "")
        article_idea = ai_summary.get("article_idea", "")
        article_angle = ai_summary.get("article_angle", "")

        # Sestavení AI bloku
        ai_block = ""
        if summary_text:
            ai_block += f'<p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:#374151;">{_escape(summary_text)}</p>'
        if why_matters:
            ai_block += f'<p style="margin:0 0 10px;font-size:13px;line-height:1.5;color:#6b7280;"><strong style="color:#374151;">Proč je to důležité:</strong> {_escape(why_matters)}</p>'

        # Návrh článku
        article_block = ""
        if article_idea or article_angle:
            article_block = f"""
<div style="background:#fefce8;border:1px solid #fde68a;padding:12px 16px;border-radius:8px;margin:12px 0;">
    <p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#92400e;text-transform:uppercase;">Návrh na LinkedIn článek</p>
    {"<p style='margin:0 0 6px;font-size:14px;font-weight:600;color:#1f2937;'>" + _escape(article_idea) + "</p>" if article_idea else ""}
    {"<p style='margin:0;font-size:13px;color:#78716c;line-height:1.5;'>" + _escape(article_angle) + "</p>" if article_angle else ""}
</div>"""

        # Konkrétní články z clusteru
        articles_html = ""
        article_items = []
        for idx in cluster.get("item_indices", [])[:8]:
            if idx < len(items):
                item = items[idx]
                if item.title and item.url:
                    article_items.append(item)

        if article_items:
            articles_html = '<div style="margin-top:12px;">'
            for item in article_items[:6]:
                source_badge = f'<span style="font-size:11px;color:#9ca3af;">{_escape(item.source)}</span>'
                # Vyčistit description od HTML
                desc = re.sub(r"<[^>]+>", "", item.description or "")[:150]
                desc = html.unescape(desc).strip()

                articles_html += f"""
<div style="padding:8px 0;border-bottom:1px solid #f3f4f6;">
    <a href="{_escape(item.url)}" style="text-decoration:none;color:#1e40af;font-size:14px;font-weight:500;line-height:1.4;">{_escape(item.title)}</a>
    {"<p style='margin:4px 0 0;font-size:12px;color:#6b7280;line-height:1.4;'>" + _escape(desc) + "</p>" if desc else ""}
    <p style="margin:2px 0 0;">{source_badge}</p>
</div>"""
            articles_html += "</div>"

        return f"""
<div style="margin-bottom:28px;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
    <div style="background:{bg_color};padding:16px 20px;border-bottom:1px solid #e5e7eb;">
        <h2 style="margin:0;font-size:17px;color:{color};">{_escape(label.title())}</h2>
        <span style="font-size:12px;color:#9ca3af;">{size} článků</span>
    </div>
    <div style="padding:16px 20px;">
        {ai_block}
        {article_block}
        {articles_html}
    </div>
</div>"""

    def _build_newsletter_text(
        self,
        clusters: list[dict],
        items: list,
        metadata: dict,
        newsletter_intro: str,
    ) -> str:
        """Sestaví textovou verzi newsletteru (fallback)."""
        lines = [
            f"TRENDING TOPICS – {metadata.get('scan_date', date.today().isoformat())}",
            f"Marketing, AI & Analytics",
            f"{metadata.get('total_items', 0)} zdrojových článků",
            "=" * 60,
        ]

        if newsletter_intro:
            lines.extend(["", newsletter_intro, ""])

        for i, cluster in enumerate(clusters[:12], 1):
            label = cluster.get("label", "")
            ai_summary = cluster.get("ai_summary", {})

            lines.append(f"\n{'─' * 50}")
            lines.append(f"{i}. {label.upper()}")
            lines.append(f"   {cluster.get('size', 0)} článků")

            if ai_summary.get("summary"):
                lines.append(f"\n   {ai_summary['summary']}")
            if ai_summary.get("why_it_matters"):
                lines.append(f"\n   Proč je to důležité: {ai_summary['why_it_matters']}")
            if ai_summary.get("article_idea"):
                lines.append(f"\n   Návrh článku: {ai_summary['article_idea']}")
            if ai_summary.get("article_angle"):
                lines.append(f"   Úhel: {ai_summary['article_angle']}")

            # Články
            lines.append("")
            for idx in cluster.get("item_indices", [])[:5]:
                if idx < len(items):
                    item = items[idx]
                    if item.title:
                        lines.append(f"   - {item.title}")
                        if item.url:
                            lines.append(f"     {item.url}")

        return "\n".join(lines)
