"""WSGI entry point for gunicorn (production).

Starts background services (scheduler, engagement, metrics) then exposes the Flask app.
For local development, use run_all.py instead.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import (
    init_db,
    get_approved_posts,
    get_engagement_config,
    get_schedule_config,
    get_analytics_config,
)

init_db()

# Start background threads (same logic as run_all.py)
sched_cfg = get_schedule_config()
if sched_cfg.get("is_active") or get_approved_posts():
    try:
        from scheduler.scheduler import scheduler
        scheduler.start()
        print("[wsgi] Scheduler started.")
    except Exception as e:
        print(f"[wsgi] Scheduler failed to start: {e}")

eng_cfg = get_engagement_config()
if eng_cfg.get("is_enabled"):
    try:
        from engagement.monitor import engagement_monitor
        engagement_monitor.start()
        print("[wsgi] Engagement monitor started.")
    except Exception as e:
        print(f"[wsgi] Engagement monitor failed to start: {e}")

analytics_cfg = get_analytics_config()
if analytics_cfg.get("is_enabled"):
    try:
        from analytics.collector import metrics_collector
        metrics_collector.start()
        print("[wsgi] Metrics collector started.")
    except Exception as e:
        print(f"[wsgi] Metrics collector failed to start: {e}")

from dashboard.app import create_app

app = create_app()
