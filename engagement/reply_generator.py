import re
import json
import random

from mistralai import Mistral

import config
from storage.database import log_api_usage, get_recent_reply_contents
from limiter.usage_limiter import usage_limiter
from scoring.quality_scorer import (
    score_ai_detection,
    score_readability,
    score_emoji_compliance,
    _extract_significant_words,
    _load_config,
)

MODEL = "mistral-small-latest"

REPLY_STYLES = ["complementary", "witty", "question", "hot_take", "agreement", "emoji_reaction"]

# --- Safety: toxic content detection ---

# Slurs, hate speech terms, and discriminatory language patterns.
# This catches obvious cases instantly without an API call.
_TOXIC_KEYWORDS = [
    # Racial slurs
    "nigger", "nigga", "negro", "chink", "gook", "spic", "wetback", "kike",
    "raghead", "towelhead", "beaner", "coon", "darkie", "redskin", "paki",
    "cracker", "honky", "gringo",
    # Misogynistic / sexist
    "bitch", "whore", "slut", "cunt", "hoe", "thot",
    # Homophobic / transphobic
    "faggot", "fag", "dyke", "tranny", "shemale", "ladyboy",
    # Ableist
    "retard", "retarded",
    # General hate
    "subhuman", "untermensch", "white power", "white supremacy",
    "heil hitler", "gas the", "kill all",
]

# Patterns that signal discriminatory context (regex)
_TOXIC_PATTERNS = [
    r"\b(?:all|those|these|the)\s+(?:women|girls|females)\s+(?:are|should|need to|belong)",
    r"\b(?:all|those|these|the)\s+(?:men|boys|males)\s+(?:are|should)",
    r"\b(?:go\s+back\s+to|deport\s+(?:all|them|every))",
    r"\b(?:women|girls)\s+(?:can'?t|shouldn'?t|don'?t)\s+(?:lead|drive|work|think|code)",
    r"\b(?:illegals?|aliens?)\s+(?:are|should|invad)",
    r"\billegal\s+(?:immigrant|alien|people)",
    r"\b(?:gender|sex)\s+(?:is|are)\s+(?:only|just)\s+(?:two|2)\b",
    r"\b(?:trans\s+(?:people|women|men)\s+(?:aren'?t|are\s+not|are\s+(?:mentally|just)))",
    r"\b(?:gay|lesbian|homosexual)\s+(?:agenda|disease|disorder|sin|abomination)",
]

_TOXIC_KEYWORDS_SET = set(_TOXIC_KEYWORDS)
_TOXIC_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in _TOXIC_PATTERNS]


def check_toxicity(text, skip_llm=False):
    """Check if text contains toxic/discriminatory content.

    Returns dict with:
      - is_toxic: bool
      - reason: str (explanation if toxic)
      - method: 'keyword' | 'pattern' | 'llm' | None

    Uses a multi-layer approach:
      1. Fast keyword/pattern matching (instant, no API cost)
      2. LLM moderation check (catches subtle cases) - skipped if skip_llm=True
    """
    text_lower = text.lower()

    # Layer 1: Keyword matching
    words = set(re.findall(r"[a-z']+", text_lower))
    # Check single-word slurs
    found_slurs = words & _TOXIC_KEYWORDS_SET
    if found_slurs:
        return {
            "is_toxic": True,
            "reason": f"Contains slur: {', '.join(found_slurs)}",
            "method": "keyword",
        }
    # Check multi-word phrases
    for phrase in _TOXIC_KEYWORDS:
        if " " in phrase and phrase in text_lower:
            return {
                "is_toxic": True,
                "reason": f"Contains toxic phrase: '{phrase}'",
                "method": "keyword",
            }

    # Layer 2: Pattern matching
    for pattern in _TOXIC_PATTERNS_COMPILED:
        match = pattern.search(text)
        if match:
            return {
                "is_toxic": True,
                "reason": f"Matches discriminatory pattern: '{match.group()}'",
                "method": "pattern",
            }

    # Layer 3: LLM moderation (catches nuanced / context-dependent toxicity)
    if not skip_llm:
        try:
            result = _llm_moderation_check(text)
            if result["is_toxic"]:
                return result
        except Exception:
            pass  # If LLM check fails, let it through (keyword/pattern already passed)

    return {"is_toxic": False, "reason": None, "method": None}


