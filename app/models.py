from flask_login import UserMixin

from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password = db.Column(db.String(128), unique=False, nullable=False)

    @staticmethod
    def get(user_id: int):
        return User.query.get(user_id)

    @staticmethod
    def get_by_username(username: str):
        return User.query.filter_by(username=username).first()
