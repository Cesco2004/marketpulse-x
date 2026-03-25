"""Authentication routes (login / logout)."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user

from dashboard.auth import User, check_credentials

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if check_credentials(username, password):
            login_user(User(username), remember=True)
            next_page = request.args.get("next", "/")
            return redirect(next_page)
        return render_template("login.html", error="Identifiants incorrects")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