def _llm_moderation_check(text):
    """Use LLM to detect subtle toxicity that keywords miss.

    Routes to Groq (free) when available, falls back to Mistral.
    """
    # Try the provider router first (prefers Groq for moderation)
    try:
        from generator.provider_router import moderation_check
        return moderation_check(text)
    except (ImportError, RuntimeError):
        pass

    # Direct Mistral fallback
    allowed, _ = usage_limiter.check_mistral()
    if not allowed:
        return {"is_toxic": False, "reason": None, "method": None}

    client = _get_client()
    prompt = f"""Is this text hate speech, discriminatory, or toxic? Be strict.

Text: "{text}"

Reply EXACTLY: SAFE or TOXIC: [reason]"""

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    usage = response.usage
    if usage:
        cost = (usage.prompt_tokens * 0.000001) + (usage.completion_tokens * 0.000003)
        log_api_usage("mistral", "moderation_check", usage.prompt_tokens, usage.completion_tokens, cost)

    answer = response.choices[0].message.content.strip()

    if answer.upper().startswith("TOXIC"):
        reason = answer.split(":", 1)[1].strip() if ":" in answer else "Flagged by LLM moderation"
        return {"is_toxic": True, "reason": reason, "method": "llm"}

    return {"is_toxic": False, "reason": None, "method": None}


def _get_client():
    return Mistral(api_key=config.MISTRAL_API_KEY)


