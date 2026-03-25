"""Gunicorn configuration for Quantum Brief dashboard."""

bind = "0.0.0.0:5001"
workers = 1        # Must be 1 — background threads (scheduler, engagement, metrics) are singletons
threads = 4        # Concurrent dashboard requests
timeout = 120      # Fetch pipeline can be slow
accesslog = "-"    # stdout → journald
errorlog = "-"
