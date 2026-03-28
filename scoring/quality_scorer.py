import re
import json


# --- Default config (overridden by DB quality_config) ---

DEFAULT_CONFIG = {
    "ai_detection_enabled": True,
    "ai_penalty_phrases": [
        "delve", "landscape", "it's worth noting", "revolutionize",
        "game-changer", "paradigm shift", "at the forefront", "in the realm of",
        "harness", "leverage", "navigate", "unprecedented", "groundbreaking",
        "synergy", "deep dive", "robust", "seamlessly", "tapestry", "embark",
        "pivotal", "multifaceted", "notably", "essentially", "furthermore",
        "transformative", "disruptive",
        # Financial AI buzzwords
        "to the moon", "diamond hands", "paper hands", "WAGMI", "NGMI",
        "disruptive fintech", "paradigm shift in defi",
    ],
    "ai_emdash_penalty": 15,
    "ai_phrase_penalty": 10,
    "readability_enabled": True,
    "readability_jargon_list": [
        # Financial jargon that's too obscure for general audience
        "contango", "backwardation", "delta hedging", "gamma squeeze",
        "implied volatility skew", "convexity", "duration risk",
        "monte carlo", "sharpe ratio", "sortino ratio",
    ],
    "readability_jargon_penalty": 8,
    "readability_max_grade_level": 10,
    "emoji_enabled": False,  # Disabled: professional tone, no emojis
    "emoji_preferred": [],
    "emoji_leading_bonus": 0,
    "weight_substance": 0.30,
    "weight_variety": 0.15,
    "weight_ai": 0.15,
    "weight_readability": 0.15,
    "weight_emoji": 0.00,     # Disabled: no emojis in professional bot
    "weight_tone": 0.25,      # Replaces weight_vibes (increased from 0.20)
    "weight_vibes": 0.00,     # Deprecated, kept for DB compat
    "weight_data_accuracy": 0.20,  # New: disclaimer, numbers, no predictions
    "min_quality_score": 45.0,
    "auto_reject_below": 25.0,
}

# Passive voice markers
PASSIVE_PATTERNS = [
    r"\bit has been\b", r"\bit is observed\b", r"\bit was found\b",
    r"\bit is noted\b", r"\bit should be noted\b", r"\bhas been shown\b",
    r"\bcan be seen\b", r"\bis considered\b",
]

# Emoji regex: covers most common emoji ranges
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended
    "\u2600-\u27BF"          # misc symbols
    "\u2300-\u23FF"          # misc technical
    "\u2B50-\u2B55"          # stars
    "\u200D"                 # zero width joiner
    "\uFE0F"                 # variation selector
    "]"
)


def _count_syllables(word):
    """Simple English syllable counter."""
    word = word.lower().strip(".,!?;:'\"")
    if len(word) <= 2:
        return 1
    # Remove trailing silent e
    if word.endswith("e") and not word.endswith("le"):
        word = word[:-1]
    # Count vowel groups
    count = len(re.findall(r"[aeiouy]+", word))
    return max(count, 1)


def _load_config(config=None):
    """Merge provided config with defaults."""
    if config is None:
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    for key, val in config.items():
        if val is not None:
            # Handle JSON strings from DB
            if key in ("ai_penalty_phrases", "readability_jargon_list", "emoji_preferred"):
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        continue
            # Handle int booleans from DB
            if key in ("ai_detection_enabled", "readability_enabled", "emoji_enabled"):
                val = bool(val)
            merged[key] = val
    return merged


