"""Source aggregator: combines RSS, HackerNews, Reddit with cross-source dedup and boost."""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from sources.rss_fetcher import fetch_all_feeds, fetch_all_feeds_from_db
from sources.hackernews_fetcher import fetch_hackernews
from sources.reddit_fetcher import fetch_reddit


def _normalize_url(url):
    """Normalize URL for dedup: strip protocol, www, trailing slash, query params."""
    url = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    url = re.sub(r"\?.*$", "", url)
    return url.lower()


def _title_fingerprint(title):
    """Rough title fingerprint for cross-source dedup."""
    words = re.findall(r"[a-z]{4,}", title.lower())
    return frozenset(words)


def _get_subreddits_from_db():
    """Load subreddit config from content_sources table if available."""
    try:
        from storage.database import get_content_sources
        sources = get_content_sources("reddit")
        if sources:
            return [s["config_value"] for s in sources if s.get("config_value")]
    except Exception:
        pass
    return None


def fetch_all_sources():
    """Fetch from all enabled sources in parallel. Returns combined, deduplicated article list.

    Each article gets an extra 'source_count' field indicating how many sources reported it.
    Articles appearing in multiple sources get a virality boost.
    """
    all_articles = []
    subreddits = _get_subreddits_from_db()

    # Fetch from all sources in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}

        # RSS feeds (primary, always enabled)
        futures[executor.submit(_fetch_rss)] = "rss"
        # HackerNews
        futures[executor.submit(fetch_hackernews)] = "hackernews"
        # Reddit
        futures[executor.submit(fetch_reddit, subreddits)] = "reddit"

        for future in as_completed(futures):
            source_name = futures[future]
            try:
                articles = future.result()
                all_articles.extend(articles)
            except Exception as e:
                print(f"  Error from {source_name}: {e}")

    # Cross-source deduplication and boost
    return _deduplicate_and_boost(all_articles)


def _fetch_rss():
    """Fetch RSS from DB feeds, fallback to config."""
    articles = fetch_all_feeds_from_db()
    if not articles:
        articles = fetch_all_feeds()
    return articles


def _deduplicate_and_boost(articles):
    """Deduplicate articles across sources. Articles found in multiple sources get boosted.

    Dedup strategy:
    1. Exact URL match (after normalization)
    2. Title fingerprint overlap (Jaccard > 0.6)
    """
    # Group by normalized URL
    url_groups = {}
    for article in articles:
        norm_url = _normalize_url(article.get("url", ""))
        if norm_url in url_groups:
            url_groups[norm_url].append(article)
        else:
            url_groups[norm_url] = [article]

    # Second pass: merge groups with similar titles
    groups = list(url_groups.values())
    merged = []
    used = set()

    for i, group in enumerate(groups):
        if i in used:
            continue

        fp_i = _title_fingerprint(group[0]["title"])

        for j in range(i + 1, len(groups)):
            if j in used:
                continue
            fp_j = _title_fingerprint(groups[j][0]["title"])

            if fp_i and fp_j:
                intersection = fp_i & fp_j
                union = fp_i | fp_j
                similarity = len(intersection) / len(union) if union else 0
                if similarity > 0.6:
                    group.extend(groups[j])
                    used.add(j)

        merged.append(group)
        used.add(i)

    # Pick best article from each group, add source_count and cross-source boost
    result = []
    for group in merged:
        # Pick the article with the best engagement signal
        best = max(group, key=lambda a: a.get("engagement_score", 0))

        source_count = len(set(a.get("source", "") for a in group))
        best["source_count"] = source_count

        # Cross-source virality boost: multiply topic_weight
        if source_count >= 3:
            best["topic_weight"] = best.get("topic_weight", 1.0) * 2.0
        elif source_count >= 2:
            best["topic_weight"] = best.get("topic_weight", 1.0) * 1.5

        result.append(best)

    return result
