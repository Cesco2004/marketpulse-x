import calendar as cal
from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, request
from storage.database import get_connection, get_schedule_config, update_schedule_config
import pytz

bp = Blueprint("calendar", __name__)


def _get_tz(tz_name):
    try:
        return pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        return pytz.timezone("Europe/Paris")


def _to_local_time(dt_str, tz):
    """Convert a UTC datetime string to local HH:MM."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(tz).strftime("%H:%M")
    except Exception:
        return dt_str[11:16] if len(dt_str) > 16 else ""


def _get_month_data(year, month):
    today = date.today()
    first_day = date(year, month, 1)
    _, days_in_month = cal.monthrange(year, month)
    last_day = date(year, month, days_in_month)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM posts
        WHERE (posted_at IS NOT NULL AND date(posted_at) BETWEEN ? AND ?)
           OR (status IN ('pending_review', 'approved') AND date(created_at) BETWEEN ? AND ?)
           OR (scheduled_at IS NOT NULL AND date(scheduled_at) BETWEEN ? AND ?)
        ORDER BY
            CASE status WHEN 'approved' THEN 0 WHEN 'pending_review' THEN 1 ELSE 2 END,
            COALESCE(posted_at, scheduled_at, created_at) DESC
    """, (first_day.isoformat(), last_day.isoformat(),
          first_day.isoformat(), last_day.isoformat(),
          first_day.isoformat(), last_day.isoformat()))
    posts = cursor.fetchall()
    conn.close()

    posts_by_date = {}
    for post in posts:
        # Use scheduled_at date for approved posts, posted_at for posted, created_at fallback
        if post["status"] == "approved" and post["scheduled_at"]:
            post_date = post["scheduled_at"][:10]
        elif post["status"] == "posted" and post["posted_at"]:
            post_date = post["posted_at"][:10]
        else:
            post_date = (post["created_at"] or "")[:10]

        if post_date:
            if post_date not in posts_by_date:
                posts_by_date[post_date] = []
            posts_by_date[post_date].append(dict(post))

    start_weekday = first_day.weekday()
    weeks = []
    current_week = [None] * start_weekday

    for day_num in range(1, days_in_month + 1):
        d = date(year, month, day_num)
        day_posts = posts_by_date.get(d.isoformat(), [])
        dot = None
        if day_posts:
            statuses = {p["status"] for p in day_posts}
            if "posted" in statuses:
                dot = "green"
            elif "approved" in statuses:
                dot = "accent"
            else:
                dot = "red"
        current_week.append({
            "num": day_num, "date": d.isoformat(), "is_today": d == today,
            "posts": day_posts, "dot": dot, "count": len(day_posts),
        })
        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []
    if current_week:
        current_week += [None] * (7 - len(current_week))
        weeks.append(current_week)

    return weeks, posts_by_date


def _validate_random_config(config):
    min_gap = config.get("random_min_gap_hours", 0) * 60 + config.get("random_min_gap_minutes", 0)
    max_gap = config.get("random_max_gap_hours", 0) * 60 + config.get("random_max_gap_minutes", 0)
    start = config.get("random_start_hour", 9) * 60 + config.get("random_start_minute", 0)
    end = config.get("random_end_hour", 22) * 60 + config.get("random_end_minute", 0)
    tweets = config.get("random_tweets_per_day", 1)

    if min_gap < 1:
        return "Min gap must be at least 1 minute."
    if max_gap < min_gap:
        return "Max gap must be greater than min gap."
    if end <= start:
        return "End time must be after start time."
    window_minutes = end - start
    min_time_needed = min_gap * (tweets - 1) if tweets > 1 else 0
    if min_time_needed > window_minutes:
        return f"Not enough time: {tweets} tweets need {min_time_needed}min minimum, but window is {window_minutes}min."
    return None


@bp.route("/calendar")
def calendar_page():
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    selected_date = request.args.get("date")

    weeks, posts_by_date = _get_month_data(year, month)
    month_name = date(year, month, 1).strftime("%B %Y")

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    schedule = get_schedule_config()
    tz_name = schedule.get("timezone", "Europe/Paris")
    tz = _get_tz(tz_name)
    tz_label = datetime.now(tz).strftime("%Z")

    from scheduler.scheduler import scheduler as sched_instance
    sched_running = sched_instance.is_running
    next_post_display = None
    if sched_instance.next_post_time:
        try:
            npt = pytz.utc.localize(sched_instance.next_post_time).astimezone(tz)
            next_post_display = npt.strftime("%H:%M %Z")
        except Exception:
            next_post_display = sched_instance.next_post_time.strftime("%H:%M UTC")

    # Enrich selected day posts with local times
    selected_day_posts = []
    selected_day_label = ""
    if selected_date and selected_date in posts_by_date:
        for p in posts_by_date[selected_date]:
            if p["status"] == "posted":
                p["local_time"] = _to_local_time(p.get("posted_at"), tz)
            elif p["status"] == "approved" and p.get("scheduled_at"):
                p["local_time"] = _to_local_time(p["scheduled_at"], tz)
            else:
                p["local_time"] = ""
        selected_day_posts = posts_by_date[selected_date]
        try:
            selected_day_label = datetime.strptime(selected_date, "%Y-%m-%d").strftime("%A, %B %d")
        except ValueError:
            selected_day_label = selected_date

    total_posted = sum(1 for posts in posts_by_date.values() for p in posts if p["status"] == "posted")
    total_approved = sum(1 for posts in posts_by_date.values() for p in posts if p["status"] == "approved")
    total_pending = sum(1 for posts in posts_by_date.values() for p in posts if p["status"] == "pending_review")
    active_days = len([d for d in posts_by_date.values() if d])

    validation_error = _validate_random_config(schedule) if schedule.get("mode") == "random" else None

    return render_template(
        "calendar.html",
        weeks=weeks, month_name=month_name,
        year=year, month=month,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        selected_date=selected_date,
        selected_day_posts=selected_day_posts,
        selected_day_label=selected_day_label,
        total_posted=total_posted, total_approved=total_approved,
        total_pending=total_pending, active_days=active_days,
        schedule=schedule, tz_label=tz_label,
        sched_running=sched_running, next_post=next_post_display,
        validation_error=validation_error,
    )


