from flask import Blueprint, redirect

bp = Blueprint("articles", __name__)


@bp.route("/articles")
def articles_page():
    return redirect("/sources")
