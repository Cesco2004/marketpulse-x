"""Gemini-based content generation (free tier fallback).

Mirrors the mistral_generator contract: rank_articles(), generate_posts(),
moderation_check(). Uses Gemini 2.0 Flash via the google-generativeai SDK.
"""

import re
import json
from datetime import datetime

import google.generativeai as genai

import config
from storage.database import update_article_rank, log_api_usage
from limiter import UsageLimitReached
from limiter.usage_limiter import usage_limiter
from generator.mistral_generator import parse_posts  # reuse the robust parser

MODEL = "gemini-2.0-flash"


def _get_model():
    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel(MODEL)


def _log_usage(endpoint, response):
    """Log Gemini token usage to the api_usage table."""
    try:
        meta = response.usage_metadata
        input_tokens = getattr(meta, "prompt_token_count", 0) or 0
        output_tokens = getattr(meta, "candidates_token_count", 0) or 0
        # Gemini free tier has no cost, but log for tracking
        cost = 0.0
        log_api_usage("gemini", endpoint, input_tokens, output_tokens, cost)
    except Exception:
        pass


def rank_articles(articles_text, prefiltered_articles, count=10):
    """Use Gemini to rank pre-filtered articles. Persist ranks to DB."""
    allowed, reason = usage_limiter.check_gemini()
    if not allowed:
        raise UsageLimitReached(reason)

    model = _get_model()
    prompt = config.RANKING_PROMPT.format(count=count, articles=articles_text)

    response = model.generate_content(prompt, generation_config={"temperature": 0.3})
    raw = response.text.strip()

    _log_usage("rank_articles", response)

    rankings = None
    try:
        match = re.search(r"\[[\d\s,]+\]", raw)
        if match:
            rankings = json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    if not rankings:
        rankings = list(range(1, 6))

    for rank_pos, article_num in enumerate(rankings[:5], 1):
        idx = article_num - 1
        if 0 <= idx < len(prefiltered_articles):
            article = prefiltered_articles[idx]
            if article.get("url"):
                stage = "selected" if rank_pos <= 5 else "ranked"
                update_article_rank(article["url"], rank_pos, stage)

    return rankings


def generate_posts(articles_text):
    """Generate 7 X posts from article summaries using Gemini."""
    allowed, reason = usage_limiter.check_gemini()
    if not allowed:
        raise UsageLimitReached(reason)

    model = _get_model()

    # Inject emoji list from quality config
    try:
        from storage.database import get_quality_config
        import json as _json
        qconfig = get_quality_config()
        emoji_raw = qconfig.get("emoji_preferred", "[]")
        if isinstance(emoji_raw, str):
            emoji_list = ", ".join(_json.loads(emoji_raw))
        else:
            emoji_list = ", ".join(emoji_raw)
    except Exception:
        emoji_list = "\U0001f6a8, \U0001f525, \u26a1, \U0001f4a1, \U0001f680, \U0001f9e0, \U0001f440, \U0001f4c8, \U0001f4a5, \u2728"

    prompt = config.GENERATION_PROMPT.format(articles=articles_text, emoji_list=emoji_list)

    response = model.generate_content(prompt, generation_config={"temperature": 0.7})
    raw_text = response.text

    _log_usage("generate_posts", response)

    return parse_posts(raw_text)


def moderation_check(text):
    """Use Gemini for content moderation (free, saves Mistral tokens).

    Returns dict with is_toxic, reason, method.
    """
    allowed, reason = usage_limiter.check_gemini()
    if not allowed:
        return {"is_toxic": False, "reason": None, "method": None}

    model = _get_model()
    prompt = f"""Is this text hate speech, discriminatory, or toxic? Be strict.

Text: "{text}"

Reply EXACTLY: SAFE or TOXIC: [reason]"""

    response = model.generate_content(prompt, generation_config={"temperature": 0.0})
    _log_usage("moderation_check", response)

    answer = response.text.strip()

    if answer.upper().startswith("TOXIC"):
        reason = answer.split(":", 1)[1].strip() if ":" in answer else "Flagged by Gemini moderation"
        return {"is_toxic": True, "reason": reason, "method": "llm_gemini"}

    return {"is_toxic": False, "reason": None, "method": None}


def get_batch_id():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
