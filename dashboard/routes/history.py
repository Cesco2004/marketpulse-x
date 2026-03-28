from flask import Blueprint, redirect

bp = Blueprint("history", __name__)


@bp.route("/history")
def history_page():
    return redirect("/pipeline")
