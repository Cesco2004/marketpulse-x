"""Fetch trending stories from the HackerNews API (free, no auth)."""

import requests

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

# Thresholds for quality filtering
MIN_SCORE = 50
MIN_COMMENTS = 10


def fetch_hackernews(limit=30, min_score=MIN_SCORE, min_comments=MIN_COMMENTS):
    """Fetch top HN stories filtered by score and comment count.

    Returns list of article dicts compatible with the pipeline.
    """
    try:
        resp = requests.get(HN_TOP_URL, timeout=15)
        resp.raise_for_status()
        story_ids = resp.json()[:limit]
    except Exception as e:
        print(f"  Error fetching HN top stories: {e}")
        return []

    articles = []
    for story_id in story_ids:
        try:
            item = requests.get(HN_ITEM_URL.format(story_id), timeout=10).json()
            if not item or item.get("type") != "story":
                continue

            score = item.get("score", 0)
            comments = item.get("descendants", 0)

            if score < min_score or comments < min_comments:
                continue

            title = item.get("title", "")
            url = item.get("url", f"https://news.ycombinator.com/item?id={story_id}")

            articles.append({
                "title": title,
                "url": url,
                "source": "HackerNews",
                "summary": title,  # HN stories are link-posts; title IS the content
                "priority": 1 if score >= 200 else 2,
                "published": "",
                "topic_weight": 1.0,
                "engagement_score": score,
                "comment_count": comments,
            })
        except Exception:
            continue

    return articles
