import os
from datetime import timedelta

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=31)
    # Map API key
    PROTOMAPS_API_KEY = os.environ.get('PROTOMAPS_API_KEY')
    # Other common configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///dev.db'


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    # Enforce HTTPS
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    # Other security settings
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}