import json
from flask import Blueprint, render_template, request

from storage.database import get_quality_config, update_quality_config, get_topic_categories, update_topic_category, get_image_config, update_image_config
from scoring.quality_scorer import score_post

bp = Blueprint("settings", __name__)


@bp.route("/settings")
def settings_page():
    tab = request.args.get("tab", "quality")
    qconfig = get_quality_config()
    categories = get_topic_categories()

    # Parse JSON lists for template
    ai_phrases = []
    jargon_list = []
    emoji_list = []
    try:
        ai_phrases = json.loads(qconfig.get("ai_penalty_phrases", "[]"))
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        jargon_list = json.loads(qconfig.get("readability_jargon_list", "[]"))
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        emoji_list = json.loads(qconfig.get("emoji_preferred", "[]"))
    except (json.JSONDecodeError, TypeError):
        pass

    iconfig = get_image_config()

    return render_template(
        "settings.html",
        tab=tab,
        qconfig=qconfig,
        ai_phrases=ai_phrases,
        jargon_list=jargon_list,
        emoji_list=emoji_list,
        categories=categories,
        iconfig=iconfig,
    )


@bp.route("/api/settings/quality", methods=["POST"])
def save_quality_config():
    form = request.form

    updates = {}

    # Toggles
    updates["ai_detection_enabled"] = 1 if form.get("ai_detection_enabled") else 0
    updates["readability_enabled"] = 1 if form.get("readability_enabled") else 0
    updates["emoji_enabled"] = 1 if form.get("emoji_enabled") else 0

    # Weights (all 7 components)
    try:
        weight_keys = ["weight_substance", "weight_tone", "weight_data_accuracy",
                       "weight_variety", "weight_ai", "weight_readability", "weight_emoji"]
        defaults = [0.30, 0.25, 0.20, 0.15, 0.15, 0.15, 0.05]
        raw = {}
        for key, default in zip(weight_keys, defaults):
            raw[key] = float(form.get(key, default))
        total = sum(raw.values())
        if total > 0:
            for key in weight_keys:
                updates[key] = round(raw[key] / total, 3)
    except (ValueError, TypeError):
        pass

    # Thresholds
    try:
        updates["min_quality_score"] = float(form.get("min_quality_score", 50))
    except (ValueError, TypeError):
        pass
    try:
        updates["auto_reject_below"] = float(form.get("auto_reject_below", 30))
    except (ValueError, TypeError):
        pass
    try:
        updates["auto_approve_above"] = float(form.get("auto_approve_above", 70))
    except (ValueError, TypeError):
        pass

    # Penalties
    try:
        updates["ai_emdash_penalty"] = int(form.get("ai_emdash_penalty", 15))
    except (ValueError, TypeError):
        pass
    try:
        updates["ai_phrase_penalty"] = int(form.get("ai_phrase_penalty", 10))
    except (ValueError, TypeError):
        pass
    try:
        updates["readability_jargon_penalty"] = int(form.get("readability_jargon_penalty", 8))
    except (ValueError, TypeError):
        pass
    try:
        updates["readability_max_grade_level"] = int(form.get("readability_max_grade_level", 10))
    except (ValueError, TypeError):
        pass
    try:
        updates["emoji_leading_bonus"] = int(form.get("emoji_leading_bonus", 50))
    except (ValueError, TypeError):
        pass

    # Lists (textarea, one per line)
    ai_phrases_raw = form.get("ai_penalty_phrases", "")
    if ai_phrases_raw.strip():
        phrases = [p.strip() for p in ai_phrases_raw.strip().split("\n") if p.strip()]
        updates["ai_penalty_phrases"] = json.dumps(phrases)

    jargon_raw = form.get("readability_jargon_list", "")
    if jargon_raw.strip():
        jargon = [j.strip() for j in jargon_raw.strip().split("\n") if j.strip()]
        updates["readability_jargon_list"] = json.dumps(jargon)

    emoji_raw = form.get("emoji_preferred", "")
    if emoji_raw.strip():
        emojis = [e.strip() for e in emoji_raw.strip().split() if e.strip()]
        updates["emoji_preferred"] = json.dumps(emojis)

    update_quality_config(**updates)

    return '<div style="color:var(--qb-green);font-size:0.85rem;padding:0.5rem">Settings saved successfully.</div>'


