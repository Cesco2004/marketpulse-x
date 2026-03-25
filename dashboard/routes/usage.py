from flask import Blueprint, render_template
from storage.database import get_api_usage_summary

bp = Blueprint("usage", __name__)


@bp.route("/usage")
def usage_page():
    usage = get_api_usage_summary()
    return render_template("usage.html", usage=usage)
