"""Alert detector: checks market data for significant movements and creates alerts."""

import logging
from storage.database import (
    get_pending_alerts,
    expire_old_alerts,
    update_alert_status,
    get_alert_stats,
)

logger = logging.getLogger(__name__)

# Default thresholds (can be overridden)
ALERT_THRESHOLDS = {
    "polymarket_odds_shift": 8.0,   # >8% odds shift
    "crypto_price_move": 4.0,       # >4% price move
    "index_move": 2.0,              # >2% index move
    "vix_spike": 25.0,              # VIX above 25
}

# Max alert tweets per day
MAX_ALERT_TWEETS_PER_DAY = 3


def check_and_process_alerts():
    """Check for pending alerts and return those ready to tweet.

    Returns list of alert dicts, sorted by magnitude (biggest first).
    """
    # Expire old alerts first
    expired = expire_old_alerts()
    if expired:
        logger.info(f"Expired {expired} old alerts")

    # Get pending alerts
    alerts = get_pending_alerts()
    if not alerts:
        return []

    logger.info(f"Found {len(alerts)} pending alerts")
    return alerts


def dismiss_alert(alert_id, reason="manually dismissed"):
    """Dismiss an alert without tweeting it."""
    update_alert_status(alert_id, "dismissed")
    logger.info(f"Dismissed alert {alert_id}: {reason}")


def mark_alert_tweeted(alert_id, post_id=None):
    """Mark an alert as tweeted."""
    update_alert_status(alert_id, "tweeted", post_id=post_id)
    logger.info(f"Alert {alert_id} marked as tweeted (post_id={post_id})")


def get_alert_summary():
    """Get a summary of alert status for dashboard/CLI."""
    stats = get_alert_stats()
    pending = get_pending_alerts()

    return {
        "stats": stats,
        "pending_count": len(pending),
        "pending_alerts": pending,
        "thresholds": ALERT_THRESHOLDS,
        "max_per_day": MAX_ALERT_TWEETS_PER_DAY,
    }


def format_alerts_for_prompt(alerts, max_items=5):
    """Format pending alerts into text for LLM prompt."""
    if not alerts:
        return "No significant market alerts."

    lines = []
    for i, alert in enumerate(alerts[:max_items], 1):
        lines.append(f"--- ALERT {i} ---")
        lines.append(f"Source: {alert['source']}")
        lines.append(f"Asset: {alert['asset_name']}")
        lines.append(f"Type: {alert['alert_type']}")
        lines.append(f"Magnitude: {alert['magnitude']:.1f}")
        lines.append(f"Description: {alert.get('description', 'N/A')}")
        lines.append("")

    return "\n".join(lines)