@bp.route("/api/settings/test-score", methods=["POST"])
def test_score():
    text = request.form.get("text", "")
    if not text.strip():
        return '<div style="color:var(--qb-dim);font-size:0.8rem">Enter a tweet to test.</div>'

    qconfig = get_quality_config()
    result = score_post(text, qconfig)

    overall = result["overall"]
    if overall >= 70:
        color = "var(--qb-green)"
    elif overall >= 50:
        color = "var(--qb-yellow)"
    else:
        color = "var(--qb-red)"

    # Build component breakdown
    components = [
        ("Substance", result.get("substance", {}).get("score")),
        ("Tone", result.get("tone", {}).get("score")),
        ("Data Acc.", result.get("data_accuracy", {}).get("score")),
        ("Variety", result.get("variety", {}).get("score")),
        ("Anti-AI", result["ai"]["score"]),
        ("Readability", result["readability"]["score"]),
        ("Format", result["emoji"]["score"]),
    ]

    html = f'<div class="post-card" style="margin-top:0.5rem">'
    html += f'<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">'
    html += f'<span class="score-badge" style="background:rgba(99,102,241,0.15);color:{color};font-size:1.1rem;font-weight:800">{overall:.0f}</span>'
    html += '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;font-size:0.72rem">'
    for label, score in components:
        if score is not None:
            s = int(round(score))
            sc = "var(--qb-green)" if s >= 70 else ("var(--qb-accent-soft)" if s >= 50 else "var(--qb-red)")
            html += f'<span style="color:{sc}">{label}:{s}</span>'
    html += '</div></div>'

    if result["penalties"]:
        html += '<div style="display:flex;flex-wrap:wrap;gap:0.25rem">'
        for p in result["penalties"]:
            html += f'<span class="penalty-tag">{p}</span>'
        html += '</div>'
    else:
        html += '<span style="color:var(--qb-green);font-size:0.8rem">No penalties detected.</span>'

    html += '</div>'
    return html


@bp.route("/api/settings/categories", methods=["POST"])
def save_categories():
    form = request.form
    categories = get_topic_categories()
    for cat in categories:
        enabled_key = f"cat_enabled_{cat['id']}"
        weight_key = f"cat_weight_{cat['id']}"
        is_enabled = 1 if form.get(enabled_key) else 0
        try:
            weight = float(form.get(weight_key, cat["weight"]))
        except (ValueError, TypeError):
            weight = cat["weight"]
        update_topic_category(cat["id"], is_enabled=is_enabled, weight=weight)

    return '<div style="color:var(--qb-green);font-size:0.85rem;padding:0.5rem">Categories updated.</div>'


@bp.route("/api/settings/images", methods=["POST"])
def save_image_config():
    form = request.form
    updates = {}
    updates["images_enabled"] = 1 if form.get("images_enabled") else 0
    updates["prefer_article_images"] = 1 if form.get("prefer_article_images") else 0
    try:
        updates["image_ratio"] = float(form.get("image_ratio", 0.66))
    except (ValueError, TypeError):
        pass
    try:
        updates["min_image_score"] = float(form.get("min_image_score", 50))
    except (ValueError, TypeError):
        pass
    unsplash = form.get("unsplash_api_key", "").strip()
    if unsplash:
        updates["unsplash_api_key"] = unsplash
    pexels = form.get("pexels_api_key", "").strip()
    if pexels:
        updates["pexels_api_key"] = pexels

    update_image_config(**updates)
    return '<div style="color:var(--qb-green);font-size:0.85rem;padding:0.5rem">Image settings saved.</div>'


@bp.route("/api/settings/tab/quality")
def quality_tab():
    """Return quality settings content (redirects to full page for simplicity)."""
    from flask import redirect
    return redirect("/settings?tab=quality")


@bp.route("/api/settings/tab/budget")
def budget_tab():
    """Return API budget content as HTML fragment."""
    from storage.database import get_api_usage_summary, get_monthly_usage, get_monthly_usage_by_day, get_monthly_usage_by_endpoint
    from limiter.budget_forecaster import get_budget_status

    usage = get_api_usage_summary()
    mistral_budget = get_budget_status("mistral")
    groq_budget = get_budget_status("groq")

    mistral_monthly = get_monthly_usage("mistral")
    groq_monthly = get_monthly_usage("groq")
    mistral_by_day = get_monthly_usage_by_day("mistral")
    mistral_by_endpoint = get_monthly_usage_by_endpoint("mistral")
    groq_by_endpoint = get_monthly_usage_by_endpoint("groq")

    return render_template("_budget_tab.html",
                           usage=usage,
                           mistral_budget=mistral_budget,
                           groq_budget=groq_budget,
                           mistral_monthly=mistral_monthly,
                           groq_monthly=groq_monthly,
                           mistral_by_day=mistral_by_day,
                           mistral_by_endpoint=mistral_by_endpoint,
                           groq_by_endpoint=groq_by_endpoint)


@bp.route("/api/settings/tab/safety")
def safety_tab():
    """Return safety/limits content as HTML fragment."""
    from storage.database import get_usage_limits, get_kill_switch, get_recent_alerts, get_monthly_budget
    from limiter.budget_forecaster import get_budget_status, get_throttle_recommendations

    limits = get_usage_limits()
    ks = get_kill_switch()
    alerts = get_recent_alerts()
    budget = get_monthly_budget()
    mistral_budget = get_budget_status("mistral")
    throttle = get_throttle_recommendations("mistral")

    return render_template("_safety_tab.html",
                           limits=limits,
                           kill_switch=ks,
                           alerts=alerts,
                           budget=budget,
                           mistral_budget=mistral_budget,
                           throttle=throttle)
