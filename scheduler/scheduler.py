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
    """Background scheduler with full autopilot: auto-fetch, auto-approve, auto-post.

    When started, runs a continuous loop:
    1. Check if queue has enough approved posts
    2. If not, trigger fetch+generate pipeline (auto-approves best tweets)
    3. Check for market alerts (fast-track significant movements)
    4. Compute posting schedule for the day
    5. Post at scheduled times
    6. Repeat
    """

    # How often to check for new content (minutes) - faster for financial data
    FETCH_INTERVAL_MINUTES = 30  # Every 30 minutes (was 120)
    # How often to check for alerts (minutes)
    ALERT_CHECK_INTERVAL_MINUTES = 10
    # Minimum approved posts before triggering a fetch
    MIN_QUEUE_SIZE = 5
    # Max alert tweets per day
    MAX_ALERT_TWEETS_PER_DAY = 3

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._schedule = []  # list of (datetime_utc, post_id)
        self._last_fetch = None
        self._last_alert_check = None
        self._alert_tweets_today = 0
        self._alert_tweets_date = None

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
        self._last_fetch = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        update_schedule_config(is_active=1)

    def stop(self):
        self._stop_event.set()
        self._schedule = []
        clear_all_scheduled_times()
        update_schedule_config(is_active=0)

    def _should_fetch(self):
        """Determine if we should trigger a fetch+generate cycle."""
        # Always fetch if never fetched
        if self._last_fetch is None:
            return True

        # Fetch if queue is low
        queue = get_approved_posts()
        if len(queue) < self.MIN_QUEUE_SIZE:
            return True

        # Fetch if enough time has passed since last fetch
        elapsed = (datetime.utcnow() - self._last_fetch).total_seconds() / 60
        if elapsed >= self.FETCH_INTERVAL_MINUTES:
            return True

        return False

    def _auto_fetch(self):
        """Run the fetch+generate pipeline. Auto-approves tweets above threshold."""
        try:
            from pipeline import run_fetch_pipeline
            print(f"[Autopilot] Fetching new content...")
            result = run_fetch_pipeline()
            self._last_fetch = datetime.utcnow()

            if result.get("skipped_reason"):
                print(f"[Autopilot] Skipped: {result['skipped_reason']}")
            elif result.get("posts"):
                print(f"[Autopilot] Generated {len(result['posts'])} posts. "
                      f"Auto-approved: {result.get('auto_approved', 0)}, "
                      f"Rejected: {result.get('auto_rejected', 0)}")
            if result.get("errors"):
                for err in result["errors"]:
                    print(f"[Autopilot] Error: {err}")
        except Exception as e:
            print(f"[Autopilot] Fetch error: {e}")
            self._last_fetch = datetime.utcnow()  # Don't retry immediately on error

    def _compute_schedule(self):
        """Pre-compute post times for today, respecting daily limits."""
        config = get_schedule_config()
        all_posts = get_approved_posts()

        if not all_posts:
            self._schedule = []
            return

        # Daily cap
        limits = get_usage_limits()
        safety_cap = limits.get("x_max_tweets_per_day", 15)
        schedule_cap = config.get("random_tweets_per_day", 20) if config["mode"] == "random" else 999
        max_per_day = min(safety_cap, schedule_cap)

        # Subtract already-posted today
        already_posted_today = get_daily_tweet_count()
        remaining_today = max(0, max_per_day - already_posted_today)

        if remaining_today == 0:
            self._schedule = []
            return

        tz_name = config.get("timezone", "Europe/Paris")
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone("Europe/Paris")

        now_utc = datetime.utcnow()
        now_local = pytz.utc.localize(now_utc).astimezone(tz)

        # Only schedule for today (autopilot will refill queue and reschedule tomorrow)
        today_batch = all_posts[:remaining_today]
        schedule = self._schedule_day(today_batch, config, tz, now_local, 0, is_today=True)

        self._schedule = schedule
        if schedule:
            print(f"[Autopilot] Scheduled {len(schedule)} posts for today ({already_posted_today} already posted, {max_per_day} max)")

    def _schedule_day(self, posts, config, tz, now_local, day_offset, is_today):
        """Schedule a batch of posts for a single day. Returns list of (utc_time, post_id)."""
        schedule = []

        start_hour = config.get("random_start_hour", 9)
        start_minute = config.get("random_start_minute", 0)
        end_hour = config.get("random_end_hour", 22)
        end_minute = config.get("random_end_minute", 0)

        base_day = now_local + timedelta(days=day_offset)
        window_start = base_day.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        window_end = base_day.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

        if config["mode"] == "fixed":
            interval_minutes = config["fixed_interval_hours"] * 60 + config["fixed_interval_minutes"]
            if interval_minutes < 1:
                interval_minutes = 1

            cursor = max(now_local, window_start) if is_today else window_start

            for post in posts:
                cursor = cursor + timedelta(minutes=interval_minutes)
                post_time_utc = cursor.astimezone(pytz.utc).replace(tzinfo=None)
                schedule.append((post_time_utc, post["id"]))
                set_post_scheduled_at(post["id"], post_time_utc.isoformat())

        else:  # random
            min_gap = config.get("random_min_gap_hours", 0) * 60 + config.get("random_min_gap_minutes", 5)
            max_gap = config.get("random_max_gap_hours", 1) * 60 + config.get("random_max_gap_minutes", 0)
            if min_gap < 1:
                min_gap = 1
            if max_gap <= min_gap:
                max_gap = min_gap + 1

            effective_start = max(now_local, window_start) if is_today else window_start
            available_minutes = (window_end - effective_start).total_seconds() / 60

            n = len(posts)
            day_min_gap = min_gap
            day_max_gap = max_gap

            if n > 1:
                total_min_needed = day_min_gap * (n - 1)
                if total_min_needed > available_minutes:
                    even_gap = max(1, int(available_minutes / n))
                    day_min_gap = max(1, even_gap - 5)
                    day_max_gap = even_gap + 5
                elif day_max_gap * (n - 1) > available_minutes:
                    day_max_gap = max(day_min_gap + 1, int(available_minutes / (n - 1)))

            first_gap = random.randint(day_min_gap, min(day_max_gap, day_min_gap + 15))
            cursor = effective_start + timedelta(minutes=first_gap)

            for post in posts:
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

    def _should_check_alerts(self):
        """Determine if we should check for market alerts."""
        if self._last_alert_check is None:
            return True
        elapsed = (datetime.utcnow() - self._last_alert_check).total_seconds() / 60
        return elapsed >= self.ALERT_CHECK_INTERVAL_MINUTES

    def _check_and_post_alerts(self):
        """Check for pending market alerts and fast-track them to posting."""
        try:
            from alerts.detector import check_and_process_alerts, mark_alert_tweeted
            from pipeline import run_fetch_pipeline, publish_post

            self._last_alert_check = datetime.utcnow()

            # Reset daily counter if new day
            today = datetime.utcnow().date()
            if self._alert_tweets_date != today:
                self._alert_tweets_today = 0
                self._alert_tweets_date = today

            if self._alert_tweets_today >= self.MAX_ALERT_TWEETS_PER_DAY:
                return

            alerts = check_and_process_alerts()
            if not alerts:
                return

            print(f"[Autopilot] Found {len(alerts)} pending alerts")

            for alert in alerts[:self.MAX_ALERT_TWEETS_PER_DAY - self._alert_tweets_today]:
                try:
                    # Generate alert tweet via pipeline (uses alert_breaking template)
                    from sources.aggregator import format_financial_data_for_prompt
                    from alerts.detector import format_alerts_for_prompt

                    alert_text = format_alerts_for_prompt([alert])
                    print(f"[Autopilot] Processing alert: {alert.get('description', 'N/A')}")

                    # For now, just log the alert - full alert posting will use the pipeline
                    # The regular fetch cycle will pick up the alert data and generate tweets
                    self._alert_tweets_today += 1

                except Exception as e:
                    print(f"[Autopilot] Alert processing error: {e}")

        except ImportError:
            pass  # alerts module not available
        except Exception as e:
            print(f"[Autopilot] Alert check error: {e}")

    def _run_loop(self):
        """Main autopilot loop: fetch → alerts → schedule → post → repeat."""
        while not self._stop_event.is_set():
            try:
                # Step 1: Auto-fetch if queue is low or enough time has passed
                if self._should_fetch():
                    self._auto_fetch()

                # Step 2: Check for market alerts (more frequent than regular fetch)
                if self._should_check_alerts():
                    self._check_and_post_alerts()

                # Step 3: Compute today's schedule if empty
                if not self._schedule:
                    self._compute_schedule()

                # Step 4: If still no posts, wait and retry
                if not self._schedule:
                    print("[Autopilot] No approved posts. Waiting 15min before next fetch...")
                    self._stop_event.wait(timeout=900)  # Wait 15 minutes (was 30)
                    self._last_fetch = None  # Force a fetch on next loop
                    continue

                # Step 5: Wait for next post time
                next_time_utc, post_id = self._schedule[0]

                while not self._stop_event.is_set():
                    now = datetime.utcnow()
                    remaining = (next_time_utc - now).total_seconds()
                    if remaining <= 0:
                        break
                    # Check every 15s, also check alerts while waiting
                    wait_time = min(15, remaining)
                    time.sleep(wait_time)
                    # Check alerts during wait
                    if self._should_check_alerts():
                        self._check_and_post_alerts()

                if self._stop_event.is_set():
                    break

                # Step 6: Post (with freshness check)
                self._schedule.pop(0)
                post = get_post_by_id(post_id)
                if post and post["status"] == "approved":
                    # Freshness gate: skip tweets older than 4 hours
                    post_dict = dict(post)
                    created_at = post_dict.get("created_at", "")
                    is_stale = False
                    if created_at:
                        try:
                            from dateutil import parser as dp
                            created_dt = dp.parse(str(created_at))
                            age_hours = (datetime.utcnow() - created_dt.replace(tzinfo=None)).total_seconds() / 3600
                            if age_hours > 4:
                                is_stale = True
                                from storage.database import update_post_status
                                update_post_status(post_id, "expired")
                                print(f"[Autopilot] Skipped stale #{post_id} ({age_hours:.1f}h old)")
                        except Exception:
                            pass  # If we can't parse date, allow the post

                    if not is_stale:
                        try:
                            from pipeline import publish_post
                            tweet_id, has_image = publish_post(post)
                            mark_as_posted(post_id, tweet_id)
                            img_tag = " (with chart)" if has_image else ""
                            print(f"[Autopilot] Posted #{post_id}{img_tag} -> tweet {tweet_id}")
                        except Exception as e:
                            print(f"[Autopilot] Error posting #{post_id}: {e}")

            except Exception as e:
                print(f"[Autopilot] Loop error: {e}")
                self._stop_event.wait(timeout=60)  # Wait 1 min on error

        # Stopped
        if not self._stop_event.is_set():
            update_schedule_config(is_active=0)


# Global singleton
scheduler = QuantumScheduler()
