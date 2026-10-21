import io
import json

import cv2
import numpy as np

from tests.conftest import get_csrf


def _synthetic_leaf_bytes():
    img = np.full((400, 400, 3), (230, 230, 230), dtype=np.uint8)
    cv2.ellipse(img, (200, 200), (150, 110), 0, 0, 360, (40, 150, 40), -1)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _create_plant(client, species=None, name="Tomato #1"):
    r = client.get("/plants/create")
    c = get_csrf(r.get_data(as_text=True))
    client.post("/plants/create", data={
        "name": name, "species": species or "", "csrf_token": c,
    },
                content_type="multipart/form-data")


def test_full_leaf_analysis_flow(auth_client):
    _create_plant(auth_client)
    r = auth_client.get("/analyze/")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": c,
        "image": (io.BytesIO(_synthetic_leaf_bytes()), "leaf.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert b"Leaf-Based Visual Score" in r.data
    assert b"VISION ASSESSMENT UNAVAILABLE" in r.data
    assert b"AI disease model not installed" not in r.data


def test_legacy_classifier_prediction_is_not_shown_in_results(auth_client, app, monkeypatch):
    _create_plant(auth_client, species="Apple")
    from app.models import Analysis
    from app.extensions import db
    r = auth_client.get("/analyze/")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": c,
        "image": (io.BytesIO(_synthetic_leaf_bytes()), "leaf.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)

    assert r.status_code == 200
    assert b"Vision-Based Plant Health Assessment" in r.data
    assert b"Secondary fixed-class disease screening" not in r.data
    assert b"MODEL-BASED SCREENING" not in r.data
    with app.app_context():
        analysis = Analysis.query.one()
        analysis.ai_prediction = "Tomato___Septoria_leaf_spot"
        analysis.ai_confidence = 63.1
        db.session.commit()
    r = auth_client.get("/analyze/1")
    assert b"Tomato___Septoria_leaf_spot" not in r.data
    assert b"63.1%" not in r.data


def test_legacy_classifier_prediction_is_not_shown_in_history_timeline_or_search(auth_client, app):
    from app.models import Analysis
    from app.extensions import db

    _create_plant(auth_client)
    page = auth_client.get("/analyze/")
    auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": get_csrf(page.get_data(as_text=True)),
        "image": (io.BytesIO(_synthetic_leaf_bytes()), "leaf.jpg"),
    }, content_type="multipart/form-data")
    with app.app_context():
        analysis = Analysis.query.one()
        analysis.ai_prediction = "Tomato___Septoria_leaf_spot"
        analysis.ai_confidence = 63.1
        db.session.commit()

    for path in ("/history/", "/timeline/", "/search/?q=Tomato"):
        response = auth_client.get(path)
        assert response.status_code == 200
        assert b"Tomato___Septoria_leaf_spot" not in response.data
        assert b"63.1%" not in response.data


def test_legacy_classifier_is_not_presented_as_an_active_ai_feature(auth_client):
    for path in ("/settings/", "/system-status/"):
        response = auth_client.get(path)
        assert response.status_code == 200
        assert b"AI Disease Model" not in response.data
        assert b"To enable AI screening" not in response.data


def test_invalid_image_shows_friendly_error(auth_client):
    _create_plant(auth_client)
    r = auth_client.get("/analyze/")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": c,
        "image": (io.BytesIO(b"garbage" * 20), "leaf.jpg"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"Could not read the uploaded image" in r.data


def test_report_generation_produces_real_pdf(auth_client):
    from app.models import Analysis
    from app.extensions import db

    _create_plant(auth_client)
    r = auth_client.get("/analyze/")
    c = get_csrf(r.get_data(as_text=True))
    auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": c,
        "image": (io.BytesIO(_synthetic_leaf_bytes()), "leaf.jpg"),
    }, content_type="multipart/form-data")
    with auth_client.application.app_context():
        analysis = Analysis.query.one()
        analysis.ai_prediction = "Tomato___Septoria_leaf_spot"
        analysis.ai_confidence = 63.1
        db.session.commit()

    r = auth_client.get("/analyze/1")
    c = get_csrf(r.get_data(as_text=True))
    r = auth_client.post("/reports/generate/1", data={"csrf_token": c}, follow_redirects=True)
    assert r.status_code == 200

    r = auth_client.get("/reports/")
    import re
    m = re.search(r"/reports/(\d+)\"", r.get_data(as_text=True))
    assert m, "expected a report link on the reports page"
    report_id = m.group(1)

    r = auth_client.get(f"/reports/{report_id}")
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"
    assert b"AI Disease Screening" not in r.data
    assert b"Tomato___Septoria_leaf_spot" not in r.data


