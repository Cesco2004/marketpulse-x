import json
from flask import Blueprint, render_template, request, make_response
from storage.database import (
    get_connection, get_content_sources, get_topic_categories,
    toggle_content_source, get_pending_alerts, get_alert_stats,
    update_alert_status, get_recent_narratives,
)
import config

bp = Blueprint("markets", __name__)


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

        cursor.execute(
            "SELECT COUNT(*) FROM market_data WHERE source = ?",
            (source_type,),
        )
        data_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT MAX(fetched_at) FROM market_data WHERE source = ?",
            (source_type,),
        )
        last_row = cursor.fetchone()[0]
        last_fetched = last_row[:19] if last_row else "Never"

        cursor.execute(
            "SELECT COUNT(*) FROM market_alerts WHERE source = ? AND status = 'pending'",
            (source_type,),
        )
        pending_alerts = cursor.fetchone()[0]

        result.append({
            "id": src["id"],
            "name": name,
            "source_type": source_type,
            "config_value": src["config_value"],
            "is_enabled": src.get("is_enabled", 1),
            "api_url": API_URLS.get(source_type, ""),
            "data_points": data_count,
            "last_fetched": last_fetched,
            "pending_alerts": pending_alerts,
        })

    conn.close()
    return result


def _get_categories_dict():
    cats = get_topic_categories()
    if cats:
        return {c["key"]: {"label": c["label"], "icon": c["icon"], "color": c["color"]} for c in cats}
    return config.SOURCE_CATEGORIES


# Pattern type display config
PATTERN_COLORS = {
    "risk_regime": {"color": "#f87171", "label": "Risk Regime"},
    "crypto_macro_divergence": {"color": "#fbbf24", "label": "Crypto-Macro Divergence"},
    "policy_to_price": {"color": "#60a5fa", "label": "Policy to Price"},
    "volatility_gap": {"color": "#a78bfa", "label": "Volatility Gap"},
    "dominance_rotation": {"color": "#34d399", "label": "Dominance Rotation"},
}


@bp.route("/markets")
def markets_page():
    alerts = get_pending_alerts()
    alert_stats = get_alert_stats()
    narratives = get_recent_narratives(hours=24)
    sources = _get_source_stats()
    categories = _get_categories_dict()

    # Group sources by type
    sources_by_cat = {}
    for src in sources:
        cat = src["source_type"]
        if cat not in sources_by_cat:
            sources_by_cat[cat] = []
        sources_by_cat[cat].append(src)

    # Enrich narratives with display info
    for n in narratives:
        ptype = n.get("pattern_type", "")
        info = PATTERN_COLORS.get(ptype, {"color": "#9ca3af", "label": ptype})
        n["display_color"] = info["color"]
        n["display_label"] = info["label"]
        try:
            n["data_points_list"] = json.loads(n.get("data_points_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            n["data_points_list"] = []

    return render_template(
        "markets.html",
        alerts=alerts,
        alert_stats=alert_stats,
        narratives=narratives,
        categories=categories,
        sources_by_cat=sources_by_cat,
        pattern_colors=PATTERN_COLORS,
    )


# --- HTMX Endpoints ---

@bp.route("/api/markets/alerts", methods=["GET"])
def alerts_fragment():
    alerts = get_pending_alerts()
    if not alerts:
        return '<div style="color:var(--text-secondary);padding:1rem;text-align:center">No pending alerts.</div>'

    html_parts = []
    for a in alerts:
        mag_color = "var(--qb-red)" if a["magnitude"] >= 5 else ("var(--qb-yellow)" if a["magnitude"] >= 3 else "var(--qb-accent-soft)")
        html_parts.append(f'''
        <div class="post-card" id="alert-{a['id']}" style="border-left:3px solid {mag_color};padding:0.6rem 0.8rem">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <span style="font-weight:700">{a['asset_name']}</span>
                    <span class="badge" style="margin-left:0.4rem;background:{mag_color}22;color:{mag_color}">{a['alert_type']}</span>
                    <span style="font-size:0.82rem;color:{mag_color};font-weight:600;margin-left:0.4rem">{a['magnitude']:+.1f}%</span>
                </div>
                <div style="display:flex;gap:0.3rem">
                    <button class="outline secondary" style="padding:0.2rem 0.5rem;font-size:0.7rem"
                            hx-post="/api/markets/alerts/{a['id']}/dismiss"
                            hx-target="#alert-{a['id']}"
                            hx-swap="outerHTML">Dismiss</button>
                </div>
            </div>
            <div style="font-size:0.72rem;color:var(--qb-dim);margin-top:0.2rem">{a.get('description', '') or a['source']} &middot; {a['detected_at'][:16]}</div>
        </div>
        ''')
    return "".join(html_parts)


@bp.route("/api/markets/alerts/<int:alert_id>/dismiss", methods=["POST"])
def dismiss_alert(alert_id):
    update_alert_status(alert_id, "dismissed")
    return '<div style="opacity:0.4;padding:0.4rem 0.8rem;font-size:0.75rem;color:var(--text-secondary)">Dismissed</div>'


@bp.route("/api/markets/narratives", methods=["GET"])
def narratives_fragment():
    narratives = get_recent_narratives(hours=24)
    if not narratives:
        return '<div style="color:var(--text-secondary);padding:1rem;text-align:center">No narratives detected in the last 24h. Run a fetch cycle.</div>'

    html_parts = []
    for n in narratives:
        ptype = n.get("pattern_type", "")
        info = PATTERN_COLORS.get(ptype, {"color": "#9ca3af", "label": ptype})
        color = info["color"]
        strength = n.get("strength", 0)
        strength_pct = int(strength * 100)

        try:
            data_points = json.loads(n.get("data_points_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            data_points = []

        dp_html = ""
        if data_points:
            dp_items = "".join(f'<span class="penalty-tag" style="background:{color}15;color:{color};border-color:{color}33">{dp}</span>' for dp in data_points[:5])
            dp_html = f'<div style="display:flex;flex-wrap:wrap;gap:0.2rem;margin-top:0.3rem">{dp_items}</div>'

        html_parts.append(f'''
        <div class="post-card" style="border-left:3px solid {color};padding:0.6rem 0.8rem">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <span class="badge" style="background:{color}22;color:{color}">{info["label"]}</span>
                    <span style="font-weight:600;margin-left:0.4rem">{n.get("label", "")}</span>
                </div>
                <div style="display:flex;align-items:center;gap:0.4rem">
                    <div style="width:60px;height:4px;background:var(--bg-tertiary);border-radius:2px;overflow:hidden">
                        <div style="height:100%;width:{strength_pct}%;background:{color};border-radius:2px"></div>
                    </div>
                    <span style="font-size:0.72rem;color:{color};font-weight:600">{strength_pct}%</span>
                </div>
            </div>
            {f'<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.3rem">{n.get("synthesis_hint", "")}</div>' if n.get("synthesis_hint") else ""}
            {dp_html}
            <div style="font-size:0.65rem;color:var(--qb-dim);margin-top:0.3rem">Batch: {n.get("batch_id", "?")} &middot; {n["detected_at"][:16]}</div>
        </div>
        ''')
    return "".join(html_parts)


# Source toggle (reused from old sources route)
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
