from flask import Blueprint, render_template, request
from storage.database import (
    get_connection, get_content_sources, get_topic_categories,
    toggle_content_source,
)
import config

bp = Blueprint("sources", __name__)


# API base URLs for display
API_URLS = {
    "polymarket": "https://gamma-api.polymarket.com",
    "coingecko": "https://api.coingecko.com/api/v3",
    "yahoo_finance": "via yfinance (Yahoo Finance)",
}


def _get_source_stats():
    """Get per-source statistics from market_data table."""
    sources = get_content_sources()
    conn = get_connection()
    cursor = conn.cursor()

    result = []
    for src in sources:
        source_type = src["source_type"]
        name = src["name"]

        # Count market data points for this source type
        cursor.execute(
            "SELECT COUNT(*) FROM market_data WHERE source = ?",
            (source_type,),
        )
        data_count = cursor.fetchone()[0]

        # Last fetch time
        cursor.execute(
            "SELECT MAX(fetched_at) FROM market_data WHERE source = ?",
            (source_type,),
        )
        last_row = cursor.fetchone()[0]
        last_fetched = last_row[:19] if last_row else "Never"

        # Count alerts from this source
        cursor.execute(
            "SELECT COUNT(*) FROM market_alerts WHERE source = ? AND status = 'pending'",
            (source_type,),
        )
        pending_alerts = cursor.fetchone()[0]

        # Count articles from this source name
        cursor.execute(
            "SELECT COUNT(*) FROM articles WHERE source = ?",
            (name if source_type != "coingecko" else "CoinGecko",),
        )
        article_count = cursor.fetchone()[0]

        result.append({
            "id": src["id"],
            "name": name,
            "source_type": source_type,
            "config_value": src["config_value"],
            "is_enabled": src.get("is_enabled", 1),
            "api_url": API_URLS.get(source_type, ""),
            "data_points": data_count,
            "article_count": article_count,
            "last_fetched": last_fetched,
            "pending_alerts": pending_alerts,
        })

    conn.close()
    return result


def _get_categories_dict():
    """Build categories dict from DB, falling back to config."""
    cats = get_topic_categories()
    if cats:
        return {c["key"]: {"label": c["label"], "icon": c["icon"], "color": c["color"]} for c in cats}
    return config.SOURCE_CATEGORIES


@bp.route("/sources")
def sources_page():
    sources = _get_source_stats()
    categories = _get_categories_dict()

    # Group by source_type
    sources_by_cat = {}
    for src in sources:
        cat = src["source_type"]
        if cat not in sources_by_cat:
            sources_by_cat[cat] = []
        sources_by_cat[cat].append(src)

    return render_template(
        "sources.html",
        categories=categories,
        sources_by_cat=sources_by_cat,
    )


@bp.route("/sources/<source_name>")
def source_detail(source_name):
    """Show details for a specific source."""
    sources = get_content_sources()
    source_config = None
    for src in sources:
        if src["name"] == source_name:
            source_config = src
            break

    if not source_config:
        return f"Source '{source_name}' not found", 404

    cat = source_config.get("source_type", "other")
    categories = _get_categories_dict()
    source_info = categories.get(cat, {"label": cat, "icon": "", "color": "#9ca3af"})

    # Get recent market data for this source
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM market_data WHERE source = ? ORDER BY fetched_at DESC LIMIT 50",
        (cat,),
    )
    data_points = cursor.fetchall()

    # Get articles for this source
    source_label = source_config["name"]
    cursor.execute(
        "SELECT * FROM articles WHERE source LIKE ? ORDER BY fetched_at DESC LIMIT 30",
        (f"%{source_label.split()[0]}%",),
    )
    articles = cursor.fetchall()

    conn.close()

    return render_template(
        "source_detail.html",
        source_name=source_name,
        source_config=source_config,
        source_info=source_info,
        articles=articles,
        avg_score=0,
    )


# --- API ---

@bp.route("/api/sources/<int:source_id>/toggle", methods=["POST"])
def api_toggle_source(source_id):
    toggle_content_source(source_id)
    sources = get_content_sources()
    src = next((s for s in sources if s["id"] == source_id), None)
    if src:
        status = "enabled" if src["is_enabled"] else "disabled"
        color = "var(--qb-green)" if src["is_enabled"] else "var(--qb-red)"
        return f'<span style="color:{color};font-size:0.75rem;font-weight:600">{status}</span>'
    return ""
