import pytest

from app import create_app, db
from app.models import User


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


@pytest.fixture
def user():
    user = User(username="testuser")
    user.set_password("testpassword")
    db.session.add(user)
    db.session.commit()
    return user


def test_login(client, user):
    response = client.post(
        "/auth/login", data={"username": "testuser", "password": "testpassword"}
    )
    assert response.status_code == 302  # Redirect to main page
    assert b"Invalid username or password" not in response.data


def test_register(client):
    response = client.post(
        "/auth/register", data={"username": "newuser", "password": "newpassword"}
    )
    assert response.status_code == 302  # Redirect to main page
    assert User.query.filter_by(username="newuser").first() is not None
    assert b"Username already exists" not in response.data


def test_logout(client, user):
    client.post(
        "/auth/login", data={"username": "testuser", "password": "testpassword"}
    )
    response = client.get("/auth/logout")
    assert response.status_code == 302  # Redirect to main page
