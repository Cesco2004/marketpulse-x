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


def _get_emoji_list():
    """Get emoji list from quality config or use defaults."""
    try:
        from storage.database import get_quality_config
        import json as _json
        qconfig = get_quality_config()
        emoji_raw = qconfig.get("emoji_preferred", "[]")
        if isinstance(emoji_raw, str):
            return ", ".join(_json.loads(emoji_raw))
        return ", ".join(emoji_raw)
    except Exception:
        return "\U0001f6a8, \U0001f525, \u26a1, \U0001f4a1, \U0001f680, \U0001f9e0, \U0001f440, \U0001f4c8, \U0001f4a5, \u2728"


def generate_posts(articles_text, template_prompt=None, template_meta=None):
    """Generate X posts from article summaries using Mistral.

    Args:
        articles_text: Formatted article text for the prompt.
        template_prompt: Optional specific template prompt (from GENERATION_TEMPLATES).
                         Falls back to config.GENERATION_PROMPT if None.
        template_meta: Optional dict with template metadata (is_thread, is_poll, etc.)
    """
    allowed, reason = usage_limiter.check_mistral()
    if not allowed:
        raise UsageLimitReached(reason)

    client = get_client()
    emoji_list = _get_emoji_list()

    if template_prompt:
        prompt = template_prompt.format(articles=articles_text, emoji_list=emoji_list)
    else:
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

    return parse_posts(raw_text, template_meta=template_meta)


