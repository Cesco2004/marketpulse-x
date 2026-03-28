"""Sentiment fetcher: fetch Crypto Fear & Greed Index from alternative.me API."""

import logging
import requests

from storage.database import save_market_data

logger = logging.getLogger(__name__)

FNG_API_URL = "https://api.alternative.me/fng/"


def fetch_sentiment():
    """Fetch Crypto Fear & Greed Index.

    Returns list of article-compatible dicts for the pipeline.
    Free API, no auth required, JSON response.
    """
    try:
        resp = requests.get(FNG_API_URL, params={"limit": 2}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            logger.warning("Sentiment: no data returned from Fear & Greed API")
            return []

        current = data[0]
        value = int(current.get("value", 50))
        classification = current.get("value_classification", "Neutral")

        # Get previous day for delta
        prev_value = int(data[1]["value"]) if len(data) > 1 else None

        # Save to DB
        data_id, change_pct = save_market_data(
            source="alternative_me",
            asset_id="crypto_fear_greed",
            asset_name="Crypto Fear & Greed Index",
            metric_type="sentiment",
            value=value,
            extra_data={
                "classification": classification,
                "previous_value": prev_value,
            },
        )

        # Build summary
        change_str = ""
        if prev_value is not None:
            delta = value - prev_value
            change_str = f" ({delta:+d} from yesterday)"

        summary = f"Crypto Fear & Greed Index: {value}/100 ({classification}){change_str}."

        # Extreme readings are more interesting
        keyword_score = 20
        alert_level = "normal"
        if value <= 20 or value >= 80:
            keyword_score = 60
        elif value <= 30 or value >= 70:
            keyword_score = 40

        article = {
            "title": f"Crypto Fear & Greed: {classification} ({value})",
            "url": "https://alternative.me/crypto/fear-and-greed-index/",
            "source": "Alternative.me",
            "summary": summary,
            "keyword_score": keyword_score,
            "matched_keywords": ["fear", "greed", "sentiment"],
            "asset_id": "crypto_fear_greed",
            "asset_type": "sentiment",
            "change_pct": change_pct,
            "alert_level": alert_level,
        }

        logger.info(f"Sentiment: Fear & Greed at {value} ({classification})")
        return [article]

    except Exception as e:
        logger.error(f"Sentiment fetch error: {e}")
        return []
