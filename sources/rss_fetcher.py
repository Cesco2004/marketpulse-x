import re
import feedparser

import config
from storage.database import update_article_score, update_article_stage


def fetch_all_feeds():
    """Fetch from hardcoded config.RSS_FEEDS (legacy fallback)."""
    all_articles = []

    for feed_config in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])

            for entry in feed.entries[:10]:
                summary = ""
                if hasattr(entry, "summary"):
                    summary = entry.summary[:500]
                elif hasattr(entry, "description"):
                    summary = entry.description[:500]

                summary = re.sub(r"<[^>]+>", "", summary).strip()

                article = {
                    "title": entry.get("title", "No title"),
                    "url": entry.get("link", ""),
                    "source": feed_config["name"],
                    "summary": summary,
                    "priority": feed_config["priority"],
                    "published": entry.get("published", ""),
                    "topic_weight": 1.0,
                }
                all_articles.append(article)

        except Exception as e:
            print(f"  Error fetching {feed_config['name']}: {e}")

    return all_articles


def fetch_all_feeds_from_db():
    """Fetch from database-configured feeds (enabled only)."""
    from storage.database import get_rss_feeds

    feeds = get_rss_feeds(enabled_only=True)
    if not feeds:
        return []

    all_articles = []
    for feed_config in feeds:
        try:
            feed = feedparser.parse(feed_config["url"])

            for entry in feed.entries[:10]:
                summary = ""
                if hasattr(entry, "summary"):
                    summary = entry.summary[:500]
                elif hasattr(entry, "description"):
                    summary = entry.description[:500]

                summary = re.sub(r"<[^>]+>", "", summary).strip()

                article = {
                    "title": entry.get("title", "No title"),
                    "url": entry.get("link", ""),
                    "source": feed_config["name"],
                    "summary": summary,
                    "priority": feed_config["priority"],
                    "published": entry.get("published", ""),
                    "topic_weight": feed_config.get("topic_weight", 1.0),
                }
                all_articles.append(article)

        except Exception as e:
            print(f"  Error fetching {feed_config['name']}: {e}")

    return all_articles


def score_article(article):
    """Score an article and return (score, matched_keywords)."""
    text = (article["title"] + " " + article["summary"]).lower()
    matched = []
    for keyword in config.HIGH_IMPACT_KEYWORDS:
        if keyword.lower() in text:
            matched.append(keyword)
    score = len(matched)
    # Bonus for source priority (priority 1 = +2, priority 2 = +1)
    score += 3 - article["priority"]
    # Apply topic weight multiplier from feed config
    topic_weight = article.get("topic_weight", 1.0)
    score = int(score * topic_weight)
    return score, matched


def keyword_prefilter(articles, count=10):
    """Pre-filter articles by keyword score. Persist scores to DB."""
    scored = []
    for a in articles:
        score, matched = score_article(a)
        a["keyword_score"] = score
        a["matched_keywords"] = matched
        scored.append((score, a))

        # Persist score to DB
        if a.get("url"):
            update_article_score(a["url"], score, matched, stage="prefiltered" if score > 0 else "fetched")

    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for score, article in scored:
        title_key = article["title"].lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(article)

    # Mark top N as prefiltered
    result = unique[:count]
    for a in result:
        if a.get("url"):
            update_article_score(a["url"], a["keyword_score"], a["matched_keywords"], "prefiltered")

    return result


def format_articles_for_prompt(articles):
    """Format selected articles into a string for the LLM prompt."""
    formatted = []
    for i, article in enumerate(articles, 1):
        text = f"{i}. [{article['source']}] {article['title']}"
        if article.get("summary"):
            text += f"\n   Summary: {article['summary'][:300]}"
        formatted.append(text)

    return "\n\n".join(formatted)
