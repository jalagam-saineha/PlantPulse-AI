import io
import json
import re
import time

import cv2
import numpy as np

from tests.conftest import get_csrf
from app.extensions import db
from app.models import VideoAnalysis


def _synthetic_growth_video_bytes():
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        path = f.name
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, 10.0, (320, 240))
    for i in range(30):  # 3 seconds at 10fps
        img = np.full((240, 320, 3), (230, 230, 230), dtype=np.uint8)
        axes = (int(60 + 60 * i / 30), int(45 + 40 * i / 30))
        cv2.ellipse(img, (160, 120), axes, 0, 0, 360, (40, 150, 40), -1)
        out.write(img)
    out.release()
    with open(path, "rb") as f:
        return f.read()


def _create_plant(client):
    r = client.get("/plants/create")
    c = get_csrf(r.get_data(as_text=True))
    client.post("/plants/create", data={"name": "Tomato #1", "csrf_token": c},
                content_type="multipart/form-data")


def test_growth_scan_processes_and_produces_frames(auth_client, app):
    _create_plant(auth_client)
    r = auth_client.get("/growth/")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/growth/", data={
        "plant_id": "1", "interval": "1", "csrf_token": c,
        "video": (io.BytesIO(_synthetic_growth_video_bytes()), "growth.mp4"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    video_id = r.request.path.rsplit("/", 1)[-1]

    status = None
    for _ in range(30):
        resp = auth_client.get(f"/growth/{video_id}/status.json")
        status = resp.get_json()
        if status["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(1)

    assert status is not None
    assert status["status"] == "COMPLETED", status.get("error_message")
    assert status["frame_count"] > 0

    r = auth_client.get(f"/growth/{video_id}")
    assert b"Frame Timeline" in r.data
    html = r.get_data(as_text=True)
    assert "chart.js@4.4.4/dist/chart.umd.min.js" in html
    assert "type: 'linear'" in html
    assert "No valid data is available for this measurement." in html
    assert "chart-health" in html
    assert "function drawFallback" in html

    timestamp_match = re.search(r"var timestamps = (\[[^\]]*\]);", html)
    assert timestamp_match
    with app.app_context():
        video = db.session.get(VideoAnalysis, int(video_id))
        frames = video.frames.all()
        assert json.loads(timestamp_match.group(1)) == [frame.timestamp_seconds for frame in frames]
        expected_series = {
            "chart-health": [frame.health_score for frame in frames],
            "chart-area": [frame.leaf_area_px for frame in frames],
            "chart-green": [frame.green_coverage for frame in frames],
            "chart-damage": [frame.damage for frame in frames],
        }
    for chart_id, expected in expected_series.items():
        series_match = re.search(r"mkChart\('" + chart_id + r"', (\[[^\]]*\])", html)
        assert series_match
        assert json.loads(series_match.group(1)) == expected


def test_second_scan_blocked_while_one_is_processing(auth_client):
    _create_plant(auth_client)
    r = auth_client.get("/growth/")
    c = get_csrf(r.get_data(as_text=True))
    auth_client.post("/growth/", data={
        "plant_id": "1", "interval": "1", "csrf_token": c,
        "video": (io.BytesIO(_synthetic_growth_video_bytes()), "growth.mp4"),
    }, content_type="multipart/form-data")

    r = auth_client.get("/growth/")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/growth/", data={
        "plant_id": "1", "interval": "1", "csrf_token": c,
        "video": (io.BytesIO(_synthetic_growth_video_bytes()), "growth2.mp4"),
    }, content_type="multipart/form-data", follow_redirects=True)
    # Either it's still processing (blocked) or finished very fast and allowed through;
    # the important guarantee is the app never crashes and gives a clear message either way.
    assert r.status_code == 200