def _score_gibberish(text):
    """Detect gibberish / broken formatting that makes text look bot-generated.

    Returns (penalty, list_of_reasons).  A penalty of 100 means instant score = 0.
    """
    penalty = 0
    reasons = []

    # Strip emoji for analysis
    clean = EMOJI_RE.sub("", text).strip()
    if not clean:
        return 100, ["Empty text after removing emoji"]

    # 1. Repeated special chars in a row: %$*, !!!, ???, etc.
    if re.search(r"[!?]{4,}", clean):
        penalty += 40
        reasons.append("Excessive punctuation repetition")
    if re.search(r"[^a-zA-Z0-9\s.,!?:;'\"@#\-/()\u2019\u2018]{2,}", clean):
        penalty += 50
        reasons.append("Suspicious symbol sequence")

    # 2. High ratio of special chars vs letters (normal text is mostly letters)
    letters = len(re.findall(r"[a-zA-Z]", clean))
    specials = len(re.findall(r"[^a-zA-Z0-9\s]", clean))
    if letters > 0 and specials / letters > 0.4:
        penalty += 60
        reasons.append(f"Too many special chars ({specials}/{letters} ratio)")
    elif letters == 0 and len(clean) > 3:
        penalty += 100
        reasons.append("No actual words")

    # 3. Random capitalization (lIkE tHiS) — more than 3 mid-word caps
    mid_caps = len(re.findall(r"(?<=[a-z])[A-Z](?=[a-z])", clean))
    if mid_caps >= 3:
        penalty += 30
        reasons.append(f"Random capitalization ({mid_caps} mid-word caps)")

    # 4. Repeated characters (aaaaaaa, lolololol)
    if re.search(r"(.)\1{4,}", clean.lower()):
        penalty += 40
        reasons.append("Repeated characters")

    # 5. Repeated words/fragments (buy buy buy, ha ha ha ha)
    if re.search(r"\b(\w+)\s+(\1\s+){2,}", clean.lower()):
        penalty += 40
        reasons.append("Repeated words")

    # 6. Markdown/formatting artifacts that shouldn't appear in a tweet
    #    Catches **bold**, __underline__, ###heading, ```code```,
    #    and single *italic* / _italic_ wrapping (e.g. *us*, *then*)
    if re.search(r"\*{2,}|_{2,}|#{2,}|```", clean):
        penalty += 30
        reasons.append("Formatting artifacts (markdown)")
    elif re.search(r"\*\w+\*|_\w+_", clean):
        penalty += 25
        reasons.append("Italic markdown (*word*)")

    return min(penalty, 100), reasons


def score_ai_detection(text, config=None):
    """Score text for AI-telltale patterns. Returns dict with score, penalties, details."""
    cfg = _load_config(config)
    if not cfg["ai_detection_enabled"]:
        return {"score": 100, "penalties": [], "details": "AI detection disabled"}

    score = 100
    penalties = []
    text_lower = text.lower()

    # Gibberish detection — instant kill if severe
    gibberish_penalty, gibberish_reasons = _score_gibberish(text)
    if gibberish_penalty > 0:
        score -= gibberish_penalty
        for reason in gibberish_reasons:
            penalties.append(f"Gibberish: {reason} (-{gibberish_penalty})")

    # Em dash penalty
    emdash_count = text.count("\u2014") + text.count("--")
    if emdash_count > 0:
        penalty = emdash_count * cfg["ai_emdash_penalty"]
        score -= penalty
        penalties.append(f"Em dash x{emdash_count} (-{penalty})")

    # AI phrases penalty
    phrase_penalty = cfg["ai_phrase_penalty"]
    for phrase in cfg["ai_penalty_phrases"]:
        if phrase.lower() in text_lower:
            score -= phrase_penalty
            penalties.append(f'AI phrase: "{phrase}" (-{phrase_penalty})')

    # Passive voice penalty
    for pattern in PASSIVE_PATTERNS:
        if re.search(pattern, text_lower):
            score -= 5
            penalties.append(f"Passive voice (-5)")

    # Multiple colons penalty
    colon_count = text.count(":")
    if colon_count > 1:
        extra = colon_count - 1
        penalty = extra * 5
        score -= penalty
        penalties.append(f"Extra colons x{extra} (-{penalty})")

    score = max(score, 0)
    return {
        "score": score,
        "penalties": penalties,
        "details": f"{len(penalties)} issues found" if penalties else "Clean",
    }