def test_vision_is_primary_and_sent_to_care_context(auth_client, app, monkeypatch):
    from app.models import Analysis, PlantVisionAssessment
    from app.extensions import db

    _create_plant(auth_client, species="Hibiscus", name="Hibiscus")
    vision = {
        "overall_condition": "mild symptoms",
        "observed_symptoms": ["Leaves look green and intact, while white cottony clusters are visible on the Hibiscus stem."],
        "likely_causes": ["The white cottony clusters could be consistent with mealybugs; inspect closely because a photo cannot confirm the pest."],
        "image_evidence": "Green intact leaves and white cottony clusters on the stem are visible.",
        "uncertainty_notes": "The visible clusters suggest a possible pest, but the image cannot confirm its identity.",
        "identification_note": "",
        "recommended_care": ["Check soil moisture and ensure free drainage."],
        "treatment_guidance": "Inspect further before disease-specific treatment; no chemical is recommended.",
        "follow_up": "Observe the spots and take a clear close-up in several days.",
        "recommended_next_steps": ["Inspect both sides of nearby leaves and monitor for spread."],
        "non_plant_image": False,
    }
    monkeypatch.setattr("app.routes.analysis.analyze_uploaded_image", lambda *args: (vision, "gemini", None))
    page = auth_client.get("/analyze/")
    response = auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": get_csrf(page.get_data(as_text=True)),
        "image": (io.BytesIO(_synthetic_leaf_bytes()), "leaf.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    assert b"Vision-Based Plant Health Assessment" in response.data
    assert b"Recorded plant:</strong> Hibiscus" in response.data
    assert b"GEMINI VISION SCREENING" in response.data
    assert b"Identification note" not in response.data
    assert b"visually confirmed" not in response.data.lower()
    assert b"Mild symptoms" in response.data
    assert b"Leaf-Based Visual Score" in response.data
    assert b"AI-OBSERVED CONCERN" in response.data
    assert b"Possible visible pest signs" in response.data
    assert b"white cottony clusters are visible on the Hibiscus stem" in response.data
    with app.app_context():
        analysis = Analysis.query.one()
        assert analysis.health_score is not None and analysis.health_score >= 90
    assert b"Recommended care plan" in response.data
    assert b"Treatment precautions" in response.data
    assert b"Follow-up" in response.data
    assert b"MODEL-BASED SCREENING" not in response.data
    with app.app_context():
        saved_vision = PlantVisionAssessment.query.one()
        assert saved_vision.provider == "gemini"
        saved_vision.assessment_json = json.dumps({
            **vision,
            "identification_note": "The visible leaf arrangement appears inconsistent with the Hibiscus identity on record.",
        })
        db.session.commit()

    mismatch_page = auth_client.get("/analyze/1")
    assert b"Identification note" in mismatch_page.data
    assert b"inconsistent with the Hibiscus identity on record" in mismatch_page.data

    page = mismatch_page
    csrf = get_csrf(page.get_data(as_text=True))
    captured = {}
    recommendation = {
        "condition_summary": "Symptoms are uncertain.", "possible_causes": ["Several causes are possible."],
        "precautions": ["Inspect the plant."], "care_plan": ["Check soil moisture."],
        "treatment_guidance": "No chemical treatment is supported.", "follow_up": "Recheck later.",
    }
    def fake_care(context, symptoms, config):
        captured.update(context)
        return recommendation, "basic-care", "Mock fallback."
    monkeypatch.setattr("app.routes.analysis.generate_care", fake_care)
    response = auth_client.post("/analyze/1", data={
        "csrf_token": csrf, "symptoms": "brown_spots", "affected_area": "older_leaves",
        "watering": "twice weekly", "sunlight": "morning sun",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert captured["plant_name"] == "Hibiscus"
    assert captured["vision_assessment"]["observed_symptoms"] == vision["observed_symptoms"]
    assert "Hibiscus" in captured["plant_name"]


def test_no_foliage_image_still_reaches_vision_and_has_no_false_score(auth_client, app, monkeypatch):
    from app.models import Analysis, PlantVisionAssessment

    _create_plant(auth_client, species="Unknown plant")
    non_plant = {
        "overall_condition": "inconclusive",
        "observed_symptoms": [], "likely_causes": [],
        "image_evidence": "No plant is clearly visible in this image.",
        "uncertainty_notes": "A clear plant photo is required for identification.",
        "identification_note": "",
        "recommended_care": [],
        "treatment_guidance": "No plant treatment can be recommended from this image.",
        "follow_up": "Upload a clear close-up of the plant or affected leaf.",
        "recommended_next_steps": ["Upload a clear photo showing the plant or affected leaf."],
        "non_plant_image": True,
    }
    monkeypatch.setattr("app.routes.analysis.analyze_uploaded_image", lambda *args: (non_plant, "gemini", None))
    page = auth_client.get("/analyze/")
    white = np.full((180, 180, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", white)
    assert ok
    response = auth_client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": get_csrf(page.get_data(as_text=True)),
        "image": (io.BytesIO(encoded.tobytes()), "white.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    assert b"does not show a clearly identifiable plant" in response.data
    assert b"OpenCV could not segment foliage" in response.data
    with app.app_context():
        analysis = Analysis.query.one()
        assert analysis.health_score is None and analysis.leaf_coverage is None
        assert PlantVisionAssessment.query.one().provider == "gemini"
