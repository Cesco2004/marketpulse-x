import json

from flask import Blueprint, render_template, request

from storage.database import (
    get_analytics_config,
    update_analytics_config,
    get_analytics_summary,
    get_latest_tweet_metrics,
    get_engagement_by_post_type,
    get_engagement_heatmap_data,
    get_follower_history,
    get_engagement_over_time,
    get_top_tweets,
    get_flop_tweets,
    get_quality_vs_engagement,
)

bp = Blueprint("analytics", __name__)


@bp.route("/analytics")
def analytics_page():
    period = request.args.get("period", "30")
    days = int(period) if period.isdigit() else 30

    summary = get_analytics_summary()
    tweets = get_latest_tweet_metrics()
    by_type = get_engagement_by_post_type()
    heatmap = get_engagement_heatmap_data()
    followers = get_follower_history(days=days)
    engagement_trend = get_engagement_over_time(days=days)
    top = get_top_tweets(limit=5)
    flop = get_flop_tweets(limit=5)
    quality_corr = get_quality_vs_engagement()
    config = get_analytics_config()

    # Check collector status
    try:
        from analytics.collector import metrics_collector
        collector_running = metrics_collector.is_running
        collector_stats = metrics_collector.stats
    except Exception:
        collector_running = False
        collector_stats = {}

    return render_template(
        "analytics.html",
        summary=summary,
        tweets=tweets,
        by_type_json=json.dumps(by_type, default=str),
        heatmap_json=json.dumps(heatmap, default=str),
        followers_json=json.dumps(followers, default=str),
        engagement_trend_json=json.dumps(engagement_trend, default=str),
        quality_corr_json=json.dumps(quality_corr, default=str),
        top_tweets=top,
        flop_tweets=flop,
        config=config,
        period=period,
        collector_running=collector_running,
        collector_stats=collector_stats,
    )


@bp.route("/api/analytics/config", methods=["POST"])
def save_config():
    update_analytics_config(
        collection_interval_hours=int(request.form.get("collection_interval_hours", 12)),
        lookback_days=int(request.form.get("lookback_days", 30)),
        own_username=request.form.get("own_username", "").strip().lstrip("@"),
    )
    return '<span class="save-ok">Saved</span>'


@bp.route("/api/analytics/collector/toggle", methods=["POST"])
def toggle_collector():
    from analytics.collector import metrics_collector
    if metrics_collector.is_running:
        metrics_collector.stop()
        label = "Start Collector"
        color = "var(--text-tertiary)"
        status = "OFF"
    else:
        metrics_collector.start()
        label = "Stop Collector"
        color = "var(--green)"
        status = "ON"
    return (
        f'<button class="btn-toggle" hx-post="/api/analytics/collector/toggle" hx-target="#collector-toggle" hx-swap="innerHTML">'
        f'{label}</button>'
        f'<span style="font-size:0.7rem;font-weight:600;color:{color};margin-left:0.5rem">{status}</span>'
    )


@bp.route("/api/analytics/collect-now", methods=["POST"])
def collect_now():
    from analytics.collector import metrics_collector
    result = metrics_collector.collect_once()
    scraped = result.get("tweets_scraped", 0)
    errors = result.get("errors", 0)
    return f'<span style="font-size:0.75rem;color:var(--green)">Done: {scraped} tweets scraped, {errors} errors</span>'
