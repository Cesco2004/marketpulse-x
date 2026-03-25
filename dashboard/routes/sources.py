from flask import Blueprint, render_template, request
from storage.database import (
    get_connection, get_rss_feeds, get_topic_categories,
    add_rss_feed, toggle_rss_feed, delete_rss_feed, update_rss_feed_weight,
)
import config

bp = Blueprint("sources", __name__)


def _get_source_stats():
    """Get per-source statistics from the database, using DB feeds."""
    feeds = get_rss_feeds()
    conn = get_connection()
    cursor = conn.cursor()

    sources = []
    for feed in feeds:
        name = feed["name"]

        cursor.execute("SELECT COUNT(*) FROM articles WHERE source = ?", (name,))
        article_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM articles WHERE source = ? AND stage = 'selected'", (name,))
        selected_count = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(keyword_score) FROM articles WHERE source = ?", (name,))
        avg_row = cursor.fetchone()[0]
        avg_score = avg_row if avg_row else 0

        cursor.execute("SELECT MAX(fetched_at) FROM articles WHERE source = ?", (name,))
        last_row = cursor.fetchone()[0]
        last_fetched = last_row[:10] if last_row else None

        sources.append({
            "id": feed["id"],
            "name": name,
            "url": feed["url"],
            "priority": feed["priority"],
            "category": feed.get("category", "other"),
            "description": feed.get("description", ""),
            "website": feed.get("website", ""),
            "is_enabled": feed.get("is_enabled", 1),
            "topic_weight": feed.get("topic_weight", 1.0),
            "article_count": article_count,
            "selected_count": selected_count,
            "avg_score": avg_score,
            "last_fetched": last_fetched,
        })

    conn.close()
    return sources


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

    # Group by category
    sources_by_cat = {}
    for src in sources:
        cat = src["category"]
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
    # Find source from DB feeds
    feeds = get_rss_feeds()
    source_config = None
    for feed in feeds:
        if feed["name"] == source_name:
            source_config = feed
            break

    # Fallback to legacy config
    if not source_config:
        for feed in config.RSS_FEEDS:
            if feed["name"] == source_name:
                source_config = feed
                break

    if not source_config:
        return f"Source '{source_name}' not found", 404

    cat = source_config.get("category", "other")
    categories = _get_categories_dict()
    source_info = categories.get(cat, {"label": cat, "icon": "", "color": "#9ca3af"})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM articles WHERE source = ? ORDER BY fetched_at DESC",
        (source_name,),
    )
    articles = cursor.fetchall()

    cursor.execute("SELECT AVG(keyword_score) FROM articles WHERE source = ?", (source_name,))
    avg_row = cursor.fetchone()[0]
    avg_score = avg_row if avg_row else 0

    conn.close()

    return render_template(
        "source_detail.html",
        source_name=source_name,
        source_config=source_config,
        source_info=source_info,
        articles=articles,
        avg_score=avg_score,
    )


# --- CRUD API ---

@bp.route("/api/sources/add", methods=["POST"])
def api_add_source():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    category = request.form.get("category", "industry_news")
    priority = int(request.form.get("priority", 2))

    if not name or not url:
        return '<div style="color:var(--qb-red);font-size:0.8rem;padding:0.3rem">Name and URL are required.</div>'

    feed_id = add_rss_feed(name, url, priority=priority, category=category)
    if feed_id is None:
        return '<div style="color:var(--qb-red);font-size:0.8rem;padding:0.3rem">Feed already exists (duplicate name or URL).</div>'

    return '<div style="color:var(--qb-green);font-size:0.8rem;padding:0.3rem">Feed added. Refresh to see it.</div>'


@bp.route("/api/sources/<int:feed_id>/toggle", methods=["POST"])
def api_toggle_source(feed_id):
    toggle_rss_feed(feed_id)
    feeds = get_rss_feeds()
    feed = next((f for f in feeds if f["id"] == feed_id), None)
    if feed:
        status = "enabled" if feed["is_enabled"] else "disabled"
        color = "var(--qb-green)" if feed["is_enabled"] else "var(--qb-red)"
        return f'<span style="color:{color};font-size:0.75rem;font-weight:600">{status}</span>'
    return ""


@bp.route("/api/sources/<int:feed_id>/delete", methods=["POST"])
def api_delete_source(feed_id):
    delete_rss_feed(feed_id)
    return ""
