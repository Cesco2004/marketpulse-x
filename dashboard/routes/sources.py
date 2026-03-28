from flask import Blueprint, redirect

bp = Blueprint("sources", __name__)


@bp.route("/sources")
def sources_page():
    return redirect("/markets")


@bp.route("/sources/<source_name>")
def source_detail(source_name):
    return redirect("/markets")
