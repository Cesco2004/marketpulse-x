"""Fetch trending posts from Reddit via public JSON endpoints (no auth needed)."""

import requests

DEFAULT_SUBREDDITS = [
    "technology",
    "artificial",
    "Futurology",
    "singularity",
    "startups",
]

USER_AGENT = "QuantumBrief/1.0 (content aggregator)"

# Thresholds
MIN_UPVOTES = 100


def fetch_reddit(subreddits=None, limit=25, min_upvotes=MIN_UPVOTES):
    """Fetch top daily posts from configured subreddits.

    Returns list of article dicts compatible with the pipeline.
    """
    subreddits = subreddits or DEFAULT_SUBREDDITS
    headers = {"User-Agent": USER_AGENT}
    articles = []

    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/top/.json?t=day&limit={limit}"
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})

                # Skip stickied, self-posts without substance, and low-score posts
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

                # Prefer external link; fall back to reddit permalink
                link = post_url if post_url and not post_url.startswith("https://www.reddit.com") else f"https://www.reddit.com{permalink}"

                # Build a useful summary from selftext or title (never just upvote counts)
                if selftext and len(selftext.strip()) > 30:
                    summary = selftext
                else:
                    summary = title  # Title is the content for link posts

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
