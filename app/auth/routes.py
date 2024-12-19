from flask import render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user

from app import db
from app.auth import bp
from app.models import User


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.get_by_username(username)  # Replace with actual user lookup
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("main.index"))
        else:
            flash("Invalid username or password")
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if User.get_by_username(username):
            flash("Username already exists")
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("main.index"))

    return render_template("auth/register.html")