def generate_reply(original_tweet_text, target_username, reply_style="mixed", max_length=280):
    """Generate 3 reply candidates via Mistral. Returns list of dicts with content and style."""
    allowed, reason = usage_limiter.check_mistral()
    if not allowed:
        print(f"[Limiter] Mistral blocked: {reason}")
        return []

    if reply_style == "mixed":
        reply_style = random.choice(REPLY_STYLES)

    client = _get_client()
    prompt = config.REPLY_GENERATION_PROMPT.format(
        target_username=target_username,
        original_tweet=original_tweet_text,
        reply_style=reply_style,
        max_length=max_length,
    )

    response = client.chat.complete(
        model=MODEL,
        messages=[
            {"role": "system", "content": config.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.85,
    )

    raw_text = response.choices[0].message.content

    # Log usage
    usage = response.usage
    if usage:
        cost = (usage.prompt_tokens * 0.000001) + (usage.completion_tokens * 0.000003)
        log_api_usage("mistral", "generate_reply", usage.prompt_tokens, usage.completion_tokens, cost)

    candidates = _parse_replies(raw_text, reply_style)
    return candidates


def _clean_reply(text):
    """Strip markdown/formatting artifacts from LLM output."""
    # *italic* and **bold** -> plain text
    text = re.sub(r"\*{1,2}(\w[\w\s]*?\w?)\*{1,2}", r"\1", text)
    # _italic_ and __underline__
    text = re.sub(r"_{1,2}(\w[\w\s]*?\w?)_{1,2}", r"\1", text)
    # Remove stray asterisks/underscores
    text = text.replace("**", "").replace("__", "")
    # Em dash -> regular dash
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    return text.strip()


def _parse_replies(raw_text, style):
    """Parse LLM output into structured reply candidates."""
    candidates = []

    # Try REPLY N: format
    pattern = re.compile(
        r"REPLY\s+(\d+)\s*:\s*(.+?)(?=REPLY\s+\d+\s*:|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(raw_text)

    if matches:
        for num, content in matches[:3]:
            cleaned = _clean_reply(content.strip().strip('"'))
            if cleaned and len(cleaned) > 5:
                candidates.append({"content": cleaned, "style": style})
        if candidates:
            return candidates

    # Fallback: numbered list (1. ... 2. ...)
    pattern2 = r"(\d+)[.\)]\s+(.+?)(?=\n\d+[.\)]|\Z)"
    matches = re.findall(pattern2, raw_text, re.DOTALL)
    for num, content in matches[:3]:
        cleaned = _clean_reply(content.strip().strip('"'))
        if cleaned and len(cleaned) > 5:
            candidates.append({"content": cleaned, "style": style})

    # Last fallback: split by newlines and take non-empty lines
    if not candidates:
        lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
        for line in lines[:3]:
            cleaned = _clean_reply(re.sub(r"^[\d.\-\)]+\s*", "", line).strip().strip('"'))
            if cleaned and len(cleaned) > 5:
                candidates.append({"content": cleaned, "style": style})

    return candidates


def score_reply(reply_text, original_tweet_text, quality_config=None, existing_replies=None, skip_llm_moderation=False):
    """Score a reply with reply-specific weights.

    Reuses AI detection and readability from scoring/quality_scorer.py.
    Adds relevance scoring (word overlap with original tweet).
    Includes toxicity safeguard: toxic reply = automatic 0.

    When skip_llm_moderation=True, only keyword/pattern toxicity checks run
    (saves ~160 tokens per call). Use this during candidate ranking, then
    run full moderation on the winner only.
    """
    cfg = _load_config(quality_config)

    # SAFEGUARD: Toxicity check on our reply — instant kill if toxic
    toxicity = check_toxicity(reply_text, skip_llm=skip_llm_moderation)
    if toxicity["is_toxic"]:
        return {
            "overall": 0,
            "ai": {"score": 0, "penalties": [], "details": "Blocked by toxicity filter"},
            "readability": {"score": 0, "penalties": [], "details": "Blocked"},
            "emoji": {"score": 0, "has_leading_emoji": False, "emoji_found": [], "penalties": [], "details": "Blocked"},
            "relevance": {"score": 0, "details": "Blocked"},
            "duplicate": {"score": 0, "details": "Blocked"},
            "toxicity": toxicity,
            "blocked": True,
            "blocked_reason": f"TOXIC REPLY: {toxicity['reason']} (method: {toxicity['method']})",
        }

    ai = score_ai_detection(reply_text, cfg)
    readability = score_readability(reply_text, cfg)
    emoji = score_emoji_compliance(reply_text, cfg)
    relevance = _score_relevance(reply_text, original_tweet_text)
    duplicate = _score_reply_duplicate(reply_text, existing_replies or [])

    # Reply-specific weights
    overall = (
        ai["score"] * 0.40
        + readability["score"] * 0.30
        + relevance["score"] * 0.20
        + emoji["score"] * 0.10
    )

    # Length bonus: shorter replies are better
    length = len(reply_text)
    if length <= 100:
        overall += 5
    elif length <= 140:
        overall += 3

    # Duplicate penalty as multiplier
    if duplicate["score"] < 100:
        overall = overall * (duplicate["score"] / 100.0)

    overall = round(min(max(overall, 0), 100), 1)

    return {
        "overall": overall,
        "ai": ai,
        "readability": readability,
        "emoji": emoji,
        "relevance": relevance,
        "duplicate": duplicate,
        "toxicity": {"is_toxic": False, "reason": None, "method": None},
        "blocked": False,
    }


def _score_relevance(reply_text, original_tweet_text):
    """Score how relevant the reply is to the original tweet.
    Based on word overlap between reply and tweet.
    """
    reply_words = _extract_significant_words(reply_text)
    tweet_words = _extract_significant_words(original_tweet_text)

    if not tweet_words or not reply_words:
        return {"score": 50, "details": "Too short to evaluate relevance"}

    overlap = reply_words & tweet_words
    # Relevance = what fraction of tweet's key words we reference
    relevance_ratio = len(overlap) / len(tweet_words) if tweet_words else 0

    if relevance_ratio >= 0.2:
        score = 100
    elif relevance_ratio >= 0.1:
        score = 75
    elif relevance_ratio > 0:
        score = 50
    else:
        score = 20  # No word overlap at all

    return {
        "score": score,
        "overlap": list(overlap),
        "details": f"{len(overlap)} shared words ({relevance_ratio:.0%})",
    }


def _score_reply_duplicate(reply_text, existing_replies):
    """Check reply against recent replies for duplicates."""
    if not existing_replies:
        return {"score": 100, "details": "No history"}

    new_words = _extract_significant_words(reply_text)
    if not new_words:
        return {"score": 100, "details": "Too short"}

    worst = 0.0
    for existing in existing_replies:
        content = existing if isinstance(existing, str) else existing.get("reply_content", "")
        old_words = _extract_significant_words(content)
        if not old_words:
            continue
        intersection = new_words & old_words
        union = new_words | old_words
        similarity = len(intersection) / len(union) if union else 0
        worst = max(worst, similarity)

    score = 100
    if worst >= 0.7:
        score = 0
    elif worst >= 0.5:
        score = max(0, 100 - int(worst * 100))
    elif worst >= 0.35:
        score = max(0, 100 - int(worst * 60))

    return {"score": score, "details": f"Max similarity: {worst:.0%}"}


def pick_best_reply(original_tweet_text, candidates, quality_config=None):
    """Score all candidates and return the best one with its score.

    Token optimization: candidates are scored with keyword/pattern-only
    toxicity checks. LLM moderation runs only on the winning candidate,
    saving ~160 tokens per non-winning candidate (~66% reduction).
    """
    existing = get_recent_reply_contents(limit=50)

    best = None
    best_score = -1

    # Phase 1: Score all candidates WITHOUT LLM moderation (fast + free)
    for candidate in candidates:
        result = score_reply(
            candidate["content"], original_tweet_text,
            quality_config=quality_config, existing_replies=existing,
            skip_llm_moderation=True,
        )
        candidate["quality_score"] = result["overall"]
        candidate["score_details"] = result

        if result["overall"] > best_score:
            best_score = result["overall"]
            best = candidate

    if not best:
        return None

    # Phase 2: Run full toxicity check (including LLM) on the winner only
    if not best["score_details"].get("blocked"):
        toxicity = check_toxicity(best["content"], skip_llm=False)
        if toxicity["is_toxic"]:
            best["quality_score"] = 0
            best["score_details"]["overall"] = 0
            best["score_details"]["toxicity"] = toxicity
            best["score_details"]["blocked"] = True
            best["score_details"]["blocked_reason"] = f"TOXIC REPLY: {toxicity['reason']} (method: {toxicity['method']})"

    return best
