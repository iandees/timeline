from datetime import datetime

from flask_login import UserMixin

from . import db
import json


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    events = db.relationship('Event', backref='user', lazy=True)


class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)

    user = db.relationship('User', backref=db.backref('api_keys', lazy=True))

    @staticmethod
    def generate_key():
        return secrets.token_urlsafe(32)

    def __repr__(self):
        return f'<APIKey {self.name}>'


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # e.g., 'meal', 'hygiene', 'travel', etc.
    title = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column(db.DateTime)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    location = db.relationship('Location')
    notes = db.Column(db.Text)
    attributes = db.relationship('EventAttribute', backref='event', lazy=True, cascade='all, delete-orphan')

    def add_attribute(self, key, value):
        attr = EventAttribute(key=key, value=json.dumps(value), event_id=self.id)
        db.session.add(attr)

    def get_attribute(self, key):
        attr = EventAttribute.query.filter_by(event_id=self.id, key=key).first()
        if attr:
            return json.loads(attr.value)
        return None


class EventAttribute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    key = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Text)  # Stores JSON serialized data


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    altitude = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    address = db.Column(db.String(255))
    place_name = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='locations')


class GPSPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    altitude = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    speed = db.Column(db.Float)
    bearing = db.Column(db.Float)
    provider = db.Column(db.String(50))
    source = db.Column(db.String(50))  # e.g. 'gpslogger' or 'gpx_import'

    user = db.relationship('User', backref=db.backref('gps_positions', lazy=True))

    def __repr__(self):
        return f'<GPSPosition {self.timestamp}: {self.latitude},{self.longitude}>'