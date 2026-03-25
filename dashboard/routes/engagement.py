from flask import Blueprint, render_template, request

from storage.database import (
    get_engagement_config,
    update_engagement_config,
    get_target_accounts,
    add_target_account,
    update_target_account,
    delete_target_account,
    get_pending_engagement_replies,
    update_engagement_reply_status,
    get_engagement_history,
    get_engagement_replies_today,
)

bp = Blueprint("engagement", __name__)


@bp.route("/engagement")
def engagement_page():
    cfg = get_engagement_config()
    accounts = get_target_accounts()
    pending = get_pending_engagement_replies()
    history = get_engagement_history(limit=20)
    today_count = get_engagement_replies_today()

    # Check if monitor is running
    try:
        from engagement.monitor import engagement_monitor
        monitor_running = engagement_monitor.is_running
        monitor_stats = engagement_monitor.stats
    except Exception:
        monitor_running = False
        monitor_stats = {}

    return render_template(
        "engagement.html",
        config=cfg,
        accounts=accounts,
        pending=pending,
        history=history,
        today_count=today_count,
        monitor_running=monitor_running,
        monitor_stats=monitor_stats,
    )


@bp.route("/api/engagement/config", methods=["POST"])
def save_config():
    update_engagement_config(
        poll_interval_minutes=int(request.form.get("poll_interval_minutes", 10)),
        max_replies_per_day=int(request.form.get("max_replies_per_day", 10)),
        max_replies_per_account_per_day=int(request.form.get("max_replies_per_account_per_day", 3)),
        reply_delay_min_minutes=int(request.form.get("reply_delay_min_minutes", 2)),
        reply_delay_max_minutes=int(request.form.get("reply_delay_max_minutes", 15)),
        auto_reject_below=float(request.form.get("auto_reject_below", 35)),
        max_reply_length=int(request.form.get("max_reply_length", 280)),
        reply_window_hours=int(request.form.get("reply_window_hours", 6)),
        active_start_hour=int(request.form.get("active_start_hour", 8)),
        active_end_hour=int(request.form.get("active_end_hour", 23)),
    )
    return '<span style="color:var(--qb-green);font-size:0.75rem">Saved</span>'


@bp.route("/api/engagement/accounts/add", methods=["POST"])
def add_account():
    username = request.form.get("username", "").strip().lstrip("@")
    category = request.form.get("category", "general")
    reply_style = request.form.get("reply_style", "mixed")
    priority = int(request.form.get("priority", 2))

    if not username:
        return '<span style="color:var(--qb-red);font-size:0.75rem">Username required</span>'

    result = add_target_account(username, category, reply_style, priority)
    if result is None:
        return '<span style="color:var(--qb-red);font-size:0.75rem">Already exists</span>'

    return '<span style="color:var(--qb-green);font-size:0.75rem">Added. Refresh to see.</span>'


@bp.route("/api/engagement/accounts/<int:account_id>/toggle", methods=["POST"])
def toggle_account(account_id):
    accounts = get_target_accounts()
    account = next((a for a in accounts if a["id"] == account_id), None)
    if account:
        new_val = 0 if account["is_enabled"] else 1
        update_target_account(account_id, is_enabled=new_val)
        status = "ON" if new_val else "OFF"
        color = "var(--qb-green)" if new_val else "var(--qb-red)"
        return f'<span style="color:{color};font-size:0.75rem;font-weight:600">{status}</span>'
    return ""


