import os
from app.config import config
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_name='default'):
    app = Flask(__name__)

    # Default configuration
    app.config.from_object(config[config_name])

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