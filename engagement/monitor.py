import json
import random
import threading
from datetime import datetime, timedelta

import pytz

from storage.database import (
    get_engagement_config,
    update_engagement_config,
    get_target_accounts,
    update_target_account,
    update_target_last_seen,
    increment_target_errors,
    reset_target_errors,
    tweet_already_replied,
    save_engagement_reply,
    get_ready_engagement_replies,
    mark_engagement_reply_posted,
    update_engagement_reply_status,
    get_engagement_replies_today,
    get_engagement_replies_today_for_account,
    get_quality_config,
)
from engagement.twitter_reader import twitter_reader
from engagement.reply_generator import generate_reply, pick_best_reply, check_toxicity
from limiter.usage_limiter import usage_limiter


class EngagementMonitor:
    """Background monitor that polls target accounts and auto-posts replies."""

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self.stats = {
            "polls": 0,
            "new_tweets": 0,
            "replies_generated": 0,
            "replies_posted": 0,
            "errors": 0,
            "last_poll": None,
        }

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return
        self._stop_event.clear()
        update_engagement_config(is_enabled=1)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[Engagement] Monitor started.")

    def stop(self):
        self._stop_event.set()
        update_engagement_config(is_enabled=0)
        print("[Engagement] Monitor stopped.")

    def _run_loop(self):
        """Main loop: poll, post ready replies, sleep, repeat."""
        import traceback
        print("[Engagement] Loop thread started.")
        try:
            while not self._stop_event.is_set():
                cfg = get_engagement_config()
                if not cfg.get("is_enabled"):
                    print("[Engagement] is_enabled=0, stopping loop.")
                    break

                try:
                    self._poll(cfg)
                except Exception as e:
                    print(f"[Engagement] Poll error: {e}")
                    traceback.print_exc()
                    self.stats["errors"] += 1

                try:
                    self._post_ready_replies()
                except Exception as e:
                    print(f"[Engagement] Post error: {e}")
                    traceback.print_exc()
                    self.stats["errors"] += 1

                self.stats["polls"] += 1
                self.stats["last_poll"] = datetime.utcnow().isoformat()

                # Sleep for poll_interval_minutes
                interval = max(cfg.get("poll_interval_minutes", 10), 1) * 60
                print(f"[Engagement] Poll done. Next poll in {interval//60} min.")
                self._stop_event.wait(timeout=interval)
        except Exception as e:
            print(f"[Engagement] FATAL loop error: {e}")
            traceback.print_exc()
        finally:
            print("[Engagement] Loop thread exited.")

        if not self._stop_event.is_set():
            update_engagement_config(is_enabled=0)

    def poll_once(self):
        """Run a single poll cycle manually. Returns stats dict."""
        cfg = get_engagement_config()
        try:
            self._poll(cfg)
        except Exception as e:
            print(f"[Engagement] Poll error: {e}")
            self.stats["errors"] += 1

        try:
            self._post_ready_replies()
        except Exception as e:
            print(f"[Engagement] Post error: {e}")
            self.stats["errors"] += 1

        self.stats["polls"] += 1
        self.stats["last_poll"] = datetime.utcnow().isoformat()
        return dict(self.stats)

    # --- Phase 1: Poll & generate ---

    def _poll(self, cfg):
        """Poll all target accounts for new tweets and generate replies."""
        # Check kill switch before polling
        killed, reason = usage_limiter._check_kill_switch()
        if killed:
            print(f"[Engagement] {reason} - skipping poll.")
            return

        if not self._is_within_active_hours(cfg):
            print("[Engagement] Outside active hours, skipping poll.")
            return

        daily_count = get_engagement_replies_today()
        max_daily = cfg.get("max_replies_per_day", 10)
        if daily_count >= max_daily:
            print(f"[Engagement] Daily limit reached ({daily_count}/{max_daily}).")
            return

        accounts = get_target_accounts(enabled_only=True)
        if not accounts:
            print("[Engagement] No enabled accounts.")
            return

        quality_config = get_quality_config()

        for account in accounts:
            if self._stop_event.is_set():
                break
            if daily_count >= max_daily:
                break
            try:
                new_count = self._poll_account(account, cfg, quality_config)
                daily_count += new_count
            except Exception as e:
                print(f"[Engagement] Error polling @{account['username']}: {e}")
                increment_target_errors(account["id"])
                self.stats["errors"] += 1

    def _poll_account(self, account, cfg, quality_config):
        """Poll a single account. Returns number of new replies generated."""
        account_id = account["id"]
        username = account["username"]

        # Resolve user_id on first poll
        user_id = account.get("user_id")
        if not user_id:
            user_id, display_name = twitter_reader.get_user_id(username)
            if not user_id:
                print(f"[Engagement] Could not resolve @{username}")
                increment_target_errors(account_id)
                return 0
            update_target_account(account_id, user_id=user_id, display_name=display_name or "")
            print(f"[Engagement] Resolved @{username} -> {user_id} ({display_name})")

        # Fetch recent tweets
        tweets = twitter_reader.get_recent_tweets(user_id, count=10)
        reset_target_errors(account_id)

        if not tweets:
            update_target_last_seen(account_id, account.get("last_seen_tweet_id", ""))
            return 0

        # Filter to only new tweets (id > last_seen_tweet_id)
        last_seen = account.get("last_seen_tweet_id")
        if last_seen:
            tweets = [t for t in tweets if t["id"] > last_seen]

        if not tweets:
            return 0

        # Update cursor to newest tweet
        newest_id = max(t["id"] for t in tweets)
        update_target_last_seen(account_id, newest_id)

        self.stats["new_tweets"] += len(tweets)
        print(f"[Engagement] @{username}: {len(tweets)} new tweet(s)")

        # Check per-account daily limit (priority 0 = unlimited, reply to everything)
        is_super_high = account.get("priority", 2) == 0
        if is_super_high:
            remaining = 999
        else:
            max_per_account = cfg.get("max_replies_per_account_per_day", 3)
            account_today = get_engagement_replies_today_for_account(account_id)
            remaining = max_per_account - account_today

        reply_window_hours = cfg.get("reply_window_hours", 6)
        reply_count = 0

        for tweet in tweets:
            if remaining <= 0:
                break

            # Skip if already replied
            if tweet_already_replied(tweet["id"]):
                continue

            # Skip if tweet is too old
            if not self._is_within_reply_window(tweet.get("created_at"), reply_window_hours):
                continue

            # SAFEGUARD: Skip toxic tweets (don't associate our account with harmful content)
            tweet_toxicity = check_toxicity(tweet["text"])
            if tweet_toxicity["is_toxic"]:
                print(f"[Engagement] SKIPPED toxic tweet from @{username}: {tweet_toxicity['reason']}")
                continue

            # Generate reply
            try:
                reply = self._generate_and_score_reply(
                    tweet, account_id, username, account.get("reply_style", "mixed"),
                    cfg, quality_config,
                )
                if reply:
                    reply_count += 1
                    remaining -= 1
            except Exception as e:
                print(f"[Engagement] Error generating reply for tweet {tweet['id']}: {e}")
                self.stats["errors"] += 1

        return reply_count

    def _generate_and_score_reply(self, tweet, target_account_id, target_username, reply_style, cfg, quality_config):
        """Generate, score, and save a reply for a tweet."""
        max_length = cfg.get("max_reply_length", 280)
        auto_reject_below = cfg.get("auto_reject_below", 35.0)

        # Generate 3 candidates
        candidates = generate_reply(
            tweet["text"], target_username, reply_style, max_length,
        )

        if not candidates:
            print(f"[Engagement] No candidates generated for tweet {tweet['id']}")
            return None

        # Pick the best
        best = pick_best_reply(tweet["text"], candidates, quality_config)
        if not best:
            return None

        score = best.get("quality_score", 0)
        score_details = best.get("score_details", {})
        score_json = json.dumps(score_details, default=str)
        auto_approve_above = cfg.get("auto_approve_above", 60.0)

        # Determine reject reason if applicable
        reject_reason = None
        status = "approved"

        if score_details.get("blocked"):
            reject_reason = score_details.get("blocked_reason", "Contenu offensant")
            status = "rejected"
        elif score < auto_reject_below:
            # Build a descriptive reason
            reasons = []
            ai = score_details.get("ai", {})
            if ai.get("score", 100) < 30:
                reasons.append("Trop artificiel (AI-like)")
            readability = score_details.get("readability", {})
            if readability.get("score", 100) < 30:
                reasons.append("Lisibilite insuffisante")
            relevance = score_details.get("relevance", {})
            if relevance.get("score", 100) < 30:
                reasons.append("Hors sujet")
            duplicate = score_details.get("duplicate", {})
            if duplicate.get("score", 100) < 30:
                reasons.append("Trop similaire a une reply existante")
            reject_reason = "; ".join(reasons) if reasons else f"Score trop bas ({score:.0f})"
            status = "rejected"
        elif score < auto_approve_above:
            status = "pending_review"

        # Calculate reply delay (anti-spam) — only for approved
        reply_after = None
        if status == "approved":
            delay_min = cfg.get("reply_delay_min_minutes", 2)
            delay_max = cfg.get("reply_delay_max_minutes", 15)
            delay = random.randint(delay_min, delay_max)
            reply_after = (datetime.utcnow() + timedelta(minutes=delay)).isoformat()

        # Save to DB (all replies, including rejected for traceability)
        reply_id = save_engagement_reply(
            target_account_id=target_account_id,
            target_username=target_username,
            original_tweet_id=tweet["id"],
            original_tweet_text=tweet["text"],
            original_tweet_url=tweet.get("url", ""),
            reply_content=best["content"],
            reply_style=best.get("style", "mixed"),
            quality_score=score,
            score_details=score_json,
            reply_after=reply_after,
            status=status,
            reject_reason=reject_reason,
        )

        if reply_id:
            if status == "rejected":
                print(f"[Engagement] Reply REJECTED (score={score:.1f}, reason={reject_reason}): {best['content'][:60]}...")
            elif status == "pending_review":
                print(f"[Engagement] Reply pending review (score={score:.1f}): {best['content'][:80]}...")
            else:
                self.stats["replies_generated"] += 1
                print(f"[Engagement] Reply queued (score={score:.1f}, delay={delay}min): {best['content'][:80]}...")

        return reply_id

    # --- Phase 2: Post ready replies ---

    def _post_ready_replies(self):
        """Post all approved replies whose delay has passed."""
        # Check kill switch before posting
        killed, reason = usage_limiter._check_kill_switch()
        if killed:
            print(f"[Engagement] {reason} - skipping reply posting.")
            return

        ready = get_ready_engagement_replies()
        for reply in ready:
            if self._stop_event.is_set():
                break
            try:
                tweet_id = twitter_reader.reply_to_tweet(reply["original_tweet_id"], reply["reply_content"])
                mark_engagement_reply_posted(reply["id"], tweet_id)
                self.stats["replies_posted"] += 1
                print(f"[Engagement] Posted reply to @{reply['target_username']}: {reply['reply_content'][:60]}...")
            except Exception as e:
                error_msg = str(e).lower()
                if "403" in error_msg or "not allowed" in error_msg or "forbidden" in error_msg:
                    # Author restricted replies — skip, don't retry
                    update_engagement_reply_status(reply["id"], "skipped")
                    print(f"[Engagement] Skipped reply #{reply['id']} (replies restricted by @{reply['target_username']})")
                else:
                    print(f"[Engagement] Failed to post reply #{reply['id']}: {e}")
                    self.stats["errors"] += 1

    # --- Helpers ---

    def _is_within_active_hours(self, cfg):
        tz_name = cfg.get("timezone", "Europe/Paris")
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone("Europe/Paris")

        now_local = datetime.now(tz)
        start = cfg.get("active_start_hour", 8)
        end = cfg.get("active_end_hour", 23)
        return start <= now_local.hour < end

    def _is_within_reply_window(self, created_at_str, window_hours):
        if not created_at_str:
            return True  # If no date, assume it's recent enough
        try:
            # twikit returns dates like "Wed Oct 10 20:19:24 +0000 2018"
            created = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
            now = datetime.now(created.tzinfo)
            age = now - created
            return age.total_seconds() < window_hours * 3600
        except (ValueError, TypeError):
            return True  # Can't parse, let it through


# Global singleton
engagement_monitor = EngagementMonitor()