@bp.route("/api/engagement/accounts/<int:account_id>/edit", methods=["GET"])
def edit_account_form(account_id):
    """Return an inline edit form row that replaces the account row."""
    accounts = get_target_accounts()
    a = next((acc for acc in accounts if acc["id"] == account_id), None)
    if not a:
        return ""

    categories = ["general", "quantum", "ai", "robotics", "tech", "influencer",
                   "competitor", "event", "journalist", "analyst", "finance", "media", "govmil"]
    styles = ["mixed", "complementary", "witty", "question", "hot_take", "agreement", "emoji_reaction"]

    cat_options = "".join(
        f'<option value="{c}" {"selected" if c == a["category"] else ""}>{c}</option>'
        for c in categories
    )
    style_options = "".join(
        f'<option value="{s}" {"selected" if s == a["reply_style"] else ""}>{s}</option>'
        for s in styles
    )
    prio_labels = {0: "0 (Super-High)", 1: "1 (High)", 2: "2 (Normal)", 3: "3 (Low)"}
    prio_options = "".join(
        f'<option value="{p}" {"selected" if p == a["priority"] else ""}>{label}</option>'
        for p, label in prio_labels.items()
    )

    aid = a["id"]
    username = a["username"]
    polled = a.get("last_polled_at") or "never"
    on = '<span style="color:var(--qb-green);font-weight:600">ON</span>'
    off = '<span style="color:var(--qb-red);font-weight:600">OFF</span>'
    status_html = on if a["is_enabled"] else off

    save_id = f"save-btn-{aid}"
    onchange = f"document.getElementById('{save_id}').style.opacity='1';document.getElementById('{save_id}').style.color='#fff';document.getElementById('{save_id}').style.fontWeight='600'"

    return (
        f'<tr id="account-row-{aid}">'
        f'<td><strong>@{username}</strong></td>'
        f'<td><select name="category" style="font-size:0.75rem;padding:0.2rem" onchange="{onchange}">{cat_options}</select></td>'
        f'<td><select name="reply_style" style="font-size:0.75rem;padding:0.2rem" onchange="{onchange}">{style_options}</select></td>'
        f'<td><select name="priority" style="font-size:0.75rem;padding:0.2rem" onchange="{onchange}">{prio_options}</select></td>'
        f'<td style="color:var(--qb-dim)">{polled}</td>'
        f'<td><span id="account-status-{aid}">{status_html}</span></td>'
        f'<td style="white-space:nowrap">'
        f'<button id="{save_id}" hx-post="/api/engagement/accounts/{aid}/save" hx-include="closest tr" hx-target="#account-row-{aid}" hx-swap="outerHTML"'
        f' class="outline" style="padding:0.15rem 0.5rem;font-size:0.7rem;color:var(--qb-dim);opacity:0.5;transition:all 0.2s">Save</button> '
        f'<button hx-get="/api/engagement/accounts/{aid}/row" hx-target="#account-row-{aid}" hx-swap="outerHTML"'
        f' class="outline" style="padding:0.15rem 0.5rem;font-size:0.7rem">Cancel</button>'
        f'</td>'
        f'</tr>'
    )


@bp.route("/api/engagement/accounts/<int:account_id>/save", methods=["POST"])
def save_account(account_id):
    """Save edited account and return the normal row."""
    category = request.form.get("category", "general")
    reply_style = request.form.get("reply_style", "mixed")
    priority = int(request.form.get("priority", 2))

    update_target_account(account_id, category=category, reply_style=reply_style, priority=priority)

    # Return the updated static row
    accounts = get_target_accounts()
    a = next((acc for acc in accounts if acc["id"] == account_id), None)
    if not a:
        return ""
    return _render_account_row(a)


@bp.route("/api/engagement/accounts/<int:account_id>/row", methods=["GET"])
def get_account_row(account_id):
    """Return the normal (non-edit) row for an account."""
    accounts = get_target_accounts()
    a = next((acc for acc in accounts if acc["id"] == account_id), None)
    if not a:
        return ""
    return _render_account_row(a)


def _render_account_row(a):
    """Render a single account table row as HTML."""
    aid = a["id"]
    username = a["username"]
    status_html = ('<span style="color:var(--qb-green);font-weight:600">ON</span>'
                   if a["is_enabled"]
                   else '<span style="color:var(--qb-red);font-weight:600">OFF</span>')
    err_html = f' <span style="color:var(--qb-red);font-size:0.7rem">({a["poll_errors"]} err)</span>' if a.get("poll_errors") else ""
    polled = a.get("last_polled_at") or "never"

    return (
        f'<tr id="account-row-{aid}">'
        f'<td><strong>@{username}</strong></td>'
        f'<td>{a["category"]}</td>'
        f'<td>{a["reply_style"]}</td>'
        f'<td>{a["priority"]}</td>'
        f'<td style="color:var(--qb-dim)">{polled}</td>'
        f'<td><span id="account-status-{aid}">{status_html}</span>{err_html}</td>'
        f'<td style="white-space:nowrap">'
        f'<button hx-post="/api/engagement/accounts/{aid}/toggle" hx-target="#account-status-{aid}" hx-swap="innerHTML"'
        f' class="outline" style="padding:0.15rem 0.5rem;font-size:0.7rem">Toggle</button> '
        f'<button hx-get="/api/engagement/accounts/{aid}/edit" hx-target="#account-row-{aid}" hx-swap="outerHTML"'
        f' class="outline" style="padding:0.15rem 0.5rem;font-size:0.7rem;color:var(--qb-blue,#60a5fa)">Edit</button> '
        f'<button hx-post="/api/engagement/accounts/{aid}/delete" hx-target="#account-row-{aid}" hx-swap="outerHTML"'
        f' hx-confirm="Delete @{username}?"'
        f' class="outline" style="padding:0.15rem 0.5rem;font-size:0.7rem;color:var(--qb-red)">Del</button>'
        f'</td>'
        f'</tr>'
    )


