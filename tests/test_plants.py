from tests.conftest import get_csrf, register_and_login


def _create_plant(client, name="Tomato #1"):
    r = client.get("/plants/create")
    c = get_csrf(r.get_data(as_text=True))
    r = client.post("/plants/create", data={"name": name, "species": "Tomato", "csrf_token": c},
                     content_type="multipart/form-data", follow_redirects=True)
    return r


def test_create_view_edit_archive_delete_plant(auth_client):
    r = _create_plant(auth_client)
    assert b"was added to your workspace" in r.data

    r = auth_client.get("/plants/1")
    assert r.status_code == 200 and b"Tomato #1" in r.data

    r = auth_client.get("/plants/1/edit")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/plants/1/edit", data={"name": "Tomato Renamed", "csrf_token": c}, follow_redirects=True)
    assert b"Tomato Renamed" in r.data

    r = auth_client.get("/plants/")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/plants/1/archive", data={"csrf_token": c}, follow_redirects=True)
    assert b"was archived" in r.data

    r = auth_client.get("/plants/?archived=1")
    assert b"Tomato Renamed" in r.data

    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/plants/1/delete", data={"csrf_token": c}, follow_redirects=True)
    assert b"were deleted" in r.data


def test_plant_ownership_is_enforced(auth_client, client):
    _create_plant(auth_client)
    register_and_login(client, email="other@example.com")

    r = client.get("/plants/1")
    assert r.status_code == 403

    r = client.get("/dashboard")
    c = get_csrf(r.get_data(as_text=True))
    r = client.post("/plants/1/delete", data={"csrf_token": c})
    assert r.status_code == 403
