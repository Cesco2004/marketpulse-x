#!/usr/bin/env python3
"""Unified entry point for cloud deployment.

Starts the dashboard, scheduler, and engagement monitor in a single process.
Usage: python run_all.py
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import init_db, get_approved_posts, get_engagement_config, get_schedule_config, get_analytics_config
from dashboard.app import create_app


def main():
    init_db()

    # Auto-start scheduler if there are approved posts and schedule is active
    sched_cfg = get_schedule_config()
    if sched_cfg.get("is_active") or get_approved_posts():
        try:
            from scheduler.scheduler import scheduler
            scheduler.start()
            print("[run_all] Scheduler started.")
        except Exception as e:
            print(f"[run_all] Scheduler failed to start: {e}")

    # Auto-start engagement monitor if enabled
    eng_cfg = get_engagement_config()
    if eng_cfg.get("is_enabled"):
        try:
            from engagement.monitor import engagement_monitor
            engagement_monitor.start()
            print("[run_all] Engagement monitor started.")
        except Exception as e:
            print(f"[run_all] Engagement monitor failed to start: {e}")

    # Auto-start metrics collector if enabled
    analytics_cfg = get_analytics_config()
    if analytics_cfg.get("is_enabled"):
        try:
            from analytics.collector import metrics_collector
            metrics_collector.start()
            print("[run_all] Metrics collector started.")
        except Exception as e:
            print(f"[run_all] Metrics collector failed to start: {e}")

    # Run Flask (blocks the main thread)
    app = create_app()
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print(f"\n  Quantum Brief (cloud mode)")
    print(f"  http://0.0.0.0:{port}\n")

    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
