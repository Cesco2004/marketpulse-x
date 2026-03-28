from flask import Blueprint, render_template, request

from storage.database import (
    get_usage_limits,
    update_usage_limits,
    get_kill_switch,
    set_kill_switch,
    get_recent_alerts,
    get_monthly_budget,
    update_monthly_budget,
)
from limiter.usage_limiter import usage_limiter
from limiter.alerts import send_alert_email
from limiter.budget_forecaster import get_budget_status, get_throttle_recommendations

bp = Blueprint("limits", __name__)


def _get_alert_emails(limits):
    """Parse alert_email field (comma-separated) into a list."""
    raw = limits.get("alert_email", "")
    if not raw:
        return []
    return [e.strip() for e in raw.split(",") if e.strip()]


def _render_page(**extra):
    status = usage_limiter.get_status()
    limits = get_usage_limits()
    ks = get_kill_switch()
    alerts = get_recent_alerts(limit=15)
    alert_emails = _get_alert_emails(limits)
    budget = get_monthly_budget()
    mistral_budget = get_budget_status("mistral")
    groq_budget = get_budget_status("groq")
    throttle = get_throttle_recommendations("mistral")
    return render_template("limits.html", status=status, limits=limits, ks=ks,
                           alerts=alerts, alert_emails=alert_emails,
                           budget=budget, mistral_budget=mistral_budget,
                           groq_budget=groq_budget, throttle=throttle, **extra)


@bp.route("/limits")
def limits_page():
    from flask import redirect
    return redirect("/settings?tab=safety")


@bp.route("/api/limits/save-limits", methods=["POST"])
def save_limits():
    cost_str = request.form.get("mistral_max_cost_per_day", "1.00").replace(",", ".")
    update_usage_limits(
        mistral_max_tokens_per_day=int(request.form.get("mistral_max_tokens_per_day", 500000)),
        mistral_max_calls_per_day=int(request.form.get("mistral_max_calls_per_day", 50)),
        mistral_max_cost_per_day=float(cost_str),
        x_max_tweets_per_day=int(request.form.get("x_max_tweets_per_day", 15)),
        x_max_replies_per_day=int(request.form.get("x_max_replies_per_day", 10)),
        warning_threshold_pct=int(request.form.get("warning_threshold_pct", 80)),
        max_consecutive_errors=int(request.form.get("max_consecutive_errors", 5)),
    )
    return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "API limits saved!", "type": "success"}}'}


@bp.route("/api/limits/save-email", methods=["POST"])
def save_email():
    update_usage_limits(
        smtp_host=request.form.get("smtp_host", "smtp.gmail.com").strip(),
        smtp_port=int(request.form.get("smtp_port", 587)),
        smtp_user=request.form.get("smtp_user", "").strip(),
        smtp_password=request.form.get("smtp_password", "").strip(),
        alerts_enabled=1 if request.form.get("alerts_enabled") else 0,
        daily_summary_enabled=1 if request.form.get("daily_summary_enabled") else 0,
    )
    return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "Email settings saved!", "type": "success"}}'}


@bp.route("/api/limits/add-email", methods=["POST"])
def add_email():
    new_email = request.form.get("new_email", "").strip()
    if not new_email:
        return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "No email provided", "type": "error"}}'}

    limits = get_usage_limits()
    emails = _get_alert_emails(limits)
    if new_email in emails:
        return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "Email already added", "type": "error"}}'}

    emails.append(new_email)
    update_usage_limits(alert_email=", ".join(emails))
    return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "' + new_email + ' added!", "type": "success"}}'}


@bp.route("/api/limits/remove-email", methods=["POST"])
def remove_email():
    email_to_remove = request.form.get("email", "").strip()
    limits = get_usage_limits()
    emails = _get_alert_emails(limits)
    emails = [e for e in emails if e != email_to_remove]
    update_usage_limits(alert_email=", ".join(emails))
    return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "' + email_to_remove + ' removed", "type": "info"}}'}


