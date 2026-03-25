import re
import google.generativeai as genai
from datetime import datetime

import config


def generate_posts(articles_text):
    """Generate 7 X posts from article summaries using Gemini."""
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = config.GEMINI_PROMPT.format(articles=articles_text)

    response = model.generate_content(prompt)
    raw_text = response.text

    return parse_posts(raw_text)


def parse_posts(raw_text):
    """Parse Gemini output into structured posts."""
    posts = []
    post_types = [
        "news",
        "news",
        "educational",
        "educational",
        "opinion",
        "data",
        "question",
    ]

    # Split by POST N pattern
    pattern = r"POST\s+(\d+)[^:]*:\s*(.*?)(?=POST\s+\d+|$)"
    matches = re.findall(pattern, raw_text, re.DOTALL | re.IGNORECASE)

    for i, (num, content) in enumerate(matches):
        cleaned = content.strip().strip('"').strip()
        if cleaned:
            post_type = post_types[i] if i < len(post_types) else "other"
            posts.append({
                "content": cleaned,
                "type": post_type,
            })

    # Fallback: if regex didn't work, split by lines
    if not posts:
        lines = [l.strip() for l in raw_text.split("\n") if l.strip() and len(l.strip()) > 20]
        for i, line in enumerate(lines[:7]):
            # Remove leading "1." or "POST 1:" patterns
            cleaned = re.sub(r"^(POST\s*\d+[:\-\.]?\s*|[\d]+[:\-\.\)]\s*)", "", line).strip()
            if cleaned:
                post_type = post_types[i] if i < len(post_types) else "other"
                posts.append({
                    "content": cleaned,
                    "type": post_type,
                })

    return posts


def get_batch_id():
    """Generate a unique batch ID for this generation run."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