def _extract_image_hint(text):
    """Extract all IMAGE_HINT lines from text and return (cleaned_text, first_hint)."""
    hints = re.findall(r"IMAGE_HINT:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    cleaned = re.sub(r"\n?IMAGE_HINT:\s*.+?(?:\n|$)", "\n", text, flags=re.IGNORECASE).strip()
    hint = hints[0].strip().strip("[]") if hints else None
    return cleaned, hint


def _clean_post_content(content):
    """Clean raw LLM output into tweet content."""
    content = content.strip().strip('"').strip("*").strip()
    content = re.sub(r"\s*[\(\[]\d+\s*char(?:acter)?s?[\)\]]\s*$", "", content).strip()
    content = re.sub(r"\n?-{2,}\s*$", "", content).strip()
    return content


def parse_posts(raw_text, template_meta=None):
    """Parse LLM output into structured posts.

    Handles multiple output formats:
      - TWEET 1 / POST 1 labels (multiline and inline)
      - THREAD_TWEET 1/2/3 labels (for threads)
      - POLL: + OPTION_A/B/C/D labels (for polls)
      - IMAGE_HINT: lines (extracted and stored separately)
      - Numbered lists as fallback
    """
    template_meta = template_meta or {}
    posts = []

    # --- POLL format ---
    if template_meta.get("is_poll"):
        poll_match = re.search(r"POLL:\s*(.+?)(?:\n|$)", raw_text, re.IGNORECASE)
        if poll_match:
            question = poll_match.group(1).strip()
            options = re.findall(r"OPTION_[A-D]:\s*(.+?)(?:\n|$)", raw_text, re.IGNORECASE)
            if options and len(options) >= 2:
                _, hint = _extract_image_hint(raw_text)
                posts.append({
                    "content": question,
                    "type": "poll",
                    "poll_options": json.dumps(options[:4]),
                    "image_hint": hint,
                })
                return posts

    # --- THREAD format ---
    if template_meta.get("is_thread"):
        thread_re = re.compile(
            r"THREAD_TWEET\s+(\d+)\s*:?\s*(.+?)(?=THREAD_TWEET\s+\d+|IMAGE_HINT|$)",
            re.IGNORECASE | re.DOTALL,
        )
        thread_matches = thread_re.findall(raw_text)
        if thread_matches:
            _, hint = _extract_image_hint(raw_text)
            thread_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_thread")
            for num_str, content in thread_matches:
                cleaned = _clean_post_content(content)
                if cleaned and len(cleaned) > 10:
                    posts.append({
                        "content": cleaned,
                        "type": "thread",
                        "thread_id": thread_id,
                        "thread_position": int(num_str),
                        "image_hint": hint if int(num_str) == 1 else None,
                    })
            if posts:
                return posts

    # --- Standard TWEET/POST format ---
    post_types = [
        "news", "news", "educational", "data", "opinion", "educational", "question",
    ]

    # Step 1: Normalize — strip markdown bold/italic around TWEET/POST labels
    normalized = re.sub(
        r"\*{1,2}((?:TWEET|POST)\s+\d+[^*]*?)\*{1,2}",
        r"\1",
        raw_text,
        flags=re.IGNORECASE,
    )

    # Step 2: Find all TWEET/POST label positions
    label_re = re.compile(
        r"(?:^|\n)[^\n]*?(?:TWEET|POST)\s+(\d+)\s*(?:\([^)]*\))?\s*:?\s*(?:\n|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    labels = list(label_re.finditer(normalized))

    if labels:
        for i, match in enumerate(labels):
            start = match.end()
            end = labels[i + 1].start() if i + 1 < len(labels) else len(normalized)
            raw_content = normalized[start:end]
            content, hint = _extract_image_hint(raw_content)
            content = _clean_post_content(content)
            if content and len(content) > 10:
                idx = i
                post_type = post_types[idx] if idx < len(post_types) else "other"
                posts.append({"content": content, "type": post_type, "image_hint": hint})
        if posts:
            return posts

    # Step 3: Try inline label format
    inline_re = re.compile(
        r"(?:^|\n)[^\n]*?(?:TWEET|POST)\s+(\d+)\s*(?:\([^)]*\))?\s*[:\-]\s*(.+?)(?=\n[^\n]*?(?:TWEET|POST)\s+\d+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = inline_re.findall(normalized)
    if matches:
        for i, (num, raw_content) in enumerate(matches[:7]):
            content, hint = _extract_image_hint(raw_content)
            content = _clean_post_content(content)
            if content and len(content) > 10:
                post_type = post_types[i] if i < len(post_types) else "other"
                posts.append({"content": content, "type": post_type, "image_hint": hint})
        if posts:
            return posts

    # Fallback: numbered list (1. ... 2. ...)
    pattern3 = r"(\d+)[.\)]\s+(.+?)(?=\n\d+[.\)]|\Z)"
    matches = re.findall(pattern3, raw_text, re.DOTALL)

    for i, (num, raw_content) in enumerate(matches[:7]):
        content, hint = _extract_image_hint(raw_content)
        content = _clean_post_content(content)
        if content and len(content) > 10:
            post_type = post_types[i] if i < len(post_types) else "other"
            posts.append({"content": content, "type": post_type, "image_hint": hint})

    if posts:
        return posts

    # Last resort: split by leading emoji on a new line
    # Each tweet typically starts with an emoji — use that as delimiter
    emoji_split = re.split(
        r"\n(?="
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        r"\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF\u2600-\u27BF\u2300-\u23FF]"
        r")",
        raw_text.strip(),
    )
    for i, chunk in enumerate(emoji_split):
        content, hint = _extract_image_hint(chunk)
        content = _clean_post_content(content)
        if content and len(content) > 20:
            post_type = post_types[i] if i < len(post_types) else "other"
            posts.append({"content": content, "type": post_type, "image_hint": hint})

    # If still one giant blob, force-split any post over 300 chars
    if len(posts) == 1 and len(posts[0]["content"]) > 300:
        blob = posts[0]["content"]
        # Try splitting on double newlines
        parts = [p.strip() for p in re.split(r"\n\s*\n", blob) if p.strip()]
        if len(parts) >= 2:
            posts = []
            for i, part in enumerate(parts):
                part, hint = _extract_image_hint(part)
                part = _clean_post_content(part)
                if part and len(part) > 20:
                    post_type = post_types[i] if i < len(post_types) else "other"
                    posts.append({"content": part, "type": post_type, "image_hint": hint})

    return posts


def get_batch_id():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
