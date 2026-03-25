import re
import json
from datetime import datetime
from mistralai import Mistral

import config
from storage.database import update_article_rank, update_article_stage, log_api_usage
from limiter import UsageLimitReached
from limiter.usage_limiter import usage_limiter

MODEL = "mistral-small-latest"


def get_client():
    return Mistral(api_key=config.MISTRAL_API_KEY)


def rank_articles(articles_text, prefiltered_articles, count=10):
    """Use Mistral to rank pre-filtered articles. Persist ranks to DB."""
    allowed, reason = usage_limiter.check_mistral()
    if not allowed:
        raise UsageLimitReached(reason)

    client = get_client()
    prompt = config.RANKING_PROMPT.format(count=count, articles=articles_text)

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()

    # Log usage
    usage = response.usage
    if usage:
        cost = (usage.prompt_tokens * 0.000001) + (usage.completion_tokens * 0.000003)
        log_api_usage("mistral", "rank_articles", usage.prompt_tokens, usage.completion_tokens, cost)

    rankings = None
    try:
        match = re.search(r"\[[\d\s,]+\]", raw)
        if match:
            rankings = json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    if not rankings:
        rankings = list(range(1, 6))

    # Persist ranks to DB
    for rank_pos, article_num in enumerate(rankings[:5], 1):
        idx = article_num - 1
        if 0 <= idx < len(prefiltered_articles):
            article = prefiltered_articles[idx]
            if article.get("url"):
                stage = "selected" if rank_pos <= 5 else "ranked"
                update_article_rank(article["url"], rank_pos, stage)

    return rankings


def generate_posts(articles_text):
    """Generate 7 X posts from article summaries using Mistral."""
    allowed, reason = usage_limiter.check_mistral()
    if not allowed:
        raise UsageLimitReached(reason)

    client = get_client()

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

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    raw_text = response.choices[0].message.content

    # Log usage
    usage = response.usage
    if usage:
        cost = (usage.prompt_tokens * 0.000001) + (usage.completion_tokens * 0.000003)
        log_api_usage("mistral", "generate_posts", usage.prompt_tokens, usage.completion_tokens, cost)

    return parse_posts(raw_text)


def parse_posts(raw_text):
    """Parse LLM output into structured posts.

    Handles all Mistral output variations:
      TWEET 1 (Breaking): ...
      **TWEET 2**\n...
      🚀 TWEET 3: ...
      *TWEET 4 (Stat bomb):* ...
      1. ...
    """
    posts = []
    post_types = [
        "news",
        "news",
        "educational",
        "data",
        "opinion",
        "educational",
        "question",
    ]

    # Step 1: Normalize — strip markdown bold/italic around TWEET/POST labels
    # "**TWEET 5**"  → "TWEET 5"
    # "*TWEET 5*"    → "TWEET 5"
    normalized = re.sub(
        r"\*{1,2}((?:TWEET|POST)\s+\d+[^*]*?)\*{1,2}",
        r"\1",
        raw_text,
        flags=re.IGNORECASE,
    )

    # Step 2: Find all TWEET/POST label positions
    # Allows: emoji before, optional (Type) after, optional colon, ends at newline or colon+space
    label_re = re.compile(
        r"(?:^|\n)[^\n]*?(?:TWEET|POST)\s+(\d+)\s*(?:\([^)]*\))?\s*:?\s*(?:\n|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    labels = list(label_re.finditer(normalized))

    if labels:
        for i, match in enumerate(labels):
            start = match.end()
            end = labels[i + 1].start() if i + 1 < len(labels) else len(normalized)
            content = normalized[start:end].strip().strip('"').strip("*").strip()
            content = re.sub(r"\s*[\(\[]\d+\s*char(?:acter)?s?[\)\]]\s*$", "", content).strip()
            content = re.sub(r"\n?-{2,}\s*$", "", content).strip()  # Remove trailing --- separators
            if content and len(content) > 10:
                idx = i
                post_type = post_types[idx] if idx < len(post_types) else "other"
                posts.append({"content": content, "type": post_type})
        if posts:
            return posts

    # Step 3: Try inline label format (label and content on same line)
    # "TWEET 1 (Breaking): 🚨 BREAKING: Google just..."
    inline_re = re.compile(
        r"(?:^|\n)[^\n]*?(?:TWEET|POST)\s+(\d+)\s*(?:\([^)]*\))?\s*[:\-]\s*(.+?)(?=\n[^\n]*?(?:TWEET|POST)\s+\d+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = inline_re.findall(normalized)
    if matches:
        for i, (num, content) in enumerate(matches[:7]):
            cleaned = content.strip().strip('"').strip("*").strip()
            cleaned = re.sub(r"\s*[\(\[]\d+\s*char(?:acter)?s?[\)\]]\s*$", "", cleaned).strip()
            cleaned = re.sub(r"\n?-{2,}\s*$", "", cleaned).strip()
            if cleaned and len(cleaned) > 10:
                post_type = post_types[i] if i < len(post_types) else "other"
                posts.append({"content": cleaned, "type": post_type})
        if posts:
            return posts

    # Fallback: numbered list (1. ... 2. ...)
    pattern3 = r"(\d+)[.\)]\s+(.+?)(?=\n\d+[.\)]|\Z)"
    matches = re.findall(pattern3, raw_text, re.DOTALL)

    for i, (num, content) in enumerate(matches[:7]):
        cleaned = content.strip().strip('"').strip("*").strip()
        cleaned = re.sub(r"\s*[\(\[]\d+\s*char(?:acter)?s?[\)\]]\s*$", "", cleaned).strip()
        if cleaned and len(cleaned) > 10:
            post_type = post_types[i] if i < len(post_types) else "other"
            posts.append({"content": cleaned, "type": post_type})

    return posts


def get_batch_id():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