@bp.route("/api/limits/save-budget", methods=["POST"])
def save_budget():
    update_monthly_budget(
        mistral_monthly_token_limit=int(request.form.get("mistral_monthly_token_limit", 1000000)),
        groq_monthly_token_limit=int(request.form.get("groq_monthly_token_limit", 1500000)),
        auto_throttle_enabled=1 if request.form.get("auto_throttle_enabled") else 0,
        throttle_start_pct=int(request.form.get("throttle_start_pct", 70)),
        throttle_medium_pct=int(request.form.get("throttle_medium_pct", 85)),
        emergency_stop_pct=int(request.form.get("emergency_stop_pct", 95)),
        budget_alert_threshold_pct=int(request.form.get("budget_alert_threshold_pct", 75)),
    )
    return _render_page(), 200, {"HX-Trigger": '{"showToast": {"message": "Monthly budget saved!", "type": "success"}}'}


@bp.route("/api/kill-switch/toggle", methods=["POST"])
def toggle_kill_switch():
    ks = get_kill_switch()
    if ks.get("is_killed"):
        set_kill_switch(False)
        msg = "Kill switch deactivated"
    else:
        reason = request.form.get("reason", "Dashboard toggle")
        set_kill_switch(True, reason=reason, killed_by="dashboard")
        msg = "Kill switch activated"
    return _render_page(), 200, {"HX-Trigger": f'{{"showToast": {{"message": "{msg}", "type": "info"}}}}'}


@bp.route("/api/limits/test-email", methods=["POST"])
def test_email():
    ok = send_alert_email("Test alert", "This is a test email from QEdge Intel Bot.\n\nIf you see this, email alerts are working.")
    if ok:
        return "", 200, {"HX-Trigger": '{"showToast": {"message": "Test email sent!", "type": "success"}}'}
    else:
        return "", 200, {"HX-Trigger": '{"showToast": {"message": "Failed to send email. Check SMTP settings.", "type": "error"}}'}


@bp.route("/api/limits/status")
def api_limits_status():
    """Return usage bars HTML fragment for HTMX auto-refresh."""
    status = usage_limiter.get_status()
    return _render_bars(status)


def _render_bars(s):
    def bar(label, current, max_val, pct, fmt="{}"):
        color = "var(--green)" if pct < 60 else "var(--yellow)" if pct < 85 else "var(--red)"
        return (
            f'<div class="limit-bar">'
            f'<div class="limit-label"><span>{label}</span><span>{fmt.format(current)} / {fmt.format(max_val)}</span></div>'
            f'<div class="progress-track"><div class="progress-fill" style="width:{min(pct,100):.0f}%;background:{color}"></div></div>'
            f'</div>'
        )

    def section(title):
        return f'<div style="font-size:0.72rem;color:var(--text-secondary);margin:0.6rem 0 0.3rem;font-weight:600">{title}</div>'

    # Mistral daily
    html = section("Mistral")
    html += bar("Calls", s["mistral_calls"], s["mistral_calls_max"], s["mistral_calls_pct"])
    html += bar("Tokens", s["mistral_tokens"], s["mistral_tokens_max"], s["mistral_tokens_pct"])
    html += bar("Cost", s["mistral_cost"], s["mistral_cost_max"], s["mistral_cost_pct"], fmt="${:.4f}")

    # Groq daily
    groq_calls = s.get("groq_calls", 0)
    groq_tokens = s.get("groq_tokens", 0)
    html += section("Groq")
    fill = "5" if groq_calls > 0 else "0"
    html += (
        f'<div class="limit-bar">'
        f'<div class="limit-label"><span>Calls</span><span>{groq_calls} today &middot; {groq_tokens:,} tokens</span></div>'
        f'<div class="progress-track"><div class="progress-fill" style="width:{fill}%;background:var(--green)"></div></div>'
        f'</div>'
    )

    # X/Twitter daily
    html += section("X / Twitter")
    html += bar("Tweets", s["x_tweets"], s["x_tweets_max"], s["x_tweets_pct"])
    html += bar("Replies", s["x_replies"], s["x_replies_max"], s["x_replies_pct"])

    # Monthly
    html += section("This Month")
    html += bar("Mistral", s.get("mistral_monthly_tokens", 0), s.get("mistral_monthly_limit", 1000000), s.get("mistral_monthly_pct", 0))
    html += bar("Groq", s.get("groq_monthly_tokens", 0), s.get("groq_monthly_limit", 1500000), s.get("groq_monthly_pct", 0))

    return html
