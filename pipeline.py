"""
Shared pipeline logic used by both CLI (main.py) and dashboard routes.
Returns structured data instead of printing.
"""

import json

import config
from storage.database import (
    save_articles,
    save_posts,
    get_approved_posts,
    mark_as_posted,
    get_quality_config,
    get_image_config,
    update_post_status,
    expire_stale_posts,
)
from sources.aggregator import fetch_all_sources, format_financial_data_for_prompt
from sources.correlation_engine import detect_narratives
from generator.provider_router import rank_articles, generate_posts
from generator.mistral_generator import get_batch_id
from publisher.x_publisher import post_tweet, publish_thread
from scoring.quality_scorer import score_post
from limiter import UsageLimitReached


def run_fetch_pipeline():
    """Fetch financial data → rank → generate posts → score → generate charts.
    Returns a dict with results at each stage."""

    result = {
        "success": False,
        "articles_fetched": 0,
        "articles_saved": 0,
        "skipped_reason": None,
        "prefiltered": [],
        "rankings": [],
        "selected": [],
        "posts": [],
        "batch_id": None,
        "auto_approved": 0,
        "auto_rejected": 0,
        "needs_review": 0,
        "errors": [],
    }

    # Step 0: Expire stale tweets from previous fetch cycles (older than 4 hours)
    try:
        expired_count = expire_stale_posts(max_age_hours=4)
        if expired_count:
            result["expired_stale"] = expired_count
    except Exception:
        pass  # Non-fatal

    # Step 1: Fetch from all financial sources (Polymarket + CoinGecko + Yahoo Finance)
    try:
        articles = fetch_all_sources()
        result["articles_fetched"] = len(articles)
    except Exception as e:
        result["errors"].append(f"Source fetch failed: {e}")
        return result

    if not articles:
        result["errors"].append("No market data found from financial sources.")
        return result

    # Save articles to DB (returns count + list of new URLs)
    saved, new_urls = save_articles(articles)
    result["articles_saved"] = saved

    # Step 1b: Detect cross-source narratives (correlation engine)
    try:
        narratives = detect_narratives(articles)
        result["narratives"] = [
            {"pattern": n["pattern_type"], "label": n["label"], "strength": n["strength"]}
            for n in narratives
        ]
    except Exception as e:
        narratives = []
        result["errors"].append(f"Narrative detection failed (non-fatal): {e}")

    # For financial data, we always process (data changes every fetch)
    # Unlike RSS, market data is time-sensitive and always relevant

    # Budget-aware: skip generation if auto-throttle says so
    try:
        from limiter.budget_forecaster import get_throttle_recommendations
        throttle = get_throttle_recommendations("mistral")
        if throttle.get("skip_post_generation"):
            result["success"] = True
            result["skipped_reason"] = f"budget_throttle: {throttle['reason']}"
            return result
    except Exception:
        pass

    # Step 2: Pre-filter (sort by significance, take top movers)
    # Financial data is already sorted by significance from the aggregator
    prefiltered = articles[:10]  # Top 10 most significant data points
    result["prefiltered"] = [
        {"title": a["title"], "source": a["source"], "score": a.get("keyword_score", 0),
         "keywords": a.get("matched_keywords", [])}
        for a in prefiltered
    ]

    # Step 3: LLM ranking
    try:
        articles_text = format_financial_data_for_prompt(prefiltered, narratives=narratives)
        rankings = rank_articles(articles_text, prefiltered, count=len(prefiltered))
        result["rankings"] = rankings

        # Build selected articles list
        selected = []
        for rank in rankings[:5]:
            idx = rank - 1
            if 0 <= idx < len(prefiltered):
                selected.append(prefiltered[idx])

        if len(selected) < 3:
            selected = prefiltered[:5]

        result["selected"] = [
            {"title": a["title"], "source": a["source"]}
            for a in selected
        ]
    except UsageLimitReached as e:
        result["errors"].append(f"Usage limit: {e}")
        return result
    except Exception as e:
        result["errors"].append(f"LLM ranking failed: {e}")
        selected = prefiltered[:5]

    # Step 4: Generate posts
    try:
        final_text = format_financial_data_for_prompt(selected, narratives=narratives)
        posts = generate_posts(final_text)

        # Step 4b: Append source link + disclaimer to each post
        disclaimer = getattr(config, "DISCLAIMER", "\n\nNot financial advice.")
        for post in posts:
            content = post["content"].rstrip()
            # Don't double-add disclaimer
            if "not financial advice" not in content.lower():
                # Find the best matching source URL for this tweet
                source_url = _find_best_source_url(content, selected)
                if source_url:
                    content = content + "\n\n" + source_url
                content = content + "\n\n" + "Not financial advice."
            post["content"] = content

        # Step 4c: Filter out posts that are too long or too short for Twitter
        # Twitter counts URLs as 23 chars regardless of actual length
        posts = [p for p in posts if 20 < _twitter_length(p["content"]) <= 300]

        # Step 5: Score each post (with duplicate detection)
        quality_config = get_quality_config()

        # Build history: recent posted + approved + already-scored posts in this batch
        from storage.database import get_posted_posts, get_approved_posts, get_pending_posts
        history = []
        for p in get_posted_posts()[:50]:   # Last 50 posted tweets
            history.append({"content": p["content"]})
        for p in get_approved_posts():
            history.append({"content": p["content"]})
        for p in get_pending_posts():
            history.append({"content": p["content"]})

        for post in posts:
            scores = score_post(post["content"], quality_config, existing_posts=history)
            post["quality_score"] = scores["overall"]
            post["ai_score"] = scores["ai"]["score"]
            post["readability_score"] = scores["readability"]["score"]
            post["emoji_score"] = scores["emoji"]["score"]
            post["score_details"] = json.dumps({
                "penalties": scores["penalties"],
                "auto_reject": scores["auto_reject"],
                "below_minimum": scores["below_minimum"],
                "substance": scores.get("substance", {}).get("score"),
                "variety": scores.get("variety", {}).get("score"),
                "tone": scores.get("tone", {}).get("score"),
                "data_accuracy": scores.get("data_accuracy", {}).get("score"),
            })
            # Add this post to history so next posts in batch also check against it
            history.append({"content": post["content"]})

        # Step 6: Generate chart images for posts
        source_ids = [a.get("url", "") for a in selected]
        _attach_images_to_posts(posts, source_ids)

        result["posts"] = posts

        if posts:
            batch_id = get_batch_id()
            save_posts(posts, batch_id, source_article_ids=source_ids)
            result["batch_id"] = batch_id
            result["success"] = True

            # Auto-reject low quality + auto-approve high quality
            auto_reject = quality_config.get("auto_reject_below", 25.0)
            auto_approve = quality_config.get("auto_approve_above", 68.0)
            from storage.database import get_pending_posts
            pending = get_pending_posts()
            auto_rejected_count = 0
            auto_approved_count = 0
            for p in pending:
                if p["quality_score"] is not None:
                    if p["quality_score"] < auto_reject:
                        update_post_status(p["id"], "rejected")
                        auto_rejected_count += 1
                    elif p["quality_score"] >= auto_approve:
                        update_post_status(p["id"], "approved")
                        auto_approved_count += 1
            result["auto_rejected"] = auto_rejected_count
            result["auto_approved"] = auto_approved_count
            result["needs_review"] = len(posts) - auto_approved_count - auto_rejected_count
        else:
            result["errors"].append("LLM returned no posts.")
    except UsageLimitReached as e:
        result["errors"].append(f"Usage limit: {e}")
    except Exception as e:
        result["errors"].append(f"Post generation failed: {e}")

    return result


