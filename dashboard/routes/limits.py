from flask import Blueprint, render_template, request

from storage.database import (
    get_usage_limits,
    update_usage_limits,
    get_kill_switch,
    set_kill_switch,
    get_recent_alerts,
)
from limiter.usage_limiter import usage_limiter
from limiter.alerts import send_alert_email

bp = Blueprint("limits", __name__)


@bp.route("/limits")
def limits_page():
    status = usage_limiter.get_status()
    limits = get_usage_limits()
    ks = get_kill_switch()
    alerts = get_recent_alerts(limit=15)
    return render_template("limits.html", status=status, limits=limits, ks=ks, alerts=alerts)


@bp.route("/api/limits/save", methods=["POST"])
def save_limits():
    # Handle comma as decimal separator (French locale)
    cost_str = request.form.get("mistral_max_cost_per_day", "1.00").replace(",", ".")
    update_usage_limits(
        mistral_max_tokens_per_day=int(request.form.get("mistral_max_tokens_per_day", 500000)),
        mistral_max_calls_per_day=int(request.form.get("mistral_max_calls_per_day", 50)),
        mistral_max_cost_per_day=float(cost_str),
        x_max_tweets_per_day=int(request.form.get("x_max_tweets_per_day", 15)),
        x_max_replies_per_day=int(request.form.get("x_max_replies_per_day", 10)),
        warning_threshold_pct=int(request.form.get("warning_threshold_pct", 80)),
        alert_email=request.form.get("alert_email", "").strip(),
        smtp_host=request.form.get("smtp_host", "smtp.gmail.com").strip(),
        smtp_port=int(request.form.get("smtp_port", 587)),
        smtp_user=request.form.get("smtp_user", "").strip(),
        smtp_password=request.form.get("smtp_password", "").strip(),
        alerts_enabled=1 if request.form.get("alerts_enabled") else 0,
        daily_summary_enabled=1 if request.form.get("daily_summary_enabled") else 0,
        max_consecutive_errors=int(request.form.get("max_consecutive_errors", 5)),
    )

    # Reload and re-render the full page with fresh data
    status = usage_limiter.get_status()
    limits = get_usage_limits()
    ks = get_kill_switch()
    alerts = get_recent_alerts(limit=15)
    return render_template("limits.html", status=status, limits=limits, ks=ks, alerts=alerts, just_saved=True), 200, {"HX-Trigger": '{"showToast": {"message": "Configuration saved!", "type": "success"}}'}


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

    status = usage_limiter.get_status()
    limits = get_usage_limits()
    ks = get_kill_switch()
    alerts = get_recent_alerts(limit=15)
    return render_template("limits.html", status=status, limits=limits, ks=ks, alerts=alerts), 200, {"HX-Trigger": f'{{"showToast": {{"message": "{msg}", "type": "info"}}}}'}


@bp.route("/api/limits/test-email", methods=["POST"])
def test_email():
    ok = send_alert_email("Test alert", "This is a test email from Quantum Brief Bot.\n\nIf you see this, email alerts are working.")
    if ok:
        return "", 200, {"HX-Trigger": '{"showToast": {"message": "Test email sent!", "type": "success"}}'}
    else:
        return "", 200, {"HX-Trigger": '{"showToast": {"message": "Failed to send email. Check SMTP settings.", "type": "error"}}'}


@bp.route("/api/limits/status")
def api_limits_status():
    """Return usage bars HTML fragment for HTMX auto-refresh."""
    status = usage_limiter.get_status()
    bars = _render_bars(status)
    return bars


def _render_bars(s):
    """Render usage progress bars as HTML fragment."""
    def bar(label, current, max_val, pct, fmt="{}"):
        color = "var(--green)" if pct < 60 else "var(--yellow)" if pct < 85 else "var(--red)"
        return (
            f'<div class="limit-bar">'
            f'<div class="limit-label"><span>{label}</span><span>{fmt.format(current)} / {fmt.format(max_val)}</span></div>'
            f'<div class="progress-track"><div class="progress-fill" style="width:{min(pct,100):.0f}%;background:{color}"></div></div>'
            f'</div>'
        )

    html = bar("Mistral calls", s["mistral_calls"], s["mistral_calls_max"], s["mistral_calls_pct"])
    html += bar("Mistral tokens", s["mistral_tokens"], s["mistral_tokens_max"], s["mistral_tokens_pct"])
    html += bar("Mistral cost", s["mistral_cost"], s["mistral_cost_max"], s["mistral_cost_pct"], fmt="${:.4f}")
    html += bar("Tweets", s["x_tweets"], s["x_tweets_max"], s["x_tweets_pct"])
    html += bar("Replies", s["x_replies"], s["x_replies_max"], s["x_replies_pct"])
    return html
