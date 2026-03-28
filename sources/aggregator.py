"""Source aggregator: combines Polymarket, CoinGecko, and Yahoo Finance data with cross-source dedup."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from sources.polymarket_fetcher import fetch_polymarket
from sources.crypto_fetcher import fetch_crypto
from sources.macro_fetcher import fetch_macro, is_weekend
from sources.sentiment_fetcher import fetch_sentiment
from sources.calendar_fetcher import get_event_context_for_prompt

logger = logging.getLogger(__name__)


def fetch_all_sources():
    """Fetch from all financial sources in parallel. Returns combined, deduplicated article list.

    Each article has 'asset_id', 'asset_type', 'change_pct', and 'alert_level' fields.
    Articles are sorted by significance (alert level first, then abs change).
    """
    all_articles = []

    # Fetch from all sources in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}

        # Polymarket (always, 24/7)
        futures[executor.submit(fetch_polymarket)] = "polymarket"
        # Crypto (always, 24/7)
        futures[executor.submit(fetch_crypto)] = "crypto"
        # Sentiment / Fear & Greed (always, 24/7)
        futures[executor.submit(fetch_sentiment)] = "sentiment"
        # Macro (skip on weekends - no new data)
        if not is_weekend():
            futures[executor.submit(fetch_macro)] = "macro"

        for future in as_completed(futures):
            source_name = futures[future]
            try:
                articles = future.result()
                if articles:
                    all_articles.extend(articles)
                    logger.info(f"  {source_name}: {len(articles)} items")
            except Exception as e:
                logger.error(f"  Error from {source_name}: {e}")

    # Deduplicate and sort by significance
    deduped = _deduplicate(all_articles)
    sorted_articles = _sort_by_significance(deduped)

    logger.info(f"Aggregator: {len(sorted_articles)} total items after dedup")
    return sorted_articles


def _deduplicate(articles):
    """Deduplicate articles by asset_id within same source type.

    For financial data, we don't want multiple entries for the same asset
    from the same source in one fetch cycle.
    """
    seen = set()
    result = []

    for article in articles:
        key = (article.get("asset_type", ""), article.get("asset_id", ""))
        if key not in seen:
            seen.add(key)
            result.append(article)

    return result


def _sort_by_significance(articles):
    """Sort articles by significance: alerts first, then by absolute change percentage."""

    def sort_key(article):
        # Alert level: alert > normal
        alert_priority = 0 if article.get("alert_level") == "alert" else 1
        # Absolute change percentage (higher = more significant)
        change = abs(article.get("change_pct") or 0)
        return (alert_priority, -change)

    return sorted(articles, key=sort_key)


def format_financial_data_for_prompt(articles, max_items=10, narratives=None):
    """Format financial data articles into a text block for LLM prompt.

    Returns a string with structured data that the LLM can use to generate tweets.
    When narratives are provided, they appear first as prioritized cross-market patterns.
    """
    if not articles:
        return "No market data available."

    lines = []

    # Economic calendar context (upcoming FOMC, CPI, NFP, etc.)
    try:
        event_context = get_event_context_for_prompt()
        if event_context:
            lines.append(event_context)
    except Exception:
        pass  # Non-fatal if calendar fails

    # Narratives section (cross-market patterns from correlation engine)
    if narratives:
        lines.append("=== CROSS-MARKET NARRATIVES (PRIORITIZE THESE FOR TWEETS) ===")
        lines.append("")
        for i, narrative in enumerate(narratives, 1):
            strength_pct = int(narrative["strength"] * 100)
            lines.append(f"NARRATIVE {i}: {narrative['label']} (strength: {strength_pct}%)")
            # List the bundled data points
            for dp in narrative.get("data_points", []):
                source = dp.get("source", "Unknown")
                summary = dp.get("summary", "N/A")
                lines.append(f"  - [{source}] {summary}")
            lines.append(f"  Angle: {narrative['synthesis_hint']}")
            lines.append("")
        lines.append("=== INDIVIDUAL DATA POINTS (use if no narrative fits) ===")
        lines.append("")

    for i, article in enumerate(articles[:max_items], 1):
        source_tag = article.get("source", "Unknown")
        asset_type = article.get("asset_type", "")
        alert_tag = " [ALERT]" if article.get("alert_level") == "alert" else ""

        lines.append(f"--- Data Point {i} ({source_tag}){alert_tag} ---")
        lines.append(f"Title: {article['title']}")
        lines.append(f"Type: {asset_type}")
        lines.append(f"Summary: {article.get('summary', 'N/A')}")
        lines.append(f"URL: {article.get('url', 'N/A')}")
        lines.append("")

    return "\n".join(lines)
