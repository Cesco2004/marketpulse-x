import os
import sys

# Add project root to path so we can import config, storage, etc.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from storage.database import init_db


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "quantum-brief-local-dashboard")
    app.jinja_env.filters["split"] = lambda s, sep=",": s.split(sep)

    import json as _json
    def _from_json(s):
        try:
            return _json.loads(s) if isinstance(s, str) else s
        except (ValueError, TypeError):
            return {}
    app.jinja_env.filters["from_json"] = _from_json

    init_db()

    # Register route blueprints
    from dashboard.routes.dashboard import bp as dashboard_bp
    from dashboard.routes.articles import bp as articles_bp
    from dashboard.routes.review import bp as review_bp
    from dashboard.routes.queue import bp as queue_bp
    from dashboard.routes.history import bp as history_bp
    from dashboard.routes.actions import bp as actions_bp
    from dashboard.routes.usage import bp as usage_bp
    from dashboard.routes.sources import bp as sources_bp
    from dashboard.routes.calendar import bp as calendar_bp
    from dashboard.routes.settings import bp as settings_bp
    from dashboard.routes.engagement import bp as engagement_bp
    from dashboard.routes.limits import bp as limits_bp
    from dashboard.routes.analytics import bp as analytics_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(actions_bp)
    app.register_blueprint(usage_bp)
    app.register_blueprint(sources_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(engagement_bp)
    app.register_blueprint(limits_bp)
    app.register_blueprint(analytics_bp)

    return app
