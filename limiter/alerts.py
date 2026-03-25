import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from storage.database import get_usage_limits, log_alert


def _get_smtp_config():
    limits = get_usage_limits()
    return {
        "host": limits.get("smtp_host", "smtp.gmail.com"),
        "port": int(limits.get("smtp_port", 587)),
        "user": limits.get("smtp_user", ""),
        "password": limits.get("smtp_password", ""),
        "to": limits.get("alert_email", ""),
        "enabled": bool(limits.get("alerts_enabled")),
    }


def send_alert_email(subject, body):
    """Send an email via SMTP. Returns True on success."""
    cfg = _get_smtp_config()
    if not cfg["enabled"] or not cfg["to"] or not cfg["user"] or not cfg["password"]:
        return False

    msg = MIMEMultipart()
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    msg["Subject"] = f"[Quantum Brief] {subject}"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[Alerts] Failed to send email: {e}")
        return False


def send_usage_warning(service, current_pct, details):
    subject = f"Usage warning: {service} at {current_pct:.0f}%"
    body = (
        f"Quantum Brief usage alert\n\n"
        f"Service: {service}\n"
        f"Current usage: {current_pct:.0f}% of daily limit\n\n"
        f"Details:\n{details}\n\n"
        f"The bot will stop making {service} API calls when 100% is reached."
    )
    if send_alert_email(subject, body):
        log_alert(f"warning_{service}", f"{current_pct:.0f}% - {details}")


def send_limit_reached(service, details):
    subject = f"LIMIT REACHED: {service} - bot paused"
    body = (
        f"Quantum Brief has reached its daily limit for {service}.\n\n"
        f"Details:\n{details}\n\n"
        f"All {service} API calls are now blocked until midnight UTC.\n"
        f"You can increase limits from the dashboard or via the database."
    )
    if send_alert_email(subject, body):
        log_alert(f"limit_{service}", details)


def send_error_alert(service, error_count, last_error):
    subject = f"Repeated errors: {service} ({error_count} consecutive)"
    body = (
        f"Quantum Brief has encountered {error_count} consecutive errors.\n\n"
        f"Service: {service}\n"
        f"Last error: {last_error}\n\n"
        f"Check the logs or dashboard for more details."
    )
    if send_alert_email(subject, body):
        log_alert(f"errors_{service}", f"{error_count} errors - {last_error}")


def send_daily_summary():
    from storage.database import get_daily_usage, get_daily_tweet_count, get_daily_reply_count

    mistral = get_daily_usage("mistral")
    tweet_count = get_daily_tweet_count()
    reply_count = get_daily_reply_count()

    subject = "Daily usage summary"
    body = (
        f"Quantum Brief - Daily Summary\n\n"
        f"Mistral API:\n"
        f"  Calls: {mistral.get('calls', 0)}\n"
        f"  Tokens: {mistral.get('total_tokens', 0)}\n"
        f"  Cost: ${mistral.get('total_cost', 0):.4f}\n\n"
        f"Twitter/X:\n"
        f"  Tweets posted: {tweet_count}\n"
        f"  Replies posted: {reply_count}\n"
    )
    if send_alert_email(subject, body):
        log_alert("daily_summary", f"Mistral: {mistral.get('calls', 0)} calls, X: {tweet_count} tweets + {reply_count} replies")