@bp.route("/api/schedule/save", methods=["POST"])
def save_schedule():
    mode = request.form.get("mode", "fixed")

    if mode == "fixed":
        update_schedule_config(
            mode="fixed",
            fixed_interval_hours=int(request.form.get("fixed_hours", 24)),
            fixed_interval_minutes=int(request.form.get("fixed_minutes", 0)),
        )
    else:
        config = {
            "mode": "random",
            "random_tweets_per_day": int(request.form.get("tweets_per_day", 1)),
            "random_min_gap_hours": int(request.form.get("min_gap_h", 3)),
            "random_min_gap_minutes": int(request.form.get("min_gap_m", 0)),
            "random_max_gap_hours": int(request.form.get("max_gap_h", 15)),
            "random_max_gap_minutes": int(request.form.get("max_gap_m", 0)),
            "random_start_hour": int(request.form.get("start_hour", 9)),
            "random_start_minute": int(request.form.get("start_minute", 0)),
            "random_end_hour": int(request.form.get("end_hour", 22)),
            "random_end_minute": int(request.form.get("end_minute", 0)),
        }
        error = _validate_random_config(config)
        if error:
            return f'<div style="color:var(--qb-red);font-size:0.72rem;padding:0.4rem;background:rgba(248,113,113,0.1);border-radius:4px;margin-top:0.3rem">{error}</div>'
        update_schedule_config(**config)

    # Always (re)start scheduler after save
    from scheduler.scheduler import scheduler as sched_instance
    if sched_instance.is_running:
        sched_instance.stop()
    sched_instance.start()

    return '<div style="color:var(--qb-green);font-size:0.72rem;padding:0.3rem;margin-top:0.3rem">Settings saved & scheduler started.</div>'


@bp.route("/api/schedule/toggle", methods=["POST"])
def toggle_scheduler():
    from scheduler.scheduler import scheduler as sched_instance
    if sched_instance.is_running:
        sched_instance.stop()
        return '<button class="btn-fetch" style="font-size:0.72rem;padding:0.3rem 0.8rem" hx-post="/api/schedule/toggle" hx-target="#sched-toggle" hx-swap="innerHTML">Start</button>'
    else:
        sched_instance.start()
        return '<button class="outline" style="font-size:0.72rem;padding:0.3rem 0.8rem;border-color:var(--qb-red);color:var(--qb-red)" hx-post="/api/schedule/toggle" hx-target="#sched-toggle" hx-swap="innerHTML">Stop</button>'


@bp.route("/api/schedule/status")
def schedule_status():
    """Lightweight endpoint for polling scheduler status."""
    from scheduler.scheduler import scheduler as sched_instance
    schedule = get_schedule_config()
    tz_name = schedule.get("timezone", "Europe/Paris")
    tz = _get_tz(tz_name)

    sched_running = sched_instance.is_running
    next_post_display = None
    if sched_instance.next_post_time:
        try:
            npt = pytz.utc.localize(sched_instance.next_post_time).astimezone(tz)
            next_post_display = npt.strftime("%H:%M %Z")
        except Exception:
            next_post_display = sched_instance.next_post_time.strftime("%H:%M UTC")

    status_color = "var(--qb-green)" if sched_running else "var(--qb-dim)"
    status_text = "Active"
    if sched_running and next_post_display:
        status_text += f" &middot; next {next_post_display}"
    elif not sched_running:
        status_text = "Inactive"

    toggle_btn = ""
    if sched_running:
        toggle_btn = '<button class="outline" style="font-size:0.72rem;padding:0.25rem 0.7rem;border-color:var(--qb-red);color:var(--qb-red)" hx-post="/api/schedule/toggle" hx-target="#sched-toggle" hx-swap="innerHTML">Stop</button>'
    else:
        toggle_btn = '<button class="btn-fetch" style="font-size:0.72rem;padding:0.25rem 0.7rem" hx-post="/api/schedule/toggle" hx-target="#sched-toggle" hx-swap="innerHTML">Start</button>'

    return f'''
    <span style="font-size:0.75rem;color:{status_color}">{status_text}</span>
    <span id="sched-toggle">{toggle_btn}</span>
    '''
