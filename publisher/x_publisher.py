import tweepy

import config
from storage.database import log_api_usage
from limiter import UsageLimitReached
from limiter.usage_limiter import usage_limiter


def get_client():
    """Create and return an authenticated X API v2 client."""
    client = tweepy.Client(
        consumer_key=config.X_API_KEY,
        consumer_secret=config.X_API_SECRET,
        access_token=config.X_ACCESS_TOKEN,
        access_token_secret=config.X_ACCESS_TOKEN_SECRET,
    )
    return client


def get_v1_api():
    """Create tweepy v1.1 API client for media uploads."""
    auth = tweepy.OAuth1UserHandler(
        config.X_API_KEY,
        config.X_API_SECRET,
        config.X_ACCESS_TOKEN,
        config.X_ACCESS_TOKEN_SECRET,
    )
    return tweepy.API(auth)


def post_tweet(content, media_ids=None, poll_options=None, poll_duration=1440):
    """Post a tweet with optional media/poll and return the tweet ID.

    Args:
        content: Tweet text.
        media_ids: Optional list of media IDs for image attachment.
        poll_options: Optional list of poll option strings (2-4 options).
        poll_duration: Poll duration in minutes (default: 24 hours).
    """
    allowed, reason = usage_limiter.check_twitter_post()
    if not allowed:
        raise UsageLimitReached(reason)

    client = get_client()
    kwargs = {"text": content}
    if media_ids:
        kwargs["media_ids"] = media_ids
    if poll_options and len(poll_options) >= 2:
        kwargs["poll_options"] = poll_options[:4]
        kwargs["poll_duration_minutes"] = poll_duration
    response = client.create_tweet(**kwargs)
    tweet_id = response.data["id"]
    log_api_usage("x", "create_tweet", cost_estimate=0.01)
    return tweet_id


def reply_to_tweet(tweet_id, reply_text):
    """Post a reply to a specific tweet. Returns the reply's tweet ID."""
    allowed, reason = usage_limiter.check_twitter_reply()
    if not allowed:
        raise UsageLimitReached(reason)

    client = get_client()
    response = client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
    reply_id = response.data["id"]
    log_api_usage("x", "create_reply", cost_estimate=0.01)
    return reply_id


def publish_thread(tweets, media_ids_list=None):
    """Post a series of tweets as a thread. Returns list of tweet IDs.

    Args:
        tweets: List of tweet text strings (first is the head tweet).
        media_ids_list: Optional list of media_ids (one per tweet, None for no media).
    """
    ids = []
    for i, text in enumerate(tweets):
        media = None
        if media_ids_list and i < len(media_ids_list):
            media = media_ids_list[i]

        if i == 0:
            tweet_id = post_tweet(text, media_ids=media)
        else:
            tweet_id = reply_to_tweet(ids[-1], text)
        ids.append(tweet_id)
    return ids


def verify_credentials():
    """Verify that the API credentials are working."""
    try:
        client = get_client()
        me = client.get_me()
        if me.data:
            print(f"  Authenticated as: @{me.data.username}")
            return True
    except Exception as e:
        print(f"  Auth error: {e}")
    return False