def _attach_images_to_posts(posts, source_ids):
    """Generate chart images for posts. Modifies posts in-place."""
    try:
        from images.fetcher import find_image_for_post, should_attach_image
    except ImportError:
        return  # images module not installed yet

    image_config = get_image_config()
    if not image_config.get("images_enabled", 1):
        return

    for post in posts:
        if not should_attach_image(post.get("type", "")):
            continue

        try:
            # Use chart_hint from LLM output (CHART_DATA line) if available
            chart_hint = post.get("chart_hint") or post.get("image_hint")

            img_path, img_source = find_image_for_post(
                post["content"],
                chart_hint=chart_hint,
                chart_data_json=post.get("chart_data_json"),
            )
            if not img_path:
                continue

            post["image_url"] = img_path  # For charts, URL = local path
            post["image_path"] = img_path
            post["image_source"] = img_source or "chart"
            post["image_score"] = 80.0  # Charts are always valid
            post["has_image"] = 1
        except Exception:
            continue  # Skip image on any error, don't break pipeline


def _find_best_source_url(tweet_text, articles):
    """Find the most relevant source URL for a tweet by matching tickers and keywords."""
    import re
    text_lower = tweet_text.lower()

    # Extract tickers from tweet ($BTC, $ETH, etc.)
    tickers = set(re.findall(r"\$([A-Z]{2,5})\b", tweet_text))

    best_url = None
    best_score = 0

    for article in articles:
        url = article.get("url", "")
        if not url or url.startswith("http") is False:
            continue

        score = 0
        # Match by ticker in article keywords or title
        for ticker in tickers:
            if ticker.lower() in article.get("title", "").lower():
                score += 10
            if ticker in article.get("matched_keywords", []):
                score += 5

        # Match by source name
        source = article.get("source", "").lower()
        if "polymarket" in text_lower and "polymarket" in source.lower():
            score += 8
        if "coingecko" in text_lower and "coingecko" in source.lower():
            score += 8
        if "yahoo" in text_lower and "yahoo" in source.lower():
            score += 8

        # Match by asset name in tweet
        title_words = article.get("title", "").lower().split()
        for word in title_words:
            if len(word) >= 4 and word in text_lower:
                score += 2

        if score > best_score:
            best_score = score
            best_url = url

    return best_url if best_score >= 2 else None


