import os

from storage.database import (
    get_usage_limits,
    get_daily_usage,
    get_daily_tweet_count,
    get_daily_reply_count,
    get_kill_switch,
    is_bot_killed,
    increment_consecutive_errors,
    reset_consecutive_errors,
    was_alert_sent_today,
    get_monthly_usage,
    get_monthly_budget,
)
from limiter.alerts import send_usage_warning, send_limit_reached, send_error_alert


# File-based kill switch fallback (touch data/KILL to activate)
_KILL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "KILL")


class UsageLimiter:
    """Checks usage limits before API calls. Thread-safe via DB queries."""

    def check_mistral(self):
        """Check if a Mistral API call is allowed.
        Returns (allowed: bool, reason: str).
        """
        killed, reason = self._check_kill_switch()
        if killed:
            return False, reason

        # Monthly budget check
        monthly = get_monthly_usage("mistral")
        budget = get_monthly_budget()
        monthly_limit = budget.get("mistral_monthly_token_limit", 1000000)
        if monthly_limit > 0 and monthly.get("total_tokens", 0) >= monthly_limit:
            reason = f"Monthly Mistral token limit reached ({monthly['total_tokens']:,}/{monthly_limit:,})"
            self._alert_limit_reached("mistral_monthly", reason)
            return False, reason

        # Monthly budget warning
        if monthly_limit > 0:
            monthly_pct = monthly.get("total_tokens", 0) / monthly_limit * 100
            alert_threshold = budget.get("budget_alert_threshold_pct", 75)
            if monthly_pct >= alert_threshold and not was_alert_sent_today("warning_mistral_monthly"):
                send_usage_warning("Mistral (monthly)", monthly_pct,
                                   f"Tokens: {monthly['total_tokens']:,}/{monthly_limit:,} ({monthly_pct:.0f}%)")

        limits = get_usage_limits()
        usage = get_daily_usage("mistral")

        # Check call count
        max_calls = limits.get("mistral_max_calls_per_day", 50)
        current_calls = usage.get("calls", 0)
        if current_calls >= max_calls:
            reason = f"Daily Mistral call limit reached ({current_calls}/{max_calls})"
            self._alert_limit_reached("mistral", reason)
            return False, reason

        # Check token count
        max_tokens = limits.get("mistral_max_tokens_per_day", 500000)
        current_tokens = usage.get("total_tokens", 0)
        if current_tokens >= max_tokens:
            reason = f"Daily Mistral token limit reached ({current_tokens}/{max_tokens})"
            self._alert_limit_reached("mistral", reason)
            return False, reason

        # Check cost
        max_cost = limits.get("mistral_max_cost_per_day", 1.00)
        current_cost = usage.get("total_cost", 0)
        if current_cost >= max_cost:
            reason = f"Daily Mistral cost limit reached (${current_cost:.4f}/${max_cost:.2f})"
            self._alert_limit_reached("mistral", reason)
            return False, reason

        # Warning threshold check
        self._check_warning("mistral", limits, current_calls, max_calls,
                            current_tokens, max_tokens, current_cost, max_cost)

        return True, ""

    def check_groq(self):
        """Check if a Groq API call is allowed.
        Returns (allowed: bool, reason: str).
        """
        killed, reason = self._check_kill_switch()
        if killed:
            return False, reason

        # Monthly budget check
        monthly = get_monthly_usage("groq")
        budget = get_monthly_budget()
        monthly_limit = budget.get("groq_monthly_token_limit", 1500000)
        if monthly_limit > 0 and monthly.get("total_tokens", 0) >= monthly_limit:
            reason = f"Monthly Groq token limit reached ({monthly['total_tokens']:,}/{monthly_limit:,})"
            self._alert_limit_reached("groq_monthly", reason)
            return False, reason

        return True, ""

    def check_twitter_post(self):
        """Check if posting a tweet is allowed.
        Returns (allowed: bool, reason: str).
        """
        killed, reason = self._check_kill_switch()
        if killed:
            return False, reason

        limits = get_usage_limits()
        max_tweets = limits.get("x_max_tweets_per_day", 15)
        current = get_daily_tweet_count()

        if current >= max_tweets:
            reason = f"Daily tweet limit reached ({current}/{max_tweets})"
            self._alert_limit_reached("x_tweets", reason)
            return False, reason

        # Warning
        threshold = limits.get("warning_threshold_pct", 80)
        if max_tweets > 0:
            pct = (current / max_tweets) * 100
            if pct >= threshold and not was_alert_sent_today("warning_x_tweets"):
                send_usage_warning("Twitter tweets", pct, f"{current}/{max_tweets} tweets")

        return True, ""

    def check_twitter_reply(self):
        """Check if posting a reply is allowed.
        Returns (allowed: bool, reason: str).
        """
        killed, reason = self._check_kill_switch()
        if killed:
            return False, reason

        limits = get_usage_limits()
        max_replies = limits.get("x_max_replies_per_day", 10)
        current = get_daily_reply_count()

        if current >= max_replies:
            reason = f"Daily reply limit reached ({current}/{max_replies})"
            self._alert_limit_reached("x_replies", reason)
            return False, reason

        # Warning
        threshold = limits.get("warning_threshold_pct", 80)
        if max_replies > 0:
            pct = (current / max_replies) * 100
            if pct >= threshold and not was_alert_sent_today("warning_x_replies"):
                send_usage_warning("Twitter replies", pct, f"{current}/{max_replies} replies")

        return True, ""

    def report_error(self, service, error):
        """Track consecutive errors. Alert if threshold exceeded."""
        result = increment_consecutive_errors()
        current = result.get("current_consecutive_errors", 0)
        max_errors = result.get("max_consecutive_errors", 5)

        if current >= max_errors and not was_alert_sent_today(f"errors_{service}"):
            send_error_alert(service, current, str(error))

    def report_success(self, service):
        """Reset consecutive error counter on success."""
        reset_consecutive_errors()

    def get_status(self):
        """Return current usage status for dashboard display."""
        limits = get_usage_limits()
        mistral = get_daily_usage("mistral")
        groq = get_daily_usage("groq")
        tweet_count = get_daily_tweet_count()
        reply_count = get_daily_reply_count()
        ks = get_kill_switch()
        budget = get_monthly_budget()

        max_calls = limits.get("mistral_max_calls_per_day", 50)
        max_tokens = limits.get("mistral_max_tokens_per_day", 500000)
        max_cost = limits.get("mistral_max_cost_per_day", 1.00)
        max_tweets = limits.get("x_max_tweets_per_day", 15)
        max_replies = limits.get("x_max_replies_per_day", 10)

        # Monthly data
        mistral_monthly = get_monthly_usage("mistral")
        groq_monthly = get_monthly_usage("groq")
        mistral_monthly_limit = budget.get("mistral_monthly_token_limit", 1000000)
        groq_monthly_limit = budget.get("groq_monthly_token_limit", 1500000)

        return {
            "kill_switch": bool(ks.get("is_killed")),
            "kill_reason": ks.get("killed_reason", ""),
            "kill_file_exists": os.path.exists(_KILL_FILE),
            # Mistral daily
            "mistral_calls": mistral.get("calls", 0),
            "mistral_calls_max": max_calls,
            "mistral_calls_pct": min(100, (mistral.get("calls", 0) / max_calls * 100)) if max_calls else 0,
            "mistral_tokens": mistral.get("total_tokens", 0),
            "mistral_tokens_max": max_tokens,
            "mistral_tokens_pct": min(100, (mistral.get("total_tokens", 0) / max_tokens * 100)) if max_tokens else 0,
            "mistral_cost": mistral.get("total_cost", 0),
            "mistral_cost_max": max_cost,
            "mistral_cost_pct": min(100, (mistral.get("total_cost", 0) / max_cost * 100)) if max_cost else 0,
            # Groq daily
            "groq_calls": groq.get("calls", 0),
            "groq_tokens": groq.get("total_tokens", 0),
            # X/Twitter daily
            "x_tweets": tweet_count,
            "x_tweets_max": max_tweets,
            "x_tweets_pct": min(100, (tweet_count / max_tweets * 100)) if max_tweets else 0,
            "x_replies": reply_count,
            "x_replies_max": max_replies,
            "x_replies_pct": min(100, (reply_count / max_replies * 100)) if max_replies else 0,
            "consecutive_errors": limits.get("current_consecutive_errors", 0),
            "limits": limits,
            # Monthly budget data
            "mistral_monthly_tokens": mistral_monthly.get("total_tokens", 0),
            "mistral_monthly_limit": mistral_monthly_limit,
            "mistral_monthly_pct": min(100, (mistral_monthly.get("total_tokens", 0) / mistral_monthly_limit * 100)) if mistral_monthly_limit else 0,
            "groq_monthly_tokens": groq_monthly.get("total_tokens", 0),
            "groq_monthly_limit": groq_monthly_limit,
            "groq_monthly_pct": min(100, (groq_monthly.get("total_tokens", 0) / groq_monthly_limit * 100)) if groq_monthly_limit else 0,
            "budget": budget,
        }

    def _check_kill_switch(self):
        """Check DB kill switch and file-based fallback."""
        # File-based kill switch
        if os.path.exists(_KILL_FILE):
            return True, "Kill switch activated (file: data/KILL)"

        # DB kill switch
        if is_bot_killed():
            ks = get_kill_switch()
            reason = ks.get("killed_reason", "")
            return True, f"Kill switch activated{': ' + reason if reason else ''}"

        return False, ""

    def _check_warning(self, service, limits, calls, max_calls, tokens, max_tokens, cost, max_cost):
        """Send warning email if any metric crosses the threshold."""
        threshold = limits.get("warning_threshold_pct", 80)

        details_parts = []
        highest_pct = 0

        if max_calls > 0:
            pct = (calls / max_calls) * 100
            if pct >= threshold:
                details_parts.append(f"Calls: {calls}/{max_calls} ({pct:.0f}%)")
                highest_pct = max(highest_pct, pct)

        if max_tokens > 0:
            pct = (tokens / max_tokens) * 100
            if pct >= threshold:
                details_parts.append(f"Tokens: {tokens}/{max_tokens} ({pct:.0f}%)")
                highest_pct = max(highest_pct, pct)

        if max_cost > 0:
            pct = (cost / max_cost) * 100
            if pct >= threshold:
                details_parts.append(f"Cost: ${cost:.4f}/${max_cost:.2f} ({pct:.0f}%)")
                highest_pct = max(highest_pct, pct)

        if details_parts and not was_alert_sent_today(f"warning_{service}"):
            send_usage_warning(service, highest_pct, "\n".join(details_parts))

    def _alert_limit_reached(self, service, reason):
        if not was_alert_sent_today(f"limit_{service}"):
            send_limit_reached(service, reason)


# Module-level singleton
usage_limiter = UsageLimiter()
