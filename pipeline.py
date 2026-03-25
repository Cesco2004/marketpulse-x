"""
Shared pipeline logic used by both CLI (main.py) and dashboard routes.
Returns structured data instead of printing.
"""

import json

from storage.database import (
    save_articles,
    save_posts,
    get_approved_posts,
    mark_as_posted,
    get_quality_config,
    get_image_config,
    update_post_status,
)
from sources.rss_fetcher import fetch_all_feeds, fetch_all_feeds_from_db, keyword_prefilter, format_articles_for_prompt
from generator.mistral_generator import rank_articles, generate_posts, get_batch_id
from publisher.x_publisher import post_tweet
from scoring.quality_scorer import score_post
from limiter import UsageLimitReached


def run_fetch_pipeline():
    """Fetch RSS → keyword score → Mistral rank → generate posts → score → find images.
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

    # Step 1: Fetch RSS (from DB feeds if available, fallback to config)
    try:
        articles = fetch_all_feeds_from_db()
        if not articles:
            articles = fetch_all_feeds()
        result["articles_fetched"] = len(articles)
    except Exception as e:
        result["errors"].append(f"RSS fetch failed: {e}")
        return result

    if not articles:
        result["errors"].append("No articles found from RSS feeds.")
        return result

    # Save articles to DB (returns count + list of new URLs)
    saved, new_urls = save_articles(articles)
    result["articles_saved"] = saved

    # Short-circuit: no new articles → skip Mistral calls, save tokens
    if saved == 0:
        result["success"] = True
        result["skipped_reason"] = "no_new_articles"
        return result

    # Step 2: Keyword pre-filter (only new articles)
    new_url_set = set(new_urls)
    new_articles = [a for a in articles if a.get("url") in new_url_set]
    prefiltered = keyword_prefilter(new_articles, count=10)
    result["prefiltered"] = [
        {"title": a["title"], "source": a["source"], "score": a["keyword_score"], "keywords": a["matched_keywords"]}
        for a in prefiltered
    ]

    # Step 3: Mistral ranking
    try:
        articles_text = format_articles_for_prompt(prefiltered)
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
        result["errors"].append(f"Mistral ranking failed: {e}")
        selected = prefiltered[:5]

    # Step 4: Generate posts
    try:
        final_text = format_articles_for_prompt(selected)
        posts = generate_posts(final_text)

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
            })
            # Add this post to history so next posts in batch also check against it
            history.append({"content": post["content"]})

        # Step 6: Find images for posts
        source_ids = [a.get("url", "") for a in selected]
        _attach_images_to_posts(posts, source_ids)

        result["posts"] = posts

        if posts:
            batch_id = get_batch_id()
            save_posts(posts, batch_id, source_article_ids=source_ids)
            result["batch_id"] = batch_id
            result["success"] = True

            # Auto-reject low quality + auto-approve high quality
            auto_reject = quality_config.get("auto_reject_below", 30.0)
            auto_approve = quality_config.get("auto_approve_above", 70.0)
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
            result["errors"].append("Mistral returned no posts.")
    except UsageLimitReached as e:
        result["errors"].append(f"Usage limit: {e}")
    except Exception as e:
        result["errors"].append(f"Post generation failed: {e}")

    return result


def _attach_images_to_posts(posts, source_ids):
    """Find and score images for posts. Modifies posts in-place."""
    try:
        from images.fetcher import find_image_for_post, should_attach_image, download_image
        from images.scorer import score_image
    except ImportError:
        return  # images module not installed yet

    image_config = get_image_config()
    if not image_config.get("images_enabled", 1):
        return

    min_score = image_config.get("min_image_score", 50.0)
    used_image_urls = set()  # Track used images to avoid duplicates

    # Distribute source articles across posts (round-robin instead of all-same)
    num_sources = len(source_ids)

    for i, post in enumerate(posts):
        if not should_attach_image(post.get("type", "")):
            continue

        try:
            # Give each post a different primary article to try first
            rotated_sources = []
            if num_sources > 0:
                start = i % num_sources
                rotated_sources = source_ids[start:] + source_ids[:start]

            img_url, img_source = find_image_for_post(
                post["content"], json.dumps(rotated_sources), image_config,
                exclude_urls=used_image_urls,
            )
            if not img_url:
                continue

            local_path = download_image(img_url, post.get("type", "0"))
            if not local_path:
                continue

            score_result = score_image(local_path, img_source)
            if score_result["score"] >= min_score:
                post["image_url"] = img_url
                post["image_path"] = local_path
                post["image_source"] = img_source
                post["image_score"] = score_result["score"]
                post["has_image"] = 1
                used_image_urls.add(img_url)  # Don't reuse this image
        except Exception:
            continue  # Skip image on any error, don't break pipeline


def publish_post(post):
    """Publish a single post with optional image. Returns (tweet_id, has_image).
    Accepts both dict and sqlite3.Row objects.
    """
    # Convert sqlite3.Row to dict if needed
    if not isinstance(post, dict):
        post = dict(post)

    media_ids = None

    # Upload image if present
    if post.get("has_image") and post.get("image_path"):
        try:
            from images.uploader import upload_and_cleanup
            media_ids = upload_and_cleanup(post["image_path"])
        except Exception:
            media_ids = None  # Fall back to text-only

    tweet_id = post_tweet(post["content"], media_ids=media_ids)
    return tweet_id, bool(media_ids)


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
