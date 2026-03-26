from flask import Blueprint, render_template, request
from storage.database import get_stats, get_api_usage_summary, get_engagement_config, get_engagement_replies_today, get_schedule_config, get_kill_switch, get_analytics_config, get_daily_tweet_count
from limiter.budget_forecaster import get_budget_status
from limiter.system_health import get_system_health

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    stats = get_stats()
    usage = get_api_usage_summary()

    # Gather active processes info
    from scheduler.scheduler import scheduler
    from engagement.monitor import engagement_monitor

    processes = []

    # Scheduler — check both thread AND DB state
    sched_thread = scheduler.is_running
    sched_cfg = get_schedule_config()
    sched_db_active = bool(sched_cfg.get("is_active"))
    sched_running = sched_thread or sched_db_active
    next_post = scheduler.next_post_time
    approved = stats.get("approved", 0)
    if sched_running:
        if next_post:
            sched_detail = f"Next post: {next_post.strftime('%H:%M')} ({approved} in queue)"
        else:
            sched_detail = f"Active ({approved} scheduled posts)"
    else:
        sched_detail = f"Inactive ({approved} approved posts waiting)"
    processes.append({
        "name": "Post Scheduler",
        "active": sched_running,
        "detail": sched_detail,
    })

    # Engagement monitor
    eng_running = engagement_monitor.is_running
    eng_cfg = get_engagement_config()
    eng_today = get_engagement_replies_today()
    eng_max = eng_cfg.get("max_replies_per_day", 10)
    eng_interval = eng_cfg.get("poll_interval_minutes", 10)
    eng_polls = engagement_monitor.stats.get("polls", 0)
    if eng_running:
        eng_detail = f"Polling every {eng_interval}min | {eng_today}/{eng_max} replies today | {eng_polls} polls"
    else:
        eng_detail = f"Inactive | {eng_today}/{eng_max} replies today"
    processes.append({
        "name": "Engagement Monitor",
        "active": eng_running,
        "detail": eng_detail,
    })

    # Metrics collector
    try:
        from analytics.collector import metrics_collector
        coll_running = metrics_collector.is_running
        coll_stats = metrics_collector.stats
        coll_detail = f"Last: {coll_stats.get('last_collection', 'never')} | {coll_stats.get('tweets_scraped', 0)} tweets scraped"
    except Exception:
        coll_running = False
        coll_detail = "Not loaded"
    processes.append({
        "name": "Metrics Collector",
        "active": coll_running,
        "detail": coll_detail,
    })

    ks = get_kill_switch()

    # Budget status for dashboard card
    mistral_budget = get_budget_status("mistral")
    groq_budget = get_budget_status("groq")

    # System health
    health = get_system_health()

    # Autopilot data
    sched_cfg_full = get_schedule_config()
    tweets_today = get_daily_tweet_count()
    next_post = scheduler.next_post_time
    next_post_str = next_post.strftime('%H:%M UTC') if next_post else None

    return render_template("dashboard.html", stats=stats, usage=usage, processes=processes,
                           kill_switch_active=bool(ks.get("is_killed")),
                           kill_switch_reason=ks.get("killed_reason", ""),
                           mistral_budget=mistral_budget,
                           groq_budget=groq_budget,
                           health=health,
                           scheduler_active=sched_running,
                           schedule_config=sched_cfg_full,
                           tweets_today=tweets_today,
                           next_post_time=next_post_str)


@bp.route("/api/autopilot/toggle", methods=["POST"])
def api_autopilot_toggle():
    """Start or stop the autopilot scheduler."""
    from scheduler.scheduler import scheduler

    if scheduler.is_running:
        scheduler.stop()
    else:
        scheduler.start()

    return _autopilot_status_html()


@bp.route("/api/autopilot/status")
def api_autopilot_status():
    """Return autopilot widget HTML fragment (for HTMX auto-refresh)."""
    return _autopilot_status_html()


