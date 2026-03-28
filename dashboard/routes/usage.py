from flask import Blueprint, redirect

bp = Blueprint("usage", __name__)


@bp.route("/usage")
def usage_page():
    return redirect("/settings?tab=budget")
