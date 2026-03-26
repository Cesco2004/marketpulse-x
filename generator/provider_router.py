"""Provider router: routes LLM tasks to Mistral or Groq.

Decides which provider handles each task based on:
  1. Configured routing preferences
  2. API key availability
  3. Monthly budget status
  4. Automatic fallback if the preferred provider is unavailable
"""

import random

import config
from limiter.usage_limiter import usage_limiter


# Default routing: which provider handles each task
# Groq handles high-volume/low-complexity tasks (free, 6000 req/day).
TASK_ROUTING = {
    "rank_articles": "mistral",     # Low cost, precision matters
    "generate_posts": "groq",       # Largest single call -> offload
    "generate_reply": "mistral",    # Quality critical for engagement
    "moderation_check": "groq",     # High volume, binary output
}


def _is_available(provider):
    """Check if a provider is available (has API key and budget)."""
    if provider == "mistral":
        if not config.MISTRAL_API_KEY:
            return False
        allowed, _ = usage_limiter.check_mistral()
        return allowed
    elif provider == "groq":
        if not config.GROQ_API_KEY:
            return False
        allowed, _ = usage_limiter.check_groq()
        return allowed
    return False


def get_provider(task):
    """Return the provider name for a given task, with automatic fallback.

    Args:
        task: one of "rank_articles", "generate_posts", "generate_reply", "moderation_check"

    Returns:
        "mistral" or "groq"

    Raises:
        RuntimeError if no provider is available for the task.
    """
    preferred = TASK_ROUTING.get(task, "mistral")
    fallback = "groq" if preferred == "mistral" else "mistral"

    if _is_available(preferred):
        return preferred

    if _is_available(fallback):
        print(f"[Router] {preferred} unavailable for {task}, falling back to {fallback}")
        return fallback

    raise RuntimeError(f"No LLM provider available for task '{task}'. Both Mistral and Groq are blocked or unconfigured.")


def rank_articles(articles_text, prefiltered_articles, count=10):
    """Route rank_articles to the appropriate provider."""
    provider = get_provider("rank_articles")
    if provider == "groq":
        from generator.groq_generator import rank_articles as groq_rank
        return groq_rank(articles_text, prefiltered_articles, count)
    else:
        from generator.mistral_generator import rank_articles as mistral_rank
        return mistral_rank(articles_text, prefiltered_articles, count)


def _select_templates(count=3):
    """Select templates from the pool using weighted random selection.

    Returns list of (template_name, template_config) tuples.
    """
    templates = config.GENERATION_TEMPLATES
    if not templates:
        return []

    names = list(templates.keys())
    weights = [templates[n].get("weight", 1.0) for n in names]

    # Select without replacement (each template at most once per batch)
    selected = []
    available = list(zip(names, weights))
    for _ in range(min(count, len(available))):
        total = sum(w for _, w in available)
        if total <= 0:
            break
        r = random.uniform(0, total)
        cumulative = 0
        for i, (name, w) in enumerate(available):
            cumulative += w
            if r <= cumulative:
                selected.append((name, templates[name]))
                available.pop(i)
                break

    return selected


def generate_posts(articles_text):
    """Generate posts using template-based generation with automatic provider routing.

    Selects 2-3 templates randomly, generates tweets for each, and combines results.
    Falls back to legacy single-prompt generation if templates fail.
    """
    templates = _select_templates(count=3)

    if not templates:
        # Fallback to legacy single-prompt
        return _generate_legacy(articles_text)

    all_posts = []
    for template_name, template_config in templates:
        try:
            prompt = template_config["prompt"]
            meta = {
                "is_thread": template_config.get("is_thread", False),
                "is_poll": template_config.get("is_poll", False),
                "template_name": template_name,
            }

            provider = get_provider("generate_posts")
            if provider == "groq":
                from generator.groq_generator import generate_posts as groq_gen
                posts = groq_gen(articles_text, template_prompt=prompt, template_meta=meta)
            else:
                from generator.mistral_generator import generate_posts as mistral_gen
                posts = mistral_gen(articles_text, template_prompt=prompt, template_meta=meta)

            all_posts.extend(posts)
        except Exception as e:
            print(f"[Router] Template '{template_name}' failed: {e}")
            continue

    # If template generation produced nothing, fall back to legacy
    if not all_posts:
        return _generate_legacy(articles_text)

    return all_posts


def _generate_legacy(articles_text):
    """Legacy single-prompt generation (fallback)."""
    provider = get_provider("generate_posts")
    if provider == "groq":
        from generator.groq_generator import generate_posts as groq_gen
        return groq_gen(articles_text)
    else:
        from generator.mistral_generator import generate_posts as mistral_gen
        return mistral_gen(articles_text)


def moderation_check(text):
    """Route moderation to the appropriate provider."""
    provider = get_provider("moderation_check")
    if provider == "groq":
        from generator.groq_generator import moderation_check as groq_mod
        return groq_mod(text)
    else:
        # Mistral moderation uses the existing _llm_moderation_check
        from engagement.reply_generator import _llm_moderation_check
        return _llm_moderation_check(text)