def score_readability(text, config=None):
    """Score text for readability. Returns dict with score, penalties, details."""
    cfg = _load_config(config)
    if not cfg["readability_enabled"]:
        return {"score": 100, "penalties": [], "details": "Readability scoring disabled"}

    score = 100
    penalties = []
    text_lower = text.lower()

    # Strip emoji for word analysis
    clean_text = EMOJI_RE.sub("", text).strip()
    words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", clean_text)

    # Long words penalty (> 4 syllables)
    for word in words:
        syllables = _count_syllables(word)
        if syllables > 4:
            score -= 5
            penalties.append(f'Complex word: "{word}" ({syllables} syl, -5)')

    # Jargon penalty
    jargon_penalty = cfg["readability_jargon_penalty"]
    for term in cfg["readability_jargon_list"]:
        if term.lower() in text_lower:
            score -= jargon_penalty
            penalties.append(f'Jargon: "{term}" (-{jargon_penalty})')

    # Bonus for short sentences
    sentences = re.split(r"[.!?]+", clean_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    for sentence in sentences:
        word_count = len(sentence.split())
        if 0 < word_count < 15:
            score += 5

    # Bonus for numbers/stats
    if re.search(r"\d", text):
        score += 5

    score = max(min(score, 100), 0)
    return {
        "score": score,
        "penalties": penalties,
        "details": f"{len(penalties)} issues" if penalties else "Good readability",
    }


def score_emoji_compliance(text, config=None):
    """Score emoji usage. Returns dict with score, has_leading_emoji, emoji_found."""
    cfg = _load_config(config)
    if not cfg["emoji_enabled"]:
        return {"score": 100, "has_leading_emoji": True, "emoji_found": [], "penalties": [], "details": "Emoji scoring disabled"}

    score = 0
    penalties = []
    preferred = cfg["emoji_preferred"]

    # Find all emoji in text
    found_emoji = EMOJI_RE.findall(text)
    # Filter out zero-width joiners and variation selectors
    found_emoji = [e for e in found_emoji if e not in ("\u200D", "\uFE0F")]

    # Check leading emoji
    stripped = text.lstrip()
    has_leading = bool(stripped) and bool(EMOJI_RE.match(stripped[0]))

    if has_leading:
        score += cfg["emoji_leading_bonus"]
    else:
        penalties.append(f"No leading emoji (-{cfg['emoji_leading_bonus']})")

    # High-engagement emoji bonus
    if any(e in preferred for e in found_emoji):
        score += 25
    elif found_emoji:
        penalties.append("No high-engagement emoji (-25)")

    # At least one emoji
    if found_emoji:
        score += 25
    else:
        penalties.append("No emoji at all")
        score = 0

    score = max(min(score, 100), 0)
    return {
        "score": score,
        "has_leading_emoji": has_leading,
        "emoji_found": found_emoji,
        "penalties": penalties,
        "details": f"{len(found_emoji)} emoji, leading={'yes' if has_leading else 'no'}",
    }


def score_vibes(text, config=None):
    """Legacy wrapper: redirects to score_tone() for financial bot."""
    return score_tone(text, config)


def score_tone(text, config=None):
    """Score tweet for professional, factual tone. Rewards data-driven, neutral writing."""
    score = 50  # Start neutral
    bonuses = []
    penalties = []

    clean = EMOJI_RE.sub("", text).strip()
    text_lower = text.lower()
    char_count = len(clean)

    # Length sweet spot (includes auto-appended link ~23 chars + disclaimer ~25 chars)
    if 120 <= char_count <= 220:
        score += 15
        bonuses.append(f"Good length {char_count} chars (+15)")
    elif 80 <= char_count <= 280:
        score += 8
        bonuses.append(f"Acceptable length {char_count} chars (+8)")
    elif char_count > 280:
        score -= 20
        penalties.append(f"Too long: {char_count} chars (-20)")
    elif char_count < 60:
        score -= 10
        penalties.append(f"Too short: {char_count} chars (-10)")

    # Text tag bonus (BREAKING:, JUST IN:, etc.)
    text_tags = ["breaking:", "just in:", "market update:", "alert:", "data:"]
    if any(text_lower.lstrip().startswith(tag) for tag in text_tags):
        score += 15
        bonuses.append("Text tag opener (+15)")

    # Emoji penalty (professional bot = no emojis)
    if EMOJI_RE.search(text):
        score -= 10
        penalties.append("Contains emoji (-10)")

    # Source attribution bonus
    attributions = ["via polymarket", "coingecko", "yahoo finance", "polygon"]
    if any(a in text_lower for a in attributions):
        score += 15
        bonuses.append("Source attribution (+15)")

    # Cashtag / ticker bonus ($BTC, $ETH, $SPX, ^GSPC)
    if re.search(r"\$[A-Z]{2,5}\b", text) or re.search(r"\^[A-Z]{2,}", text):
        score += 10
        bonuses.append("Ticker/cashtag used (+10)")

    # Comparison/context bonus (adds value beyond raw number)
    context_phrases = [
        "highest since", "lowest since", "first time", "consecutive",
        "compared to", "up from", "down from", "vs", "versus",
        "week ago", "month ago", "year ago", "daily average",
        "in 24h", "in the last", "since january", "since february",
        "since march",
    ]
    if any(p in text_lower for p in context_phrases):
        score += 10
        bonuses.append("Historical context (+10)")

    # Neutral tone check: penalize opinion/prediction language
    opinion_words = [
        "to the moon", "crash incoming", "gonna pump", "gonna dump",
        "buy now", "sell now", "you should", "i think will",
        "bullish", "bearish", "diamond hands", "paper hands",
        "trust me", "mark my words", "guaranteed",
    ]
    for phrase in opinion_words:
        if phrase in text_lower:
            score -= 15
            penalties.append(f'Opinion/prediction: "{phrase}" (-15)')

    # Penalty for casual slang (wrong tone for financial bot)
    casual_slang = [
        "damn", "lowkey", "fr ", "lol", "are we cooked",
        "ngl", "bruh", "lfg", "wagmi", "ngmi",
    ]
    for slang in casual_slang:
        if slang in text_lower:
            score -= 10
            penalties.append(f'Casual slang: "{slang.strip()}" (-10)')

    score = max(min(score, 100), 0)
    return {
        "score": score,
        "bonuses": bonuses,
        "penalties": penalties,
        "details": f"{len(bonuses)} tone signals, {len(penalties)} issues",
    }


def score_data_accuracy(text, config=None):
    """Score tweet for data accuracy markers. Checks disclaimer, numbers, no predictions."""
    score = 50  # Start neutral
    bonuses = []
    penalties = []
    text_lower = text.lower()

    # Disclaimer check (critical)
    if "not financial advice" in text_lower:
        score += 20
        bonuses.append("Disclaimer present (+20)")
    else:
        score -= 30
        penalties.append("Missing disclaimer (-30)")

    # At least one number required
    has_number = bool(re.search(r"\d", text))
    if has_number:
        score += 15
        bonuses.append("Contains number (+15)")
    else:
        score -= 20
        penalties.append("No numbers in financial tweet (-20)")

    # Percentage or dollar amount (strong data signal)
    if re.search(r"\d+\.?\d*%", text) or re.search(r"\$[\d,.]+", text):
        score += 10
        bonuses.append("Specific financial data (+10)")

    # Character count under 280 (Twitter limit)
    if len(text) <= 280:
        score += 5
        bonuses.append("Within character limit (+5)")
    else:
        score -= 20
        penalties.append(f"Over 280 chars: {len(text)} (-20)")

    # No prediction language
    predictions = [
        "will reach", "will hit", "going to ", "expect to see",
        "price target", "my prediction", "calling it now",
    ]
    for pred in predictions:
        if pred in text_lower:
            score -= 15
            penalties.append(f'Prediction language: "{pred}" (-15)')

    score = max(min(score, 100), 0)
    return {
        "score": score,
        "bonuses": bonuses,
        "penalties": penalties,
        "details": f"{len(bonuses)} accuracy signals, {len(penalties)} issues",
    }


# --- Generic closer patterns (AI-sounding kickers) ---
GENERIC_CLOSERS = [
    r"the .+ race is on",
    r"will your .+ adapt",
    r"the future (is|of) .+",
    r"this changes everything",
    r"let that sink in",
    r"and it'?s only the beginning",
    r"buckle up",
    r"the world (will never|is about to)",
    r"game over",
    r"welcome to the future",
    r"(you'?re|we'?re) not ready",
    r"mark my words",
]

# Cause-effect signal words
CAUSE_EFFECT_WORDS = {
    "because", "therefore", "means", "result", "consequence", "caused",
    "leads to", "so that", "which means", "impact", "effect",
}

# Comparison signal words
COMPARISON_WORDS = {
    "more than", "less than", "compared to", "versus", "vs", "outpaces",
    "doubles", "triples", "surpasses", "overtakes", "beats", "faster than",
    "bigger than", "smaller than", "unlike",
    "highest since", "lowest since", "up from", "down from", "above average",
    "below average", "for comparison", "near", "flat at",
}


def _extract_entities(text):
    """Extract named entities and key identifiers for semantic dedup."""
    entities = set()
    clean = EMOJI_RE.sub("", text).strip()

    # All-caps words (acronyms): IQM, TSMC, NASA, AI
    for match in re.finditer(r"\b[A-Z]{2,}\b", clean):
        entities.add(match.group().lower())

    # Capitalized multi-word names: "Series B", "Quantum Brief"
    for match in re.finditer(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", clean):
        entities.add(match.group().lower())

    # Single capitalized words not at sentence start (proper nouns)
    for match in re.finditer(r"(?<=[.!?\n] |:\s)([A-Z][a-z]{2,})", clean):
        entities.add(match.group().lower())
    # Also words after line breaks
    for line in clean.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Words that are capitalized mid-sentence
        words = line.split()
        for w in words[1:]:
            if w and w[0].isupper() and w.isalpha() and len(w) >= 3:
                entities.add(w.lower())

    # Dollar amounts: $300M, $2.1B, $90M
    for match in re.finditer(r"\$[\d,.]+[BMKbmk]?\b", text):
        entities.add(match.group().lower())

    # Percentages
    for match in re.finditer(r"\d+%", text):
        entities.add(match.group())

    # Large numbers: 1,000, 42000, etc.
    for match in re.finditer(r"\b\d{1,3}(?:,\d{3})+\b", text):
        entities.add(match.group())

    return entities


def _classify_template(text):
    """Classify tweet structure into a template type for variety scoring."""
    text_lower = text.lower().strip()
    clean = EMOJI_RE.sub("", text_lower).strip()

    if "breaking" in clean[:30]:
        return "breaking"
    if re.search(r"^(most people|here'?s (why|the thing)|turns out|fun fact)", clean):
        return "explainer"
    if clean.rstrip().endswith("?"):
        return "question"
    if re.search(r"^\$?[\d,.]+[BMK%]?\b", clean):
        return "data"
    if re.search(r"(hot take|unpopular opinion|controversial|actually)", clean[:50]):
        return "opinion"
    # Default: standard news format (fact + consequence + kicker)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) >= 3:
        return "3block"
    return "short"


def score_substance(text, config=None):
    """Score tweet for substantive content quality. Returns dict with score, penalties, details.

    Checks: specificity (proper nouns, numbers, entities), information density,
    and penalizes generic AI-sounding closers.
    """
    score = 0
    penalties = []
    bonuses = []
    text_lower = text.lower()
    clean = EMOJI_RE.sub("", text).strip()

    # --- Specificity (0-60 points) ---

    # Proper nouns / named entities
    entities = _extract_entities(text)
    proper_nouns = [e for e in entities if e.isalpha() and len(e) >= 3]
    if proper_nouns:
        score += 10
        bonuses.append(f"Named entity: {proper_nouns[0]} (+10)")

    # Dollar amounts (cumulative - each one adds value)
    dollar_matches = re.findall(r"\$[\d,.]+[BMKTbmkt]?", text)
    if dollar_matches:
        pts = min(len(dollar_matches) * 8, 20)
        score += pts
        bonuses.append(f"Dollar amounts x{len(dollar_matches)} (+{pts})")

    # Percentages (cumulative)
    pct_matches = re.findall(r"[\d.]+%", text)
    if pct_matches:
        pts = min(len(pct_matches) * 6, 15)
        score += pts
        bonuses.append(f"Percentages x{len(pct_matches)} (+{pts})")

    # Cashtags ($BTC, $ETH) - strong financial signal
    cashtags = re.findall(r"\$[A-Z]{2,5}\b", text)
    if cashtags:
        pts = min(len(cashtags) * 5, 10)
        score += pts
        bonuses.append(f"Cashtags x{len(cashtags)} (+{pts})")

    # Time reference (recency signal)
    time_words = ["in 24h", "in 1h", "today", "this week", "7-day", "7d", "30-day",
                  "since march", "since april", "since january", "highest since",
                  "lowest since", "consecutive", "week-over-week"]
    if any(w in text_lower for w in time_words):
        score += 5
        bonuses.append("Time reference (+5)")

    # --- Information density (0-30 points) ---

    # Cause-effect relationship
    if any(w in text_lower for w in CAUSE_EFFECT_WORDS):
        score += 10
        bonuses.append("Cause-effect (+10)")

    # Comparison
    if any(w in text_lower for w in COMPARISON_WORDS):
        score += 5
        bonuses.append("Comparison (+5)")

    # Content word ratio (nouns/verbs vs filler)
    words = re.findall(r"[a-zA-Z]+", clean)
    filler = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
              "have", "has", "had", "do", "does", "did", "will", "would", "could",
              "should", "may", "might", "shall", "can", "to", "of", "in", "for",
              "on", "with", "at", "by", "from", "as", "into", "about", "it", "its"}
    if words:
        content_ratio = len([w for w in words if w.lower() not in filler]) / len(words)
        if content_ratio >= 0.55:
            score += 15
            bonuses.append(f"High content density ({content_ratio:.0%}, +15)")

    # --- Generic closer penalty (-15 each) ---
    # Look at last 3 non-empty lines (closers are often before a hashtag or trailing blank)
    non_empty_lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
    last_lines = " ".join(non_empty_lines[-3:]).lower() if non_empty_lines else text_lower
    for pattern in GENERIC_CLOSERS:
        if re.search(pattern, last_lines):
            score -= 15
            penalties.append(f'Generic closer: "{pattern}" (-15)')

    score = max(min(score, 100), 0)
    return {
        "score": score,
        "penalties": penalties,
        "bonuses": bonuses,
        "details": f"{len(bonuses)} substance signals, {len(penalties)} generic patterns",
    }


def score_variety(text, existing_posts=None, config=None):
    """Score tweet for variety vs recent history. Returns dict with score, penalties, details.

    Two dimensions:
    1. Entity-based semantic dedup (catches IQM $300M posted 3x with different wording)
    2. Structural variety (penalizes same template used repeatedly)
    """
    score = 100
    penalties = []
    existing = existing_posts or []

    # --- Entity-based semantic dedup (0-50 of the 100 points) ---
    new_entities = _extract_entities(text)

    if new_entities and existing:
        worst_entity_overlap = 0.0
        most_similar = None

        for post in existing:
            content = post["content"] if isinstance(post, dict) else post[1]
            old_entities = _extract_entities(content)
            if not old_entities:
                continue

            intersection = new_entities & old_entities
            # Use overlap coefficient (intersection / min) instead of Jaccard
            # This catches cases where a short tweet reuses entities from a longer one
            min_size = min(len(new_entities), len(old_entities))
            overlap = len(intersection) / min_size if min_size else 0

            if overlap > worst_entity_overlap:
                worst_entity_overlap = overlap
                most_similar = content

        if worst_entity_overlap >= 0.7:
            score -= 50
            penalties.append(f"Entity duplicate ({worst_entity_overlap:.0%} overlap, -50)")
        elif worst_entity_overlap >= 0.5:
            penalty = int(worst_entity_overlap * 50)
            score -= penalty
            penalties.append(f"Similar entities ({worst_entity_overlap:.0%} overlap, -{penalty})")
        elif worst_entity_overlap >= 0.35:
            penalty = int(worst_entity_overlap * 30)
            score -= penalty
            penalties.append(f"Some entity overlap ({worst_entity_overlap:.0%}, -{penalty})")

    # --- Structural variety (0-50 of the 100 points) ---
    my_template = _classify_template(text)

    if existing:
        recent = existing[:10]  # Last 10 posts
        recent_templates = [_classify_template(
            p["content"] if isinstance(p, dict) else p[1]
        ) for p in recent]

        same_count = sum(1 for t in recent_templates if t == my_template)

        if same_count >= 4:
            score -= 40
            penalties.append(f'Template "{my_template}" used {same_count}/10 recent tweets (-40)')
        elif same_count >= 3:
            score -= 30
            penalties.append(f'Template "{my_template}" used {same_count}/10 recent tweets (-30)')
        elif same_count >= 2:
            score -= 15
            penalties.append(f'Template "{my_template}" used {same_count}/10 recent tweets (-15)')

    score = max(score, 0)
    return {
        "score": score,
        "penalties": penalties,
        "template": my_template,
        "details": f"Template: {my_template}, {len(penalties)} variety issues",
    }


def _extract_significant_words(text):
    """Extract significant words from text for similarity comparison."""
    clean = EMOJI_RE.sub("", text).lower()
    words = set(re.findall(r"[a-zA-Z]{4,}", clean))
    # Remove common filler words
    filler = {
        "this", "that", "with", "from", "have", "just", "more", "most",
        "about", "been", "will", "they", "their", "them", "than", "what",
        "when", "where", "which", "while", "your", "into", "also", "here",
        "breaking", "tweet", "people", "don't", "it's", "there", "because",
        "every", "still", "even", "back", "over", "after", "before",
    }
    return words - filler


def score_duplicate(text, existing_posts):
    """Score how similar a tweet is to existing posts. Returns dict with score and penalties.
    Score starts at 100 (unique) and drops with similarity.
    """
    if not existing_posts:
        return {"score": 100, "penalties": [], "details": "No history to compare", "most_similar": None}

    new_words = _extract_significant_words(text)
    if not new_words:
        return {"score": 100, "penalties": [], "details": "Too short to compare", "most_similar": None}

    worst_similarity = 0.0
    most_similar_content = None

    for post in existing_posts:
        content = post["content"] if isinstance(post, dict) else post[1]  # Handle both dict and Row
        old_words = _extract_significant_words(content)
        if not old_words:
            continue

        # Jaccard similarity
        intersection = new_words & old_words
        union = new_words | old_words
        similarity = len(intersection) / len(union) if union else 0

        if similarity > worst_similarity:
            worst_similarity = similarity
            most_similar_content = content

    score = 100
    penalties = []

    if worst_similarity >= 0.7:
        # Near-duplicate: massive penalty
        score = 0
        penalties.append(f"Near-duplicate ({worst_similarity:.0%} similar, -{100})")
    elif worst_similarity >= 0.5:
        # Very similar: heavy penalty
        penalty = int(worst_similarity * 100)
        score -= penalty
        penalties.append(f"Very similar to existing tweet ({worst_similarity:.0%}, -{penalty})")
    elif worst_similarity >= 0.35:
        # Somewhat similar: moderate penalty
        penalty = int(worst_similarity * 60)
        score -= penalty
        penalties.append(f"Overlapping topic ({worst_similarity:.0%}, -{penalty})")

    score = max(score, 0)
    return {
        "score": score,
        "penalties": penalties,
        "details": f"Max similarity: {worst_similarity:.0%}",
        "most_similar": most_similar_content[:80] if most_similar_content and worst_similarity >= 0.35 else None,
    }


def score_post(text, config=None, existing_posts=None):
    """Compute composite quality score for a tweet. Returns full breakdown.

    7-component system (financial data bot):
    - Substance (30%): Specific numbers, entities, data density
    - Data Accuracy (20%): Disclaimer present, numbers, no predictions
    - Tone (20%): Professional, neutral, source attribution
    - Variety (15%): Different from recent tweets in structure and topic
    - Anti-AI (15%): Avoids AI-tell patterns
    - Readability (15%): Accessible language
    - Format (5%): Emoji and formatting
    """
    cfg = _load_config(config)

    ai = score_ai_detection(text, cfg)
    readability = score_readability(text, cfg)
    emoji = score_emoji_compliance(text, cfg)
    substance = score_substance(text, cfg)
    variety = score_variety(text, existing_posts or [], cfg)
    tone = score_tone(text, cfg)
    data_accuracy = score_data_accuracy(text, cfg)

    # Legacy duplicate check (kept as hard blocker for near-duplicates)
    duplicate = score_duplicate(text, existing_posts or [])

    # 7-component weighting
    w_substance = cfg.get("weight_substance", 0.30)
    w_data_accuracy = cfg.get("weight_data_accuracy", 0.20)
    w_tone = cfg.get("weight_tone", 0.20)
    w_variety = cfg.get("weight_variety", 0.15)
    w_ai = cfg.get("weight_ai", 0.15)
    w_read = cfg.get("weight_readability", 0.15)
    w_emoji = cfg.get("weight_emoji", 0.05)

    # Normalize weights to sum to 1.0
    total_weight = w_substance + w_data_accuracy + w_tone + w_variety + w_ai + w_read + w_emoji
    if total_weight > 0:
        overall = (
            substance["score"] * (w_substance / total_weight)
            + data_accuracy["score"] * (w_data_accuracy / total_weight)
            + tone["score"] * (w_tone / total_weight)
            + variety["score"] * (w_variety / total_weight)
            + ai["score"] * (w_ai / total_weight)
            + readability["score"] * (w_read / total_weight)
            + emoji["score"] * (w_emoji / total_weight)
        )
    else:
        overall = 50.0

    # Legacy duplicate as hard blocker (entity dedup in variety handles soft cases)
    if duplicate["score"] < 100:
        dup_factor = duplicate["score"] / 100.0
        overall = overall * dup_factor

    overall = round(overall, 1)

    all_penalties = (
        substance["penalties"] + variety["penalties"]
        + ai["penalties"] + readability["penalties"]
        + emoji["penalties"] + duplicate["penalties"]
        + tone.get("penalties", [])
        + data_accuracy.get("penalties", [])
    )

    return {
        "overall": overall,
        "substance": substance,
        "tone": tone,
        "data_accuracy": data_accuracy,
        "vibes": tone,  # Backward compat alias
        "variety": variety,
        "ai": ai,
        "readability": readability,
        "emoji": emoji,
        "duplicate": duplicate,
        "penalties": all_penalties,
        "auto_reject": overall < cfg["auto_reject_below"],
        "below_minimum": overall < cfg["min_quality_score"],
    }
