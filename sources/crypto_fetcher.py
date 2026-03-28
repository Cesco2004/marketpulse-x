"""Crypto fetcher: fetch cryptocurrency data via CoinGecko free API."""

import logging
import os
import requests

from storage.database import save_market_data, create_market_alert

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Alert threshold: price move > 4% triggers an alert
PRICE_MOVE_ALERT_THRESHOLD = 4.0


def _get_headers():
    """Build request headers with optional API key."""
    headers = {"Accept": "application/json"}
    api_key = os.getenv("COINGECKO_API_KEY", "")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    return headers


def fetch_crypto(top_n=20):
    """Fetch top crypto coins + global data + trending.

    Returns list of article-compatible dicts for the pipeline.
    """
    articles = []

    # Fetch top coins by market cap
    top_coins = _fetch_top_coins(top_n)
    for coin in top_coins:
        article = _process_coin(coin)
        if article:
            articles.append(article)

    # Fetch global market data (BTC/ETH dominance)
    global_data = _fetch_global()
    if global_data:
        articles.append(global_data)

    # Fetch trending coins
    trending = _fetch_trending()
    for coin in trending:
        article = _process_trending_coin(coin)
        if article:
            articles.append(article)

    logger.info(f"CoinGecko: fetched {len(articles)} crypto data points")
    return articles


def _fetch_top_coins(per_page=20):
    """Fetch top coins by market cap."""
    try:
        resp = requests.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d",
            },
            headers=_get_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"CoinGecko markets error: {e}")
        return []


def _fetch_global():
    """Fetch global crypto market data (dominance, total market cap)."""
    try:
        resp = requests.get(
            f"{COINGECKO_BASE}/global",
            headers=_get_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        total_mcap = data.get("total_market_cap", {}).get("usd", 0)
        btc_dom = data.get("market_cap_percentage", {}).get("btc", 0)
        eth_dom = data.get("market_cap_percentage", {}).get("eth", 0)
        mcap_change_24h = data.get("market_cap_change_percentage_24h_usd", 0)

        # Save to DB
        save_market_data("coingecko", "global_btc_dom", "BTC Dominance", "dominance", btc_dom)
        save_market_data("coingecko", "global_eth_dom", "ETH Dominance", "dominance", eth_dom)
        save_market_data("coingecko", "global_total_mcap", "Total Crypto Market Cap", "market_cap", total_mcap)

        mcap_str = _format_usd(total_mcap)
        summary = (
            f"Total crypto market cap: {mcap_str} ({mcap_change_24h:+.1f}% 24h). "
            f"BTC dominance: {btc_dom:.1f}%. ETH dominance: {eth_dom:.1f}%."
        )

        return {
            "title": "Crypto Market Global Overview",
            "url": "https://www.coingecko.com/en/global-charts",
            "source": "CoinGecko",
            "summary": summary,
            "keyword_score": 50,
            "matched_keywords": ["BTC", "ETH", "dominance"],
            "asset_id": "global",
            "asset_type": "crypto",
            "change_pct": mcap_change_24h,
            "alert_level": "normal",
        }

    except requests.RequestException as e:
        logger.error(f"CoinGecko global error: {e}")
        return None


def _fetch_trending():
    """Fetch trending coins."""
    try:
        resp = requests.get(
            f"{COINGECKO_BASE}/search/trending",
            headers=_get_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        coins = resp.json().get("coins", [])
        return coins[:5]  # Top 5 trending
    except requests.RequestException as e:
        logger.error(f"CoinGecko trending error: {e}")
        return []


def _process_coin(coin):
    """Process a single coin from /coins/markets into an article-compatible dict."""
    try:
        coin_id = coin.get("id", "")
        name = coin.get("name", "")
        symbol = coin.get("symbol", "").upper()
        price = coin.get("current_price", 0)
        mcap = coin.get("market_cap", 0)
        volume_24h = coin.get("total_volume", 0)
        change_24h = coin.get("price_change_percentage_24h", 0) or 0
        change_1h = coin.get("price_change_percentage_1h_in_currency", 0) or 0
        change_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
        ath = coin.get("ath", 0)
        ath_change = coin.get("ath_change_percentage", 0)

        if not coin_id or not price:
            return None

        # Save to DB
        data_id, db_change = save_market_data(
            source="coingecko",
            asset_id=coin_id,
            asset_name=f"{name} ({symbol})",
            metric_type="price",
            value=price,
            extra_data={
                "symbol": symbol,
                "market_cap": mcap,
                "volume_24h": volume_24h,
                "change_1h": change_1h,
                "change_24h": change_24h,
                "change_7d": change_7d,
                "ath": ath,
                "ath_change_pct": ath_change,
            },
        )

        # Check for alert (using 24h change from API, more reliable than our delta)
        alert_level = "normal"
        if abs(change_24h) >= PRICE_MOVE_ALERT_THRESHOLD:
            alert_level = "alert"
            direction = "up" if change_24h > 0 else "down"
            create_market_alert(
                source="coingecko",
                asset_id=coin_id,
                asset_name=f"{name} ({symbol})",
                alert_type="price_spike" if change_24h > 0 else "price_drop",
                magnitude=abs(change_24h),
                description=f"${symbol} {direction} {abs(change_24h):.1f}% to {_format_price(price)} in 24h",
                market_data_id=data_id,
            )

        # Build summary
        price_str = _format_price(price)
        mcap_str = _format_usd(mcap)
        vol_str = _format_usd(volume_24h)

        summary = (
            f"${symbol} at {price_str} ({change_24h:+.1f}% 24h). "
            f"Market cap: {mcap_str}. 24h volume: {vol_str}."
        )
        if change_7d:
            summary += f" 7d: {change_7d:+.1f}%."

        return {
            "title": f"{name} (${symbol}) Price Update",
            "url": f"https://www.coingecko.com/en/coins/{coin_id}",
            "source": "CoinGecko",
            "summary": summary,
            "keyword_score": int(abs(change_24h) * 10),
            "matched_keywords": [symbol, name],
            "asset_id": coin_id,
            "asset_type": "crypto",
            "change_pct": change_24h,
            "alert_level": alert_level,
        }

    except Exception as e:
        logger.error(f"CoinGecko process coin error: {e}")
        return None


def _process_trending_coin(item):
    """Process a trending coin entry."""
    try:
        coin = item.get("item", {})
        coin_id = coin.get("id", "")
        name = coin.get("name", "")
        symbol = coin.get("symbol", "").upper()
        market_cap_rank = coin.get("market_cap_rank", "N/A")
        price_btc = coin.get("price_btc", 0)

        if not coin_id:
            return None

        summary = f"${symbol} trending on CoinGecko. Market cap rank: #{market_cap_rank}."

        return {
            "title": f"{name} (${symbol}) Trending",
            "url": f"https://www.coingecko.com/en/coins/{coin_id}",
            "source": "CoinGecko Trending",
            "summary": summary,
            "keyword_score": 30,
            "matched_keywords": [symbol, name, "trending"],
            "asset_id": coin_id,
            "asset_type": "crypto",
            "change_pct": None,
            "alert_level": "normal",
        }

    except Exception as e:
        logger.error(f"CoinGecko trending process error: {e}")
        return None


def _format_price(price):
    """Format a price for display."""
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:,.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


def _format_usd(amount):
    """Format a USD amount for display."""
    if amount >= 1_000_000_000_000:
        return f"${amount / 1_000_000_000_000:.2f}T"
    elif amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    elif amount >= 1_000_000:
        return f"${amount / 1_000_000:.0f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    else:
        return f"${amount:.0f}"