def _twitter_length(text):
    """Estimate Twitter character count (URLs count as 23 chars via t.co)."""
    import re
    # Replace URLs with 23-char placeholder
    no_urls = re.sub(r"https?://\S+", "x" * 23, text)
    return len(no_urls)


def publish_post(post):
    """Publish a single post with optional chart image, poll, or thread. Returns (tweet_id, has_image).
    Accepts both dict and sqlite3.Row objects.
    """
    # Convert sqlite3.Row to dict if needed
    if not isinstance(post, dict):
        post = dict(post)

    media_ids = None

    # Upload chart image if present
    if post.get("has_image") and post.get("image_path"):
        try:
            from images.uploader import upload_and_cleanup
            media_ids = upload_and_cleanup(post["image_path"])
        except Exception:
            media_ids = None  # Fall back to text-only

    # Handle poll tweets
    poll_options = None
    if post.get("poll_options"):
        try:
            poll_options = json.loads(post["poll_options"]) if isinstance(post["poll_options"], str) else post["poll_options"]
        except (json.JSONDecodeError, TypeError):
            poll_options = None

    tweet_id = post_tweet(post["content"], media_ids=media_ids, poll_options=poll_options)
    return tweet_id, bool(media_ids)


def publish_thread_posts(thread_posts):
    """Publish a group of posts that form a thread. Returns (first_tweet_id, has_image).

    Args:
        thread_posts: List of post dicts sorted by thread_position.
    """
    tweets = [p["content"] if isinstance(p, dict) else dict(p)["content"] for p in thread_posts]

    # Upload image for first tweet if available
    media_ids_list = [None] * len(tweets)
    first = thread_posts[0] if isinstance(thread_posts[0], dict) else dict(thread_posts[0])
    if first.get("has_image") and first.get("image_path"):
        try:
            from images.uploader import upload_and_cleanup
            media_ids_list[0] = upload_and_cleanup(first["image_path"])
        except Exception:
            pass

    tweet_ids = publish_thread(tweets, media_ids_list=media_ids_list)
    return tweet_ids[0] if tweet_ids else None, bool(media_ids_list[0])


def run_post_next():
    """Post the next approved tweet. Returns result dict."""
    posts = get_approved_posts()
    if not posts:
        return {"success": False, "error": "No approved posts in queue."}

    post = posts[0]
    try:
        tweet_id, has_image = publish_post(post)
        mark_as_posted(post["id"], tweet_id)
        return {
            "success": True,
            "post_id": post["id"],
            "tweet_id": tweet_id,
            "content": post["content"],
            "has_image": has_image,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
