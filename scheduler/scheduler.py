import random
import time
import threading
from datetime import datetime, timedelta

import pytz

from storage.database import (
    get_approved_posts, mark_as_posted, get_schedule_config,
    update_schedule_config, set_post_scheduled_at, clear_all_scheduled_times,
    get_post_by_id,
)
from publisher.x_publisher import post_tweet


class QuantumScheduler:
    """Background scheduler that pre-computes real post times and posts at those times."""

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
        """Pre-compute all post times and store them in DB."""
        config = get_schedule_config()
        posts = get_approved_posts()

        if not posts:
            self._schedule = []
            return

        tz_name = config.get("timezone", "Europe/Paris")
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone("Europe/Paris")

        now_utc = datetime.utcnow()
        now_local = pytz.utc.localize(now_utc).astimezone(tz)

        schedule = []

        if config["mode"] == "fixed":
            interval_minutes = config["fixed_interval_hours"] * 60 + config["fixed_interval_minutes"]
            if interval_minutes < 1:
                interval_minutes = 1

            for i, post in enumerate(posts):
                post_time_utc = now_utc + timedelta(minutes=interval_minutes * (i + 1))
                schedule.append((post_time_utc, post["id"]))
                set_post_scheduled_at(post["id"], post_time_utc.isoformat())

        else:  # random
            min_gap = config.get("random_min_gap_hours", 0) * 60 + config.get("random_min_gap_minutes", 0)
            max_gap = config.get("random_max_gap_hours", 0) * 60 + config.get("random_max_gap_minutes", 0)
            if min_gap < 1:
                min_gap = 1
            if max_gap <= min_gap:
                max_gap = min_gap + 1

            start_hour = config.get("random_start_hour", 9)
            start_minute = config.get("random_start_minute", 0)
            end_hour = config.get("random_end_hour", 22)
            end_minute = config.get("random_end_minute", 0)

            # Build the first valid start time in local tz
            window_start_local = now_local.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            window_end_local = now_local.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

            # If we're past today's window, start tomorrow
            if now_local >= window_end_local:
                window_start_local += timedelta(days=1)
                window_end_local += timedelta(days=1)

            # If we're before today's window, use window start
            if now_local < window_start_local:
                cursor_local = window_start_local
            else:
                # First post: random gap from now
                first_gap = random.randint(min_gap, max_gap)
                cursor_local = now_local + timedelta(minutes=first_gap)

            day_offset = 0
            for post in posts:
                current_window_start = window_start_local + timedelta(days=day_offset)
                current_window_end = window_end_local + timedelta(days=day_offset)

                # If cursor is past today's window, move to next day
                if cursor_local >= current_window_end:
                    day_offset += 1
                    current_window_start = window_start_local + timedelta(days=day_offset)
                    current_window_end = window_end_local + timedelta(days=day_offset)
                    cursor_local = current_window_start

                # If cursor is before window start, snap to window start
                if cursor_local < current_window_start:
                    cursor_local = current_window_start

                post_time_utc = cursor_local.astimezone(pytz.utc).replace(tzinfo=None)
                schedule.append((post_time_utc, post["id"]))
                set_post_scheduled_at(post["id"], post_time_utc.isoformat())

                # Next cursor
                gap = random.randint(min_gap, max_gap)
                cursor_local = cursor_local + timedelta(minutes=gap)

        self._schedule = schedule

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
