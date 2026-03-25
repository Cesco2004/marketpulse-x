"""Flask-Login authentication setup for the dashboard."""

import hmac
import os

from flask_login import LoginManager, UserMixin

login_manager = LoginManager()
login_manager.login_view = "auth.login"


class User(UserMixin):
    """Single admin user for dashboard access."""

    def __init__(self, user_id):
        self.id = user_id


@login_manager.user_loader
def load_user(user_id):
    if user_id == os.environ.get("DASHBOARD_USER", "admin"):
        return User(user_id)
    return None


def check_credentials(username, password):
    """Validate credentials against environment variables (constant-time comparison)."""
    expected_user = os.environ.get("DASHBOARD_USER", "admin")
    expected_pass = os.environ.get("DASHBOARD_PASSWORD", "")
    if not expected_pass:
        return False
    user_ok = hmac.compare_digest(username, expected_user)
    pass_ok = hmac.compare_digest(password, expected_pass)
    return user_ok and pass_ok
