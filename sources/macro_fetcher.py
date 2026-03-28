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
    # US indices
    "^GSPC": {"name": "S&P 500", "type": "index"},
    "^IXIC": {"name": "NASDAQ Composite", "type": "index"},
    "^DJI": {"name": "Dow Jones", "type": "index"},
    # Volatility
    "^VIX": {"name": "VIX (Volatility Index)", "type": "volatility"},
    # Yields (multiple maturities for yield curve analysis)
    "^IRX": {"name": "3-Month T-Bill Yield", "type": "yield"},
    "^FVX": {"name": "5Y Treasury Yield", "type": "yield"},
    "^TNX": {"name": "10Y Treasury Yield", "type": "yield"},
    "^TYX": {"name": "30Y Treasury Yield", "type": "yield"},
    # Currency
    "DX-Y.NYB": {"name": "US Dollar Index (DXY)", "type": "currency"},
    # Commodities
    "GC=F": {"name": "Gold Futures", "type": "commodity"},
    "CL=F": {"name": "Crude Oil (WTI)", "type": "commodity"},
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

    # Compute yield curve spread (10Y - 3M) as a derived metric
    yield_spread_article = _compute_yield_spread(articles)
    if yield_spread_article:
        articles.append(yield_spread_article)

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

        # Commodity/currency alert (reuse index threshold)
        if info["type"] in ("commodity", "currency") and abs(daily_change) >= INDEX_MOVE_ALERT_THRESHOLD:
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

        # Build summary
        price_str = _format_index(current_price)
        market_status = "live" if market_open else "close"

        summary = f"{info['name']} at {price_str} ({daily_change:+.1f}% today, {market_status})."
        if weekly_change is not None:
            summary += f" Weekly: {weekly_change:+.1f}%."

        # Type-specific summary overrides
        if ticker_symbol == "^VIX":
            summary = f"VIX at {current_price:.1f} ({daily_change:+.1f}% today)."
            if current_price >= VIX_SPIKE_THRESHOLD:
                summary += " Elevated volatility."
        elif info["type"] == "yield":
            summary = f"{info['name']} at {current_price:.2f}% ({daily_change:+.2f}pp today)."
        elif info["type"] == "commodity":
            summary = f"{info['name']} at ${current_price:,.2f} ({daily_change:+.1f}% today)."
            if weekly_change is not None:
                summary += f" Weekly: {weekly_change:+.1f}%."
        elif info["type"] == "currency":
            summary = f"{info['name']} at {current_price:.2f} ({daily_change:+.1f}% today)."
            if weekly_change is not None:
                summary += f" Weekly: {weekly_change:+.1f}%."

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


def _compute_yield_spread(articles):
    """Compute 10Y-3M yield curve spread from fetched articles.

    An inverted yield curve (negative spread) is a strong recession signal.
    """
    tnx_val = None
    irx_val = None

    for a in articles:
        if a.get("asset_id") == "^TNX":
            # TNX is stored as the yield value in summary
            try:
                import re
                match = re.search(r"at ([\d.]+)%", a.get("summary", ""))
                if match:
                    tnx_val = float(match.group(1))
            except (ValueError, AttributeError):
                pass
        elif a.get("asset_id") == "^IRX":
            try:
                import re
                match = re.search(r"at ([\d.]+)", a.get("summary", ""))
                if match:
                    irx_val = float(match.group(1))
            except (ValueError, AttributeError):
                pass

    if tnx_val is None or irx_val is None:
        return None

    spread = tnx_val - irx_val

    # Save to DB
    data_id, db_change = save_market_data(
        source="yahoo_finance",
        asset_id="yield_spread_10y_3m",
        asset_name="10Y-3M Yield Spread",
        metric_type="spread",
        value=spread,
        extra_data={
            "tnx": tnx_val,
            "irx": irx_val,
            "inverted": spread < 0,
        },
    )

    # Alert on yield curve inversion
    alert_level = "normal"
    if spread < 0:
        alert_level = "alert"
        create_market_alert(
            source="yahoo_finance",
            asset_id="yield_spread_10y_3m",
            asset_name="Yield Curve",
            alert_type="yield_curve_inversion",
            magnitude=abs(spread),
            description=f"Yield curve inverted: 10Y ({tnx_val:.2f}%) below 3M ({irx_val:.2f}%). Spread: {spread:.2f}pp.",
            market_data_id=data_id,
        )

    status = "INVERTED" if spread < 0 else "normal"
    summary = f"10Y-3M yield spread: {spread:+.2f}pp ({status}). 10Y: {tnx_val:.2f}%, 3M: {irx_val:.2f}%."

    return {
        "title": "Yield Curve Spread (10Y-3M)",
        "url": "https://finance.yahoo.com/quote/%5ETNX",
        "source": "Yahoo Finance",
        "summary": summary,
        "keyword_score": int(abs(spread) * 30) if spread < 0 else 10,
        "matched_keywords": ["yield curve", "treasury"],
        "asset_id": "yield_spread_10y_3m",
        "asset_type": "macro",
        "change_pct": db_change,
        "alert_level": alert_level,
    }


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
