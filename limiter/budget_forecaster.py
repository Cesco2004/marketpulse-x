"""Monthly budget forecasting and auto-throttle logic.

Tracks token consumption pace across the month and recommends
dynamic daily caps to avoid exhausting the monthly budget.
"""

from calendar import monthrange
from datetime import datetime

from storage.database import get_monthly_usage, get_monthly_budget


def get_budget_status(service="mistral"):
    """Return current month budget status for a service.

    Returns dict with:
      - monthly_limit: configured monthly token limit
      - tokens_used: tokens consumed this month
      - tokens_remaining: tokens left
      - pct_used: percentage of budget consumed
      - day_of_month: current day
      - days_in_month: total days in current month
      - days_remaining: days left (including today)
      - daily_avg_used: average daily consumption so far
      - projected_end_of_month: linear projection
      - recommended_daily_cap: suggested daily token limit
      - pace_status: "on_track" | "ahead" | "critical" | "exhausted"
    """
    now = datetime.utcnow()
    day = now.day
    _, days_in_month = monthrange(now.year, now.month)
    days_remaining = days_in_month - day + 1  # include today

    budget = get_monthly_budget()
    usage = get_monthly_usage(service)

    limit_key = f"{service}_monthly_token_limit"
    monthly_limit = budget.get(limit_key, 1000000)
    tokens_used = usage.get("total_tokens", 0)
    tokens_remaining = max(0, monthly_limit - tokens_used)

    pct_used = (tokens_used / monthly_limit * 100) if monthly_limit > 0 else 0

    # Daily average based on elapsed days (at least 1 to avoid division by zero)
    elapsed_days = max(day, 1)
    daily_avg = tokens_used / elapsed_days

    # Linear projection to end of month
    projected = int(daily_avg * days_in_month)

    # Recommended daily cap: spread remaining tokens evenly, with 10% buffer
    if days_remaining > 0 and tokens_remaining > 0:
        recommended_daily = int(tokens_remaining / days_remaining * 0.9)
    else:
        recommended_daily = 0

    # Pace status based on thresholds from config
    throttle_start = budget.get("throttle_start_pct", 70)
    throttle_medium = budget.get("throttle_medium_pct", 85)
    emergency_stop = budget.get("emergency_stop_pct", 95)

    if pct_used >= emergency_stop:
        pace_status = "exhausted"
    elif pct_used >= throttle_medium:
        pace_status = "critical"
    elif pct_used >= throttle_start:
        pace_status = "ahead"
    else:
        pace_status = "on_track"

    return {
        "service": service,
        "monthly_limit": monthly_limit,
        "tokens_used": tokens_used,
        "tokens_remaining": tokens_remaining,
        "pct_used": round(pct_used, 1),
        "day_of_month": day,
        "days_in_month": days_in_month,
        "days_remaining": days_remaining,
        "daily_avg_used": int(daily_avg),
        "projected_end_of_month": projected,
        "recommended_daily_cap": recommended_daily,
        "pace_status": pace_status,
    }


def get_throttle_recommendations(service="mistral"):
    """Return operational recommendations based on current budget pace.

    Returns dict with:
      - max_replies_per_day: recommended reply cap
      - skip_llm_moderation: whether to skip LLM-based moderation
      - skip_post_generation: whether to skip new post generation
      - engagement_enabled: whether engagement should remain active
      - reason: human-readable explanation
    """
    status = get_budget_status(service)
    budget = get_monthly_budget()

    if not budget.get("auto_throttle_enabled", 1):
        return {
            "max_replies_per_day": None,  # no override
            "skip_llm_moderation": False,
            "skip_post_generation": False,
            "engagement_enabled": True,
            "reason": "Auto-throttle disabled",
        }

    pace = status["pace_status"]

    if pace == "on_track":
        return {
            "max_replies_per_day": None,
            "skip_llm_moderation": False,
            "skip_post_generation": False,
            "engagement_enabled": True,
            "reason": f"Budget on track ({status['pct_used']}% used, day {status['day_of_month']}/{status['days_in_month']})",
        }

    if pace == "ahead":
        return {
            "max_replies_per_day": 5,
            "skip_llm_moderation": True,
            "skip_post_generation": False,
            "engagement_enabled": True,
            "reason": f"Budget ahead of pace ({status['pct_used']}% used). Reducing replies to 5/day, keyword-only moderation.",
        }

    if pace == "critical":
        return {
            "max_replies_per_day": 3,
            "skip_llm_moderation": True,
            "skip_post_generation": True,
            "engagement_enabled": True,
            "reason": f"Budget critical ({status['pct_used']}% used). Replies reduced to 3/day, post generation paused.",
        }

    # exhausted
    return {
        "max_replies_per_day": 0,
        "skip_llm_moderation": True,
        "skip_post_generation": True,
        "engagement_enabled": False,
        "reason": f"Budget exhausted ({status['pct_used']}% used). All LLM operations suspended. Publishing from queue only.",
    }
