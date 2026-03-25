from flask import Blueprint, render_template
from storage.database import get_stats, get_api_usage_summary, get_engagement_config, get_engagement_replies_today, get_schedule_config, get_kill_switch, get_analytics_config
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

    return render_template("dashboard.html", stats=stats, usage=usage, processes=processes,
                           kill_switch_active=bool(ks.get("is_killed")),
                           kill_switch_reason=ks.get("killed_reason", ""),
                           mistral_budget=mistral_budget,
                           groq_budget=groq_budget,
                           health=health)


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
