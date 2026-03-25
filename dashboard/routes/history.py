from flask import Blueprint, render_template
from storage.database import get_posted_posts

bp = Blueprint("history", __name__)


@bp.route("/history")
def history_page():
    posts = get_posted_posts()
    return render_template("history.html", posts=posts)