@bp.route("/api/engagement/accounts/<int:account_id>/delete", methods=["POST"])
def delete_account_route(account_id):
    delete_target_account(account_id)
    return ""


@bp.route("/api/engagement/monitor/toggle", methods=["POST"])
def toggle_monitor():
    from flask import request as req
    from engagement.monitor import engagement_monitor

    if engagement_monitor.is_running:
        engagement_monitor.stop()
    else:
        engagement_monitor.start()

    now_running = engagement_monitor.is_running

    if now_running:
        return (
            '<button hx-post="/api/engagement/monitor/toggle" hx-target="#monitor-controls" hx-swap="innerHTML"'
            ' class="outline" style="padding:0.25rem 0.75rem;font-size:0.75rem;color:var(--qb-red)">Stop</button>'
            '<span class="cascade-text" style="color:var(--qb-green);font-weight:600">'
            '<span>R</span>'
            '<span style="animation:cascade 6s ease 0.0s infinite;opacity:0">u</span>'
            '<span style="animation:cascade 6s ease 0.15s infinite;opacity:0">n</span>'
            '<span style="animation:cascade 6s ease 0.3s infinite;opacity:0">n</span>'
            '<span style="animation:cascade 6s ease 0.45s infinite;opacity:0">i</span>'
            '<span style="animation:cascade 6s ease 0.6s infinite;opacity:0">n</span>'
            '<span style="animation:cascade 6s ease 0.75s infinite;opacity:0">g</span>'
            '</span>'
        )
    else:
        return (
            '<span class="fade-out-delayed" style="color:var(--qb-red);font-weight:600">Stopped</span>'
            '<button hx-post="/api/engagement/monitor/toggle" hx-target="#monitor-controls" hx-swap="innerHTML"'
            ' class="outline" style="padding:0.25rem 0.75rem;font-size:0.75rem">Start</button>'
            '<button hx-post="/api/engagement/poll-now" hx-swap="innerHTML" hx-target="#poll-result"'
            ' class="outline" style="padding:0.25rem 0.75rem;font-size:0.75rem">Poll Now</button>'
            '<span id="poll-result"></span>'
        )


@bp.route("/api/engagement/poll-now", methods=["POST"])
def poll_now():
    from engagement.monitor import engagement_monitor

    result = engagement_monitor.poll_once()
    tweets = result.get("new_tweets", 0)
    replies = result.get("replies_generated", 0)
    posted = result.get("replies_posted", 0)
    return f'<span style="font-size:0.75rem">Done: {tweets} tweets, {replies} replies generated, {posted} posted</span>'


@bp.route("/api/engagement/replies/<int:reply_id>/reject", methods=["POST"])
def reject_reply(reply_id):
    update_engagement_reply_status(reply_id, "rejected")
    return '<span style="color:var(--qb-red);font-size:0.75rem">Rejected</span>'


@bp.route("/api/engagement/replies/<int:reply_id>/post-now", methods=["POST"])
def post_reply_now(reply_id):
    from storage.database import get_connection, mark_engagement_reply_posted
    from engagement.twitter_reader import twitter_reader

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM engagement_replies WHERE id = ?", (reply_id,))
    reply = cursor.fetchone()
    conn.close()

    if not reply:
        return '<span style="color:var(--qb-red);font-size:0.75rem">Not found</span>'

    try:
        tweet_id = twitter_reader.reply_to_tweet(reply["original_tweet_id"], reply["reply_content"])
        mark_engagement_reply_posted(reply_id, tweet_id)
        return f'<span style="color:var(--qb-green);font-size:0.75rem">Posted (ID: {tweet_id})</span>'
    except Exception as e:
        return f'<span style="color:var(--qb-red);font-size:0.75rem">Error: {e}</span>'
