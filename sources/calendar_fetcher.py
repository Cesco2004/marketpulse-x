"""Economic calendar: provides awareness of upcoming major economic events.

Uses a static calendar of known macro event dates (FOMC, CPI, jobs reports, etc.)
that are published well in advance. This enables context like
"S&P +0.4% ahead of tomorrow's CPI release" instead of just "S&P +0.4%."
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Major US economic events for 2026 (dates sourced from Fed/BLS calendars)
# Format: (month, day, event_name, impact_level)
# impact_level: "high" = FOMC/CPI/NFP, "medium" = PPI/GDP/retail sales
ECONOMIC_CALENDAR_2026 = [
    # FOMC meetings (2-day, date = decision day)
    (1, 28, "FOMC Rate Decision", "high"),
    (3, 18, "FOMC Rate Decision", "high"),
    (5, 6, "FOMC Rate Decision", "high"),
    (6, 17, "FOMC Rate Decision", "high"),
    (7, 29, "FOMC Rate Decision", "high"),
    (9, 16, "FOMC Rate Decision", "high"),
    (11, 4, "FOMC Rate Decision", "high"),
    (12, 16, "FOMC Rate Decision", "high"),
    # CPI releases (typically 10th-14th of each month)
    (1, 14, "CPI Report", "high"),
    (2, 12, "CPI Report", "high"),
    (3, 11, "CPI Report", "high"),
    (4, 14, "CPI Report", "high"),
    (5, 13, "CPI Report", "high"),
    (6, 10, "CPI Report", "high"),
    (7, 14, "CPI Report", "high"),
    (8, 12, "CPI Report", "high"),
    (9, 15, "CPI Report", "high"),
    (10, 13, "CPI Report", "high"),
    (11, 12, "CPI Report", "high"),
    (12, 10, "CPI Report", "high"),
    # Non-Farm Payrolls (typically first Friday of month)
    (1, 9, "Non-Farm Payrolls", "high"),
    (2, 6, "Non-Farm Payrolls", "high"),
    (3, 6, "Non-Farm Payrolls", "high"),
    (4, 3, "Non-Farm Payrolls", "high"),
    (5, 8, "Non-Farm Payrolls", "high"),
    (6, 5, "Non-Farm Payrolls", "high"),
    (7, 2, "Non-Farm Payrolls", "high"),
    (8, 7, "Non-Farm Payrolls", "high"),
    (9, 4, "Non-Farm Payrolls", "high"),
    (10, 2, "Non-Farm Payrolls", "high"),
    (11, 6, "Non-Farm Payrolls", "high"),
    (12, 4, "Non-Farm Payrolls", "high"),
    # GDP releases (quarterly)
    (1, 29, "Q4 2025 GDP (Advance)", "medium"),
    (2, 26, "Q4 2025 GDP (Second)", "medium"),
    (3, 26, "Q4 2025 GDP (Third)", "medium"),
    (4, 29, "Q1 2026 GDP (Advance)", "medium"),
    (7, 29, "Q2 2026 GDP (Advance)", "medium"),
    (10, 28, "Q3 2026 GDP (Advance)", "medium"),
]


def get_upcoming_events(days_ahead=2):
    """Get economic events happening within the next N days.

    Returns list of event dicts with name, date, and days_until.
    Used by the correlation engine and prompt formatter to add event context.
    """
    now = datetime.now(timezone.utc)
    year = now.year
    upcoming = []

    for month, day, name, impact in ECONOMIC_CALENDAR_2026:
        try:
            event_date = datetime(year, month, day, tzinfo=timezone.utc)
            delta = (event_date.date() - now.date()).days

            if 0 <= delta <= days_ahead:
                upcoming.append({
                    "name": name,
                    "date": event_date.strftime("%Y-%m-%d"),
                    "days_until": delta,
                    "impact": impact,
                    "context": _format_context(name, delta),
                })
        except ValueError:
            continue

    return upcoming


def _format_context(event_name, days_until):
    """Generate a human-readable context string for the event."""
    if days_until == 0:
        return f"{event_name} today"
    elif days_until == 1:
        return f"{event_name} tomorrow"
    else:
        return f"{event_name} in {days_until} days"


def get_event_context_for_prompt():
    """Get a formatted string of upcoming events for inclusion in LLM prompts.

    Returns None if no events are upcoming.
    """
    events = get_upcoming_events(days_ahead=2)
    if not events:
        return None

    lines = ["=== UPCOMING ECONOMIC EVENTS ==="]
    for e in events:
        impact_tag = "[HIGH IMPACT]" if e["impact"] == "high" else "[MEDIUM]"
        lines.append(f"  {impact_tag} {e['context']} ({e['date']})")
    lines.append("  Use this context in tweets where relevant (e.g., 'ahead of tomorrow's CPI release').")
    lines.append("")

    return "\n".join(lines)
