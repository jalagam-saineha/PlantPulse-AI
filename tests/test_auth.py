import re

from tests.conftest import get_csrf, register_and_login


def test_register_login_logout(client):
    register_and_login(client)
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert b"Understand your plants" in r.data

    r = client.get("/logout", follow_redirects=True)
    assert b"Welcome back" in r.data  # back at login page


def test_dashboard_requires_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_csrf_protection_blocks_missing_token(client):
    r = client.post("/login", data={"email": "x@example.com", "password": "whatever"})
    assert r.status_code == 400


def test_duplicate_email_rejected(client):
    register_and_login(client, email="dup@example.com")
    client.get("/logout", follow_redirects=True)
    r = client.get("/register")
    c = get_csrf(r.get_data(as_text=True))
    r = client.post("/register", data={
        "name": "Other", "email": "dup@example.com", "password": "password123",
        "confirm_password": "password123", "csrf_token": c,
    })
    assert r.status_code == 400
    assert b"already exists" in r.data


def test_password_reset_dev_mode_flow(client):
    register_and_login(client, email="reset@example.com")
    client.get("/logout", follow_redirects=True)

    r = client.get("/forgot-password")
    c = get_csrf(r.get_data(as_text=True))
    r = client.post("/forgot-password", data={"email": "reset@example.com", "csrf_token": c})
    html = r.get_data(as_text=True)
    assert "DEVELOPMENT MODE" in html
    m = re.search(r"/reset-password/([A-Za-z0-9_\-]+)", html)
    assert m, "reset link should be shown on screen in development mode"
    token = m.group(1)

    r = client.get(f"/reset-password/{token}")
    c = get_csrf(r.get_data(as_text=True))
    r = client.post(f"/reset-password/{token}", data={
        "password": "brandnewpassword1", "confirm_password": "brandnewpassword1", "csrf_token": c,
    }, follow_redirects=True)
    assert b"Welcome back" in r.data

    # token is single-use
    r = client.get(f"/reset-password/{token}", follow_redirects=True)
    assert b"invalid or has expired" in r.data

    # new password actually works
    r = client.get("/login")
    c = get_csrf(r.get_data(as_text=True))
    r = client.post("/login", data={
        "email": "reset@example.com", "password": "brandnewpassword1", "csrf_token": c,
    }, follow_redirects=True)
    assert b"Understand your plants" in r.data
