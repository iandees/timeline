import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)

    # Default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///timeline.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    # Override with custom config if provided
    if config:
        app.config.update(config)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Import models to ensure they're known to SQLAlchemy
    from app import model

    @login_manager.user_loader
    def load_user(user_id):
        return model.User.query.get(int(user_id))

    # Register blueprints
    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app