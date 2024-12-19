from flask import render_template, redirect, url_for, request, flash
from flask_login import login_user

from app.auth import bp
from app.models import User


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.get_by_username(username)  # Replace with actual user lookup
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password')
    return render_template('auth/login.html')
