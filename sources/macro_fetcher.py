"""Macro fetcher: fetch S&P 500, indices, and macro data via yfinance."""

import logging
from datetime import datetime, timezone

from storage.database import save_market_data, create_market_alert

logger = logging.getLogger(__name__)

# Alert threshold: index move > 2% triggers an alert
INDEX_MOVE_ALERT_THRESHOLD = 2.0
# VIX spike threshold
VIX_SPIKE_THRESHOLD = 25.0

# Tickers to track
DEFAULT_TICKERS = {
    "^GSPC": {"name": "S&P 500", "type": "index"},
    "^IXIC": {"name": "NASDAQ Composite", "type": "index"},
    "^DJI": {"name": "Dow Jones", "type": "index"},
    "^VIX": {"name": "VIX (Volatility Index)", "type": "volatility"},
    "^TNX": {"name": "10Y Treasury Yield", "type": "yield"},
}


def fetch_macro():
    """Fetch macro/indices data via yfinance.

    Returns list of article-compatible dicts for the pipeline.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        return []

    articles = []
    market_open = is_market_open()

    for ticker_symbol, info in DEFAULT_TICKERS.items():
        article = _fetch_ticker(yf, ticker_symbol, info, market_open)
        if article:
            articles.append(article)

    logger.info(f"Macro: fetched {len(articles)} indices/macro data points (market {'open' if market_open else 'closed'})")
    return articles


def _fetch_ticker(yf, ticker_symbol, info, market_open):
    """Fetch a single ticker and return article-compatible dict."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="5d")

        if hist.empty:
            logger.warning(f"Macro: no data for {ticker_symbol}")
            return None

        # Get current/latest price
        current_price = float(hist["Close"].iloc[-1])

        # Get previous close for daily change
        if len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
            daily_change = ((current_price - prev_close) / prev_close) * 100
        else:
            prev_close = current_price
            daily_change = 0

        # Get week change
        if len(hist) >= 5:
            week_ago_price = float(hist["Close"].iloc[0])
            weekly_change = ((current_price - week_ago_price) / week_ago_price) * 100
        else:
            weekly_change = None

        # Save to DB
        data_id, db_change = save_market_data(
            source="yahoo_finance",
            asset_id=ticker_symbol,
            asset_name=info["name"],
            metric_type="price" if info["type"] == "index" else info["type"],
            value=current_price,
            extra_data={
                "previous_close": prev_close,
                "daily_change_pct": daily_change,
                "weekly_change_pct": weekly_change,
                "market_open": market_open,
                "ticker_type": info["type"],
            },
        )

        # Check for alerts
        alert_level = "normal"

        # Index move alert
        if info["type"] == "index" and abs(daily_change) >= INDEX_MOVE_ALERT_THRESHOLD:
            alert_level = "alert"
            direction = "up" if daily_change > 0 else "down"
            create_market_alert(
                source="yahoo_finance",
                asset_id=ticker_symbol,
                asset_name=info["name"],
                alert_type="price_spike" if daily_change > 0 else "price_drop",
                magnitude=abs(daily_change),
                description=f"{info['name']} {direction} {abs(daily_change):.1f}% to {_format_index(current_price)}",
                market_data_id=data_id,
            )

        # VIX spike alert
        if ticker_symbol == "^VIX" and current_price >= VIX_SPIKE_THRESHOLD:
            alert_level = "alert"
            create_market_alert(
                source="yahoo_finance",
                asset_id=ticker_symbol,
                asset_name="VIX",
                alert_type="volume_spike",
                magnitude=current_price,
                description=f"VIX at {current_price:.1f}, above {VIX_SPIKE_THRESHOLD} threshold",
                market_data_id=data_id,
            )

        # Build summary
        price_str = _format_index(current_price)
        market_status = "live" if market_open else "close"

        summary = f"{info['name']} at {price_str} ({daily_change:+.1f}% today, {market_status})."
        if weekly_change is not None:
            summary += f" Weekly: {weekly_change:+.1f}%."

        if ticker_symbol == "^VIX":
            summary = f"VIX at {current_price:.1f} ({daily_change:+.1f}% today)."
            if current_price >= VIX_SPIKE_THRESHOLD:
                summary += " Elevated volatility."
        elif ticker_symbol == "^TNX":
            summary = f"10Y Treasury yield at {current_price:.2f}% ({daily_change:+.2f}pp today)."

        return {
            "title": f"{info['name']} Market Update",
            "url": f"https://finance.yahoo.com/quote/{ticker_symbol.replace('^', '%5E')}",
            "source": "Yahoo Finance",
            "summary": summary,
            "keyword_score": int(abs(daily_change) * 20),
            "matched_keywords": [info["name"], ticker_symbol],
            "asset_id": ticker_symbol,
            "asset_type": "macro",
            "change_pct": daily_change,
            "alert_level": alert_level,
        }

    except Exception as e:
        logger.error(f"Macro fetch error for {ticker_symbol}: {e}")
        return None


def is_market_open():
    """Check if US stock market is currently open (M-F, 9:30-16:00 ET)."""
    try:
        from datetime import time as dt_time
        import pytz

        et = pytz.timezone("US/Eastern")
        now_et = datetime.now(et)

        # Weekend check
        if now_et.weekday() >= 5:
            return False

        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)

        return market_open <= now_et.time() <= market_close

    except Exception:
        # Fallback: UTC-based approximation (14:30 - 21:00 UTC)
        now_utc = datetime.now(timezone.utc)
        if now_utc.weekday() >= 5:
            return False
        from datetime import time as dt_time
        return dt_time(14, 30) <= now_utc.time() <= dt_time(21, 0)


def is_weekend():
    """Check if it's a weekend (no US market data)."""
    now_utc = datetime.now(timezone.utc)
    return now_utc.weekday() >= 5


def _format_index(value):
    """Format an index value for display."""
    if value >= 1000:
        return f"{value:,.0f}"
    elif value >= 100:
        return f"{value:,.1f}"
    else:
        return f"{value:.2f}"
