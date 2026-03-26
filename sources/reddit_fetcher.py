"""Fetch trending posts from Reddit via OAuth API (works from cloud servers).

Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env.
Create a free app at https://www.reddit.com/prefs/apps (type: script).
"""

import os
from datetime import datetime, timedelta

import requests

DEFAULT_SUBREDDITS = [
    "technology",
    "artificial",
    "Futurology",
    "singularity",
    "startups",
]

BOT_NAME = "QuantumBrief"
MIN_UPVOTES = 100

# Module-level token cache
_token_cache = {"access_token": None, "expires_at": None}


def _get_oauth_token():
    """Get Reddit OAuth token using client_credentials (app-only, no user login).

    Caches token for 50 minutes (expires at 60).
    """
    # Return cached token if still valid
    if _token_cache["access_token"] and _token_cache["expires_at"] and datetime.now() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")

    if not client_id:
        return None

    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": f"{BOT_NAME}/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = datetime.now() + timedelta(seconds=3000)  # 50 min
        return _token_cache["access_token"]
    except Exception as e:
        print(f"  Reddit OAuth failed: {e}")
        return None


def _fetch_subreddit_oauth(sub, token, limit=25):
    """Fetch top posts from a subreddit using OAuth (oauth.reddit.com)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": f"{BOT_NAME}/1.0",
    }
    url = f"https://oauth.reddit.com/r/{sub}/top.json"
    resp = requests.get(url, headers=headers, params={"limit": limit, "t": "day"}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _fetch_subreddit_public(sub, limit=25):
    """Fallback: fetch from public JSON endpoint (works from non-cloud IPs)."""
    headers = {"User-Agent": f"{BOT_NAME}/1.0 (content aggregator)"}
    url = f"https://old.reddit.com/r/{sub}/top/.json?t=day&limit={limit}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 403:
        url = f"https://www.reddit.com/r/{sub}/top/.json?t=day&limit={limit}"
        resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_reddit(subreddits=None, limit=25, min_upvotes=MIN_UPVOTES):
    """Fetch top daily posts from configured subreddits.

    Uses OAuth if credentials are set (works from cloud servers),
    falls back to public JSON endpoint otherwise.

    Returns list of article dicts compatible with the pipeline.
    """
    subreddits = subreddits or DEFAULT_SUBREDDITS
    token = _get_oauth_token()
    articles = []

    for sub in subreddits:
        try:
            if token:
                data = _fetch_subreddit_oauth(sub, token, limit)
            else:
                data = _fetch_subreddit_public(sub, limit)

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})

                if post_data.get("stickied"):
                    continue
                upvotes = post_data.get("ups", 0)
                if upvotes < min_upvotes:
                    continue

                title = post_data.get("title", "")
                post_url = post_data.get("url", "")
                selftext = post_data.get("selftext", "")[:500]
                num_comments = post_data.get("num_comments", 0)
                permalink = post_data.get("permalink", "")

                link = post_url if post_url and not post_url.startswith("https://www.reddit.com") else f"https://www.reddit.com{permalink}"

                if selftext and len(selftext.strip()) > 30:
                    summary = selftext
                else:
                    summary = title

                articles.append({
                    "title": title,
                    "url": link,
                    "source": f"Reddit r/{sub}",
                    "summary": summary[:500],
                    "priority": 1 if upvotes >= 500 else 2,
                    "published": "",
                    "topic_weight": 1.0,
                    "engagement_score": upvotes,
                    "comment_count": num_comments,
                })

        except Exception as e:
            print(f"  Error fetching r/{sub}: {e}")
            continue

    return articles