def _autopilot_status_html():
    """Generate the autopilot widget inner HTML."""
    from scheduler.scheduler import scheduler

    stats = get_stats()
    sched_cfg = get_schedule_config()
    active = scheduler.is_running or bool(sched_cfg.get("is_active"))
    next_post = scheduler.next_post_time
    next_post_str = next_post.strftime('%H:%M UTC') if next_post else None
    tweets_today = get_daily_tweet_count()
    approved = stats.get("approved", 0)
    posted = stats.get("posted", 0)
    tweets_per_day = sched_cfg.get("random_tweets_per_day", 20)

    # Status line
    if active and next_post_str:
        status_line = f"Next post: {next_post_str} &middot; {tweets_today} tweets posted today"
    elif active:
        status_line = f"Fetching content & building queue... &middot; {tweets_today} tweets posted today"
    else:
        status_line = "Press Start to begin automatic fetching, generating & posting"

    dot = "active" if active else "inactive"
    state_label = '<span style="color:var(--green);font-size:0.8rem">RUNNING</span>' if active else '<span style="color:var(--text-tertiary);font-size:0.8rem">STOPPED</span>'
    btn_class = "background:var(--red,#ef4444);color:white" if active else "background:var(--accent,#3b82f6);color:white"
    btn_text = "Stop" if active else "Start"

    return f'''
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.8rem">
        <div>
            <div style="font-size:1.1rem;font-weight:700;display:flex;align-items:center;gap:0.5rem">
                <span class="process-dot {dot}" style="width:10px;height:10px"></span>
                Autopilot {state_label}
            </div>
            <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:0.25rem">{status_line}</div>
        </div>
        <button hx-post="/api/autopilot/toggle" hx-target="#autopilot-widget" hx-swap="innerHTML"
                style="padding:0.5rem 1.8rem;border-radius:8px;font-weight:700;font-size:0.95rem;border:none;cursor:pointer;{btn_class}">
            {btn_text}
        </button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;font-size:0.78rem;text-align:center">
        <div style="background:var(--bg-secondary);border-radius:6px;padding:0.4rem">
            <div style="font-weight:700;font-size:1.05rem">{tweets_per_day}</div>
            <div style="color:var(--text-secondary)">tweets/day</div>
        </div>
        <div style="background:var(--bg-secondary);border-radius:6px;padding:0.4rem">
            <div style="font-weight:700;font-size:1.05rem">{approved}</div>
            <div style="color:var(--text-secondary)">in queue</div>
        </div>
        <div style="background:var(--bg-secondary);border-radius:6px;padding:0.4rem">
            <div style="font-weight:700;font-size:1.05rem">{tweets_today}</div>
            <div style="color:var(--text-secondary)">posted today</div>
        </div>
        <div style="background:var(--bg-secondary);border-radius:6px;padding:0.4rem">
            <div style="font-weight:700;font-size:1.05rem">{posted}</div>
            <div style="color:var(--text-secondary)">total posted</div>
        </div>
    </div>
    '''


@bp.route("/api/processes")
def api_processes():
    """Return process status cards HTML fragment (for HTMX auto-refresh)."""
    from scheduler.scheduler import scheduler
    from engagement.monitor import engagement_monitor

    stats = get_stats()
    eng_cfg = get_engagement_config()
    eng_today = get_engagement_replies_today()

    processes = []

    # Scheduler — check both thread AND DB state
    sched_thread = scheduler.is_running
    sched_cfg = get_schedule_config()
    sched_db_active = bool(sched_cfg.get("is_active"))
    sched_running = sched_thread or sched_db_active
    next_post = scheduler.next_post_time
    approved = stats.get("approved", 0)
    if sched_running:
        if next_post:
            detail = f"Next post: {next_post.strftime('%H:%M')} ({approved} in queue)"
        else:
            detail = f"Active ({approved} scheduled posts)"
    else:
        detail = f"Inactive ({approved} approved posts waiting)"
    processes.append(("Post Scheduler", sched_running, detail))

    # Engagement
    eng_running = engagement_monitor.is_running
    eng_max = eng_cfg.get("max_replies_per_day", 10)
    eng_interval = eng_cfg.get("poll_interval_minutes", 10)
    eng_polls = engagement_monitor.stats.get("polls", 0)
    if eng_running:
        detail = f"Polling every {eng_interval}min | {eng_today}/{eng_max} replies today | {eng_polls} polls"
    else:
        detail = f"Inactive | {eng_today}/{eng_max} replies today"
    processes.append(("Engagement Monitor", eng_running, detail))

    # Metrics Collector
    try:
        from analytics.collector import metrics_collector
        coll_running = metrics_collector.is_running
        coll_stats = metrics_collector.stats
        coll_detail = f"Last: {coll_stats.get('last_collection', 'never')} | {coll_stats.get('tweets_scraped', 0)} tweets scraped"
    except Exception:
        coll_running = False
        coll_detail = "Not loaded"
    processes.append(("Metrics Collector", coll_running, coll_detail))

    html = ""
    for name, active, detail in processes:
        dot = "active" if active else "inactive"
        color = "color:var(--green)" if active else "color:var(--text-tertiary)"
        label = "ON" if active else "OFF"
        html += (
            f'<div class="process-card">'
            f'<div class="process-dot {dot}"></div>'
            f'<div class="process-info">'
            f'<div class="process-name">{name}</div>'
            f'<div class="process-detail">{detail}</div>'
            f'</div>'
            f'<span style="font-size:0.68rem;font-weight:600;{color}">{label}</span>'
            f'</div>'
        )
    return html
