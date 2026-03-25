import os
import threading

import twikit

import config

# Lock for thread-safe access to the twikit client (shared by EngagementMonitor and MetricsCollector)
twikit_lock = threading.Lock()

COOKIES_PATH = os.getenv(
    "TWIKIT_COOKIES_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "twikit_cookies.json"),
)


class TwitterReader:
    """Synchronous wrapper around twikit for reading Twitter timelines."""

    def __init__(self):
        self.client = twikit.Client(language="en-US")
        self._logged_in = False

    def ensure_login(self):
        if self._logged_in:
            return
        if os.path.exists(COOKIES_PATH):
            self.client.load_cookies(COOKIES_PATH)
            self._logged_in = True
            return
        if not config.X_USERNAME or not config.X_PASSWORD:
            raise RuntimeError(
                "twikit credentials missing. Set X_USERNAME, X_EMAIL, and X_PASSWORD in .env"
            )
        self.client.login(
            auth_info_1=config.X_USERNAME,
            auth_info_2=config.X_EMAIL or None,
            password=config.X_PASSWORD,
        )
        self.client.save_cookies(COOKIES_PATH)
        self._logged_in = True

    def get_user_id(self, username):
        """Resolve @username -> (user_id, display_name)."""
        self.ensure_login()
        username = username.lstrip("@").strip()
        user = self.client.get_user_by_screen_name(username)
        return user.id, user.name

    def get_recent_tweets(self, user_id, count=10):
        """Get recent original tweets (no RT, no replies) for a user."""
        self.ensure_login()
        result = self.client.get_user_tweets(
            user_id, tweet_type="Tweets", count=count
        )
        tweets = []
        for tweet in result:
            # Skip retweets
            if tweet.text.startswith("RT @"):
                continue
            tweets.append({
                "id": tweet.id,
                "text": tweet.text,
                "created_at": tweet.created_at,
                "url": f"https://x.com/i/status/{tweet.id}",
            })
        return tweets

    def reply_to_tweet(self, tweet_id, reply_text):
        """Post a reply to a tweet via twikit (bypasses API tier restrictions)."""
        self.ensure_login()
        tweet = self.client.create_tweet(text=reply_text, reply_to=tweet_id)
        return tweet.id

    def invalidate_session(self):
        """Remove saved cookies to force re-login next time."""
        self._logged_in = False
        if os.path.exists(COOKIES_PATH):
            os.remove(COOKIES_PATH)


# Module-level singleton
twitter_reader = TwitterReader()
