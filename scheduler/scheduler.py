import random
import time
import threading
from datetime import datetime, timedelta

import pytz

from storage.database import (
    get_approved_posts, mark_as_posted, get_schedule_config,
    update_schedule_config, set_post_scheduled_at, clear_all_scheduled_times,
    get_post_by_id, get_usage_limits, get_daily_tweet_count,
)
from publisher.x_publisher import post_tweet


class QuantumScheduler:
    """Background scheduler that pre-computes real post times and posts at those times.

    Schedules across multiple days: if the queue has more posts than the daily
    cap, the overflow is automatically scheduled for the next day(s).
    """

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._schedule = []  # list of (datetime_utc, post_id)

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def next_post_time(self):
        if self._schedule:
            return self._schedule[0][0]
        return None

    def start(self):
        if self.is_running:
            return
        self._stop_event.clear()
        self._compute_schedule()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        update_schedule_config(is_active=1)

    def stop(self):
        self._stop_event.set()
        self._schedule = []
        clear_all_scheduled_times()
        update_schedule_config(is_active=0)

    def _compute_schedule(self):
        """Pre-compute post times across multiple days, respecting daily limits.

        Splits the queue into daily batches (max_per_day each) and distributes
        each batch across that day's active window. Gaps are auto-adjusted if
        the configured gaps can't fit the batch in the window.
        """
        config = get_schedule_config()
        all_posts = get_approved_posts()

        if not all_posts:
            self._schedule = []
            return

        # Daily cap = min(schedule "tweets per day", safety limit)
        limits = get_usage_limits()
        safety_cap = limits.get("x_max_tweets_per_day", 15)
        schedule_cap = config.get("random_tweets_per_day", 999) if config["mode"] == "random" else 999
        max_per_day = min(safety_cap, schedule_cap)

        # For today, subtract already-posted tweets
        already_posted_today = get_daily_tweet_count()
        remaining_today = max(0, max_per_day - already_posted_today)

        tz_name = config.get("timezone", "Europe/Paris")
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone("Europe/Paris")

        now_utc = datetime.utcnow()
        now_local = pytz.utc.localize(now_utc).astimezone(tz)

        # Split posts into daily batches
        batches = []
        remaining_posts = list(all_posts)

        # Day 0 (today): limited by already-posted count
        today_batch = remaining_posts[:remaining_today]
        remaining_posts = remaining_posts[remaining_today:]
        if today_batch:
            batches.append((0, today_batch))

        # Day 1, 2, 3... : full max_per_day each
        day = 1
        while remaining_posts:
            batch = remaining_posts[:max_per_day]
            remaining_posts = remaining_posts[max_per_day:]
            batches.append((day, batch))
            day += 1

        total_scheduled = sum(len(b) for _, b in batches)
        days_needed = len(batches)
        print(f"[Scheduler] Scheduling {total_scheduled}/{len(all_posts)} posts across {days_needed} day(s) (max {max_per_day}/day, {already_posted_today} already posted today)")

        schedule = []

        for day_offset, posts in batches:
            day_schedule = self._schedule_day(
                posts, config, tz, now_local, day_offset, is_today=(day_offset == 0),
            )
            schedule.extend(day_schedule)

        self._schedule = schedule

    def _schedule_day(self, posts, config, tz, now_local, day_offset, is_today):
        """Schedule a batch of posts for a single day. Returns list of (utc_time, post_id)."""
        schedule = []

        start_hour = config.get("random_start_hour", 9)
        start_minute = config.get("random_start_minute", 0)
        end_hour = config.get("random_end_hour", 22)
        end_minute = config.get("random_end_minute", 0)

        # Build the active window for this day
        base_day = now_local + timedelta(days=day_offset)
        window_start = base_day.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        window_end = base_day.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

        if config["mode"] == "fixed":
            interval_minutes = config["fixed_interval_hours"] * 60 + config["fixed_interval_minutes"]
            if interval_minutes < 1:
                interval_minutes = 1

            # For today, start from now; for future days, start from window start
            if is_today:
                cursor = max(now_local, window_start)
            else:
                cursor = window_start

            for post in posts:
                cursor = cursor + timedelta(minutes=interval_minutes)
                post_time_utc = cursor.astimezone(pytz.utc).replace(tzinfo=None)
                schedule.append((post_time_utc, post["id"]))
                set_post_scheduled_at(post["id"], post_time_utc.isoformat())

        else:  # random
            min_gap = config.get("random_min_gap_hours", 0) * 60 + config.get("random_min_gap_minutes", 0)
            max_gap = config.get("random_max_gap_hours", 0) * 60 + config.get("random_max_gap_minutes", 0)
            if min_gap < 1:
                min_gap = 1
            if max_gap <= min_gap:
                max_gap = min_gap + 1

            # Effective start for this day
            if is_today:
                effective_start = max(now_local, window_start)
            else:
                effective_start = window_start

            # Available minutes in this day's window
            available_minutes = (window_end - effective_start).total_seconds() / 60

            # Auto-adjust gaps to fit all posts in the window
            n = len(posts)
            day_min_gap = min_gap
            day_max_gap = max_gap

            if n > 1:
                total_min_needed = day_min_gap * (n - 1)
                if total_min_needed > available_minutes:
                    even_gap = max(1, int(available_minutes / n))
                    day_min_gap = max(1, even_gap - 5)
                    day_max_gap = even_gap + 5
                    label = "today" if is_today else f"day +{day_offset}"
                    print(f"[Scheduler] Auto-adjusted gaps to {day_min_gap}-{day_max_gap}min for {label} ({n} tweets in {available_minutes:.0f}min)")
                elif day_max_gap * (n - 1) > available_minutes:
                    day_max_gap = max(day_min_gap + 1, int(available_minutes / (n - 1)))

            # First post: small random gap from start
            first_gap = random.randint(day_min_gap, min(day_max_gap, day_min_gap + 15))
            cursor = effective_start + timedelta(minutes=first_gap)

            for post in posts:
                # Clamp to window
                if cursor > window_end:
                    cursor = window_end - timedelta(minutes=1)
                if cursor < effective_start:
                    cursor = effective_start

                post_time_utc = cursor.astimezone(pytz.utc).replace(tzinfo=None)
                schedule.append((post_time_utc, post["id"]))
                set_post_scheduled_at(post["id"], post_time_utc.isoformat())

                gap = random.randint(day_min_gap, day_max_gap)
                cursor = cursor + timedelta(minutes=gap)

        return schedule

    def _run_loop(self):
        """Wait for each scheduled time and post."""
        while not self._stop_event.is_set() and self._schedule:
            next_time_utc, post_id = self._schedule[0]

            # Wait until it's time
            while not self._stop_event.is_set():
                now = datetime.utcnow()
                remaining = (next_time_utc - now).total_seconds()
                if remaining <= 0:
                    break
                time.sleep(min(15, remaining))

            if self._stop_event.is_set():
                break

            # Post it
            self._schedule.pop(0)
            post = get_post_by_id(post_id)
            if post and post["status"] == "approved":
                try:
                    from pipeline import publish_post
                    tweet_id, _ = publish_post(post)
                    mark_as_posted(post_id, tweet_id)
                except Exception as e:
                    print(f"[Scheduler] Error posting #{post_id}: {e}")

        # Done - all posted or stopped
        if not self._stop_event.is_set():
            update_schedule_config(is_active=0)


# Global singleton
scheduler = QuantumScheduler()
