"""Background metrics collector that scrapes tweet engagement and account stats via twikit."""

import random
import threading
import traceback
from datetime import datetime

from storage.database import (
    get_analytics_config,
    update_analytics_config,
    get_posted_tweets_with_ids,
    save_tweet_metrics,
    save_account_metrics,
)
from engagement.twitter_reader import twitter_reader, twikit_lock


class MetricsCollector:
    """Background collector that periodically scrapes tweet metrics and account stats."""

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self.stats = {
            "collections": 0,
            "tweets_scraped": 0,
            "errors": 0,
            "last_collection": None,
        }

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return
        self._stop_event.clear()
        update_analytics_config(is_enabled=1)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[Analytics] Metrics collector started.")

    def stop(self):
        self._stop_event.set()
        update_analytics_config(is_enabled=0)
        print("[Analytics] Metrics collector stopped.")

    def collect_once(self):
        """Run a single collection cycle manually. Returns stats dict."""
        try:
            self._collect_all()
        except Exception as e:
            print(f"[Analytics] Collection error: {e}")
            traceback.print_exc()
            self.stats["errors"] += 1
        self.stats["collections"] += 1
        self.stats["last_collection"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        return dict(self.stats)

    def _run_loop(self):
        """Main loop: collect, sleep for interval, repeat."""
        print("[Analytics] Collector loop thread started.")
        try:
            while not self._stop_event.is_set():
                cfg = get_analytics_config()
                if not cfg.get("is_enabled"):
                    print("[Analytics] is_enabled=0, stopping loop.")
                    break

                try:
                    self._collect_all()
                except Exception as e:
                    print(f"[Analytics] Collection error: {e}")
                    traceback.print_exc()
                    self.stats["errors"] += 1

                self.stats["collections"] += 1
                self.stats["last_collection"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

                interval = max(cfg.get("collection_interval_hours", 12), 1) * 3600
                print(f"[Analytics] Collection done. Next in {interval // 3600}h.")
                self._stop_event.wait(timeout=interval)
        except Exception as e:
            print(f"[Analytics] FATAL loop error: {e}")
            traceback.print_exc()
        finally:
            print("[Analytics] Collector loop thread exited.")

        if not self._stop_event.is_set():
            update_analytics_config(is_enabled=0)

    def _collect_all(self):
        """Run both tweet metrics and account metrics collection."""
        with twikit_lock:
            try:
                twitter_reader.ensure_login()
            except Exception as e:
                print(f"[Analytics] Login failed: {e}, invalidating session and retrying...")
                twitter_reader.invalidate_session()
                try:
                    twitter_reader.ensure_login()
                except Exception as e2:
                    print(f"[Analytics] Login retry failed: {e2}, skipping collection.")
                    self.stats["errors"] += 1
                    return

            self._collect_tweet_metrics()
            self._collect_account_metrics()

    def _collect_tweet_metrics(self):
        """Scrape engagement metrics for all recently posted tweets."""
        cfg = get_analytics_config()
        lookback = cfg.get("lookback_days", 30)
        tweets = get_posted_tweets_with_ids(days=lookback)

        if not tweets:
            print("[Analytics] No posted tweets to scrape.")
            return

        scraped = 0
        for tweet_data in tweets:
            if self._stop_event.is_set():
                break
            tweet_id = tweet_data["x_tweet_id"]
            post_id = tweet_data["id"]
            try:
                tweet = twitter_reader.client.get_tweet_by_id(tweet_id)
                likes = int(tweet.favorite_count or 0)
                retweets = int(tweet.retweet_count or 0)
                replies = int(tweet.reply_count or 0)
                quotes = int(tweet.quote_count or 0)
                views = int(tweet.view_count or 0)
                bookmarks = int(getattr(tweet, "bookmark_count", 0) or 0)

                save_tweet_metrics(tweet_id, post_id, likes, retweets, replies, quotes, views, bookmarks)
                scraped += 1
            except Exception as e:
                print(f"[Analytics] Failed to scrape tweet {tweet_id}: {e}")
                self.stats["errors"] += 1

            # Rate limiting: random delay between requests
            import time
            time.sleep(random.uniform(2, 3.5))

        self.stats["tweets_scraped"] = scraped
        print(f"[Analytics] Scraped {scraped}/{len(tweets)} tweets.")

    def _collect_account_metrics(self):
        """Scrape account follower/following counts."""
        cfg = get_analytics_config()
        username = cfg.get("own_username", "").strip().lstrip("@")
        if not username:
            print("[Analytics] No own_username configured, skipping account metrics.")
            return

        try:
            user = twitter_reader.client.get_user_by_screen_name(username)
            save_account_metrics(
                followers=int(user.followers_count or 0),
                following=int(user.following_count or 0),
                tweets_count=int(user.statuses_count or 0),
                listed_count=int(user.listed_count or 0),
            )
            print(f"[Analytics] Account @{username}: {user.followers_count} followers, {user.following_count} following.")
        except Exception as e:
            print(f"[Analytics] Failed to scrape account metrics: {e}")
            self.stats["errors"] += 1


# Module-level singleton
metrics_collector = MetricsCollector()
