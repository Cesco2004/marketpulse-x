"""Polymarket fetcher: fetch prediction market data via Gamma API."""

import logging
import requests
from datetime import datetime

from storage.database import save_market_data, create_market_alert

logger = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_URL = "https://polymarket.com"

# Alert threshold: odds shift > 8% triggers an alert
ODDS_SHIFT_ALERT_THRESHOLD = 8.0


def fetch_polymarket(limit=30):
    """Fetch top active markets from Polymarket Gamma API.

    Returns list of article-compatible dicts for the pipeline.
    """
    try:
        markets = _fetch_active_markets(limit=limit)
        if not markets:
            logger.warning("Polymarket: no markets returned")
            return []

        articles = []
        for market in markets:
            article = _process_market(market)
            if article:
                articles.append(article)

        logger.info(f"Polymarket: fetched {len(articles)} markets")
        return articles

    except Exception as e:
        logger.error(f"Polymarket fetch error: {e}")
        return []


def _fetch_active_markets(limit=30):
    """Fetch active markets sorted by volume."""
    try:
        resp = requests.get(
            f"{GAMMA_API_BASE}/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": limit,
                "order": "volume",
                "ascending": "false",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Polymarket API error: {e}")
        return []


def _process_market(market):
    """Process a single market into an article-compatible dict and save to DB."""
    try:
        question = market.get("question", "")
        condition_id = market.get("conditionId", market.get("id", ""))
        if not question or not condition_id:
            return None

        # Parse outcome prices
        outcome_prices = market.get("outcomePrices", [])
        if isinstance(outcome_prices, str):
            import json
            outcome_prices = json.loads(outcome_prices)

        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            import json
            outcomes = json.loads(outcomes)

        # Get Yes price (first outcome is typically "Yes")
        yes_price = float(outcome_prices[0]) * 100 if outcome_prices else None

        volume = float(market.get("volume", 0) or 0)
        liquidity = float(market.get("liquidity", 0) or 0)
        end_date = market.get("endDate", "")

        # Save to market_data and compute delta
        data_id = None
        change_pct = None
        if yes_price is not None:
            data_id, change_pct = save_market_data(
                source="polymarket",
                asset_id=str(condition_id),
                asset_name=question[:200],
                metric_type="odds",
                value=yes_price,
                extra_data={
                    "outcomes": outcomes,
                    "outcome_prices": [float(p) * 100 for p in outcome_prices] if outcome_prices else [],
                    "volume": volume,
                    "liquidity": liquidity,
                    "end_date": end_date,
                },
            )

        # Check for alert
        alert_level = "normal"
        if change_pct is not None and abs(change_pct) >= ODDS_SHIFT_ALERT_THRESHOLD:
            alert_level = "alert"
            direction = "up" if change_pct > 0 else "down"
            create_market_alert(
                source="polymarket",
                asset_id=str(condition_id),
                asset_name=question[:200],
                alert_type="odds_shift",
                magnitude=abs(change_pct),
                description=f'"{question}" shifted {direction} {abs(change_pct):.1f}pp to {yes_price:.0f}%',
                market_data_id=data_id,
            )

        # Format volume for display
        vol_str = _format_volume(volume)

        # Build summary
        prices_str = ""
        if outcomes and outcome_prices:
            prices_str = " / ".join(
                f"{o}: {float(p)*100:.0f}%" for o, p in zip(outcomes, outcome_prices)
            )

        change_str = ""
        if change_pct is not None:
            direction = "+" if change_pct > 0 else ""
            change_str = f" ({direction}{change_pct:.1f}pp)"

        summary = f"{prices_str}{change_str}. Volume: {vol_str}."

        # Build slug URL
        slug = market.get("slug", "")
        url = f"{POLYMARKET_URL}/event/{slug}" if slug else POLYMARKET_URL

        return {
            "title": question,
            "url": url,
            "source": "Polymarket",
            "summary": summary,
            "keyword_score": int(volume / 10000) if volume else 0,
            "matched_keywords": [],
            "asset_id": str(condition_id),
            "asset_type": "polymarket",
            "change_pct": change_pct,
            "alert_level": alert_level,
        }

    except Exception as e:
        logger.error(f"Polymarket process error: {e}")
        return None


def _format_volume(volume):
    """Format volume number for display."""
    if volume >= 1_000_000_000:
        return f"${volume / 1_000_000_000:.1f}B"
    elif volume >= 1_000_000:
        return f"${volume / 1_000_000:.1f}M"
    elif volume >= 1_000:
        return f"${volume / 1_000:.0f}K"
    else:
        return f"${volume:.0f}"
