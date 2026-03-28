"""Image fetcher: generates chart images for tweets using matplotlib."""

import os
import json
import logging
from datetime import datetime

import config
from images.chart_generator import generate_chart
from storage.database import get_market_data_history, get_chart_config

logger = logging.getLogger(__name__)


def should_attach_image(post_type):
    """Decide if this tweet type should get a chart image."""
    # Most financial tweets benefit from a chart
    # Polls and very short tweets don't need charts
    if post_type == "poll":
        return False
    return True


def find_image_for_post(post_content, source_urls_json=None, image_config=None,
                        exclude_urls=None, chart_hint=None, chart_data_json=None):
    """Generate a chart image for a tweet.

    Args:
        post_content: The tweet text (used to extract asset info if no hint)
        source_urls_json: Not used for charts (kept for API compat)
        image_config: Image config from DB
        exclude_urls: Not used for charts (kept for API compat)
        chart_hint: Parsed CHART_DATA hint from LLM (e.g., "line, Bitcoin, 7d")
        chart_data_json: Pre-built chart data dict

    Returns:
        (image_path, source_type) or (None, None)
    """
    chart_cfg = get_chart_config()

    # Try to build chart from hint
    chart_type, asset_name, timeframe = _parse_chart_hint(chart_hint)

    if not chart_type:
        chart_type = "line"  # Default

    # Try to get historical data for the chart
    chart_data = None

    if chart_data_json:
        try:
            chart_data = json.loads(chart_data_json) if isinstance(chart_data_json, str) else chart_data_json
        except (json.JSONDecodeError, TypeError):
            pass

    if not chart_data and asset_name:
        chart_data = _build_chart_data_from_db(chart_type, asset_name, timeframe)

    if not chart_data:
        # Try to extract asset from tweet content
        asset_name = _extract_asset_from_text(post_content)
        if asset_name:
            chart_data = _build_chart_data_from_db(chart_type, asset_name, "7d")

    if not chart_data:
        logger.info("No chart data available for this tweet")
        return None, None

    # Generate the chart
    title = _build_chart_title(asset_name, chart_type)
    output_path = _get_chart_path()

    result = generate_chart(chart_type, chart_data, title, output_path, chart_cfg)
    if result:
        return result, "chart"

    return None, None


def _parse_chart_hint(hint):
    """Parse a CHART_DATA hint string like 'line, Bitcoin, 7d'."""
    if not hint:
        return None, None, None

    parts = [p.strip() for p in hint.split(",")]
    chart_type = parts[0].lower() if len(parts) > 0 else "line"
    asset_name = parts[1] if len(parts) > 1 else None
    timeframe = parts[2] if len(parts) > 2 else "7d"

    # Normalize chart type
    valid_types = {"line", "bar", "odds", "pie", "comparison"}
    if chart_type not in valid_types:
        chart_type = "line"

    return chart_type, asset_name, timeframe


def _build_chart_data_from_db(chart_type, asset_name, timeframe):
    """Build chart data dict from market_data history."""
    days = _timeframe_to_days(timeframe)

    # Try to find the asset in market_data with flexible matching
    history = _find_market_history(asset_name, days)

    if not history or len(history) < 2:
        return None

    source = history[0].get("source", "")
    values = [row["value"] for row in history]
    labels = [row["fetched_at"][:16] if row.get("fetched_at") else "" for row in history]

    if chart_type == "odds":
        return {
            "yes_values": values,
            "no_values": [100 - v for v in values],
            "labels": labels,
        }
    elif chart_type == "bar":
        return {
            "names": [asset_name],
            "values": [history[-1].get("change_pct", 0) or 0],
            "is_percent": True,
            "xlabel": "Change %",
        }
    else:
        return {
            "values": values,
            "labels": labels,
            "label": "Price ($)" if source != "polymarket" else "Odds (%)",
        }


def _find_market_history(asset_name, days):
    """Search market_data with flexible matching: by asset_id, asset_name, or partial match."""
    from storage.database import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    search_term = asset_name.lower().strip()
    since = f"-{days} days"

    # 1. Exact asset_id match
    cursor.execute(
        """SELECT * FROM market_data WHERE LOWER(asset_id) = ?
           AND fetched_at >= datetime('now', ?) ORDER BY fetched_at ASC""",
        (search_term, since),
    )
    rows = cursor.fetchall()
    if rows and len(rows) >= 2:
        conn.close()
        return [dict(r) for r in rows]

    # 2. Partial asset_name match (e.g., "CC" matches "Canton (CC)")
    cursor.execute(
        """SELECT * FROM market_data WHERE LOWER(asset_name) LIKE ?
           AND fetched_at >= datetime('now', ?) ORDER BY fetched_at ASC""",
        (f"%{search_term}%", since),
    )
    rows = cursor.fetchall()
    if rows and len(rows) >= 2:
        conn.close()
        return [dict(r) for r in rows]

    # 3. Ticker symbol match in asset_name (e.g., "$BTC" -> "(BTC)")
    cursor.execute(
        """SELECT * FROM market_data WHERE LOWER(asset_name) LIKE ?
           AND fetched_at >= datetime('now', ?) ORDER BY fetched_at ASC""",
        (f"%({search_term.upper()})%", since),
    )
    rows = cursor.fetchall()
    if rows and len(rows) >= 2:
        conn.close()
        return [dict(r) for r in rows]

    conn.close()
    return None


def _extract_asset_from_text(text):
    """Try to extract an asset name/ticker from tweet text."""
    import re

    # Cashtags: $BTC, $ETH - return the ticker symbol directly (flexible matching handles the rest)
    match = re.search(r"\$([A-Z]{2,5})\b", text)
    if match:
        return match.group(1)

    # Index references
    if "s&p 500" in text.lower() or "s&p500" in text.lower():
        return "^GSPC"
    if "nasdaq" in text.lower():
        return "^IXIC"
    if "dow jones" in text.lower() or "dow" in text.lower():
        return "^DJI"
    if "vix" in text.lower():
        return "^VIX"

    return None


def _timeframe_to_days(timeframe):
    """Convert timeframe string to days."""
    if not timeframe:
        return 7
    timeframe = timeframe.lower().strip()
    if "1h" in timeframe or "1 hour" in timeframe:
        return 1
    elif "24h" in timeframe or "1d" in timeframe:
        return 1
    elif "7d" in timeframe or "1w" in timeframe or "week" in timeframe:
        return 7
    elif "30d" in timeframe or "1m" in timeframe or "month" in timeframe:
        return 30
    return 7


def _build_chart_title(asset_name, chart_type):
    """Build a chart title from asset name and type."""
    if not asset_name:
        return "Market Data"
    name = asset_name.replace("^", "").upper() if asset_name.startswith("^") else asset_name.title()
    type_labels = {
        "line": "Price History",
        "bar": "Change",
        "odds": "Odds History",
        "pie": "Market Share",
        "comparison": "Comparison",
    }
    return f"{name} - {type_labels.get(chart_type, 'Chart')}"


def _get_chart_path():
    """Generate a unique file path for a chart image."""
    image_dir = getattr(config, "IMAGE_DIR",
                        os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images"))
    os.makedirs(image_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(image_dir, f"chart_{timestamp}.png")


def download_image(image_url, post_id="0"):
    """Legacy compat: for chart images, the path is already local. Returns the path as-is."""
    if image_url and os.path.exists(image_url):
        return image_url
    return None
