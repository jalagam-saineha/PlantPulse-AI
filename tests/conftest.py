import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from app import create_app


def _test_config(tmp_path):
    class TestConfig(Config):
        APP_ENV = "development"
        SECRET_KEY = "test-secret-key"
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        INSTANCE_DIR = tmp_path / "instance"
        UPLOAD_IMAGES_DIR = tmp_path / "uploads" / "images"
        UPLOAD_VIDEOS_DIR = tmp_path / "uploads" / "videos"
        UPLOAD_PLANTS_DIR = tmp_path / "uploads" / "plants"
        RESULTS_PROCESSED_DIR = tmp_path / "results" / "processed"
        RESULTS_FRAMES_DIR = tmp_path / "results" / "frames"
        REPORTS_DIR = tmp_path / "reports"
        MODELS_DIR = tmp_path / "models"
        DATA_DIR = tmp_path / "data"
        # Route tests must never inherit a developer's real .env credentials.
        CARE_AI_PROVIDER = "gemini"
        CARE_AI_API_KEY = ""
        CARE_AI_GEMINI_API_KEY = ""

    return TestConfig


@pytest.fixture()
def app(tmp_path):
    application = create_app(_test_config(tmp_path))
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def get_csrf(html: str):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else None


def register_and_login(client, email="tester@example.com", password="password123", name="Tester"):
    client.get("/logout", follow_redirects=True)  # ensure a clean session before switching identity
    r = client.get("/register")
    c = get_csrf(r.get_data(as_text=True))
    client.post("/register", data={
        "name": name, "email": email, "password": password,
        "confirm_password": password, "csrf_token": c,
    })
    r = client.get("/login")
    c = get_csrf(r.get_data(as_text=True))
    client.post("/login", data={"email": email, "password": password, "csrf_token": c})
    return client


@pytest.fixture()
def auth_client(client):
    return register_and_login(client)
