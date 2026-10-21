import base64
import io
import json
import urllib.error

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.plant_vision import analyze_uploaded_image


def _image_file(tmp_path):
    image = np.full((120, 140, 3), (230, 230, 230), dtype=np.uint8)
    cv2.ellipse(image, (70, 60), (48, 34), 0, 0, 360, (40, 150, 40), -1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    path = tmp_path / "plant.jpg"
    path.write_bytes(encoded.tobytes())
    return path


def _assessment(**overrides):
    result = {
        "overall_condition": "mild symptoms",
        "observed_symptoms": ["Some lower leaf yellowing is visible."],
        "likely_causes": ["Water stress is one possibility; check soil moisture."],
        "image_evidence": "A green plant with several yellow lower leaves is visible.",
        "uncertainty_notes": "The image alone cannot establish the cause or confirm disease.",
        "identification_note": "",
        "recommended_care": ["Check soil moisture before watering and ensure good drainage."],
        "treatment_guidance": "Inspect the plant further before considering disease-specific treatment.",
        "follow_up": "Observe the affected leaves and take another close-up in five days.",
        "recommended_next_steps": ["Check soil moisture before changing watering."],
        "non_plant_image": False,
    }
    result.update(overrides)
    return result


class _Response:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode("utf-8")


def _provider_payload(value):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(value)}]}}]}


def _config():
    return {"CARE_AI_GEMINI_API_KEY": "test-only-key-never-real", "CARE_AI_GEMINI_MODEL": "gemini-3.5-flash-lite", "CARE_AI_TIMEOUT": 4}


def test_gemini_image_success_sends_actual_image_and_returns_validated_result(monkeypatch, tmp_path):
    from app.services import plant_vision
    result = _assessment()
    def open_request(request, timeout):
        assert request.full_url.endswith("/v1beta/models/gemini-3.5-flash-lite:generateContent")
        assert request.get_header("X-goog-api-key") == _config()["CARE_AI_GEMINI_API_KEY"]
        assert timeout == 4
        body = json.loads(request.data)
        parts = body["contents"][0]["parts"]
        prompt = json.loads(parts[0]["text"])
        assert prompt["recorded_plant"]["name"] == "Hibiscus"
        assert "Do not unnecessarily identify or re-identify the plant" in prompt["task"]
        assert "spots" in prompt["task"] and "affected areas" in prompt["task"]
        assert "image itself" in parts[0]["text"]
        image_bytes = base64.b64decode(parts[1]["inline_data"]["data"])
        with Image.open(io.BytesIO(image_bytes)) as sent_image:
            assert sent_image.format == "JPEG" and max(sent_image.size) <= 1536
        response_format = body["generationConfig"]["responseFormat"]["text"]
        assert response_format["mimeType"] == "APPLICATION_JSON"
        assert response_format["schema"]["type"] == "object"
        assert response_format["schema"]["properties"]["observed_symptoms"]["type"] == "array"
        assert "responseSchema" not in body["generationConfig"]
        assert "additionalProperties" not in response_format["schema"]
        return _Response(_provider_payload(result))
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", open_request)
    assessment, provider, reason = analyze_uploaded_image(_image_file(tmp_path), {"plant_name": "Hibiscus", "recorded_species": "Hibiscus rosa-sinensis", "measurements": {"yellowing": 12}}, _config())
    assert provider == "gemini" and reason is None and assessment == result


@pytest.mark.parametrize("result", [
    _assessment(identification_note=""),
    _assessment(identification_note="The visible leaf shape appears inconsistent with the recorded Hibiscus identity."),
    _assessment(non_plant_image=True,
                observed_symptoms=["yellow spots"], likely_causes=["fungus"]),
])
def test_identity_note_is_optional_and_non_plant_results_are_safe(monkeypatch, tmp_path, result):
    from app.services import plant_vision
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: _Response(_provider_payload(result)))
    assessment, provider, reason = analyze_uploaded_image(_image_file(tmp_path), {"recorded_species": "Unknown plant"}, _config())
    assert provider == "gemini" and reason is None
    if result["non_plant_image"]:
        assert assessment["observed_symptoms"] == assessment["likely_causes"] == []
    else:
        assert assessment["identification_note"] == result["identification_note"]


def test_inconclusive_assessment_does_not_keep_disease_candidates(monkeypatch, tmp_path):
    from app.services import plant_vision
    poor_quality = _assessment(
        overall_condition="inconclusive", likely_causes=["Possible fungal disease."],
        uncertainty_notes="The image is blurry and too distant to inspect leaf details.",
    )
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: _Response(_provider_payload(poor_quality)))
    assessment, provider, reason = analyze_uploaded_image(_image_file(tmp_path), {}, _config())
    assert provider == "gemini" and reason is None
    assert assessment["overall_condition"] == "inconclusive"
    assert assessment["likely_causes"] == []

@pytest.mark.parametrize(("status", "reason_text"), [
    (400, "HTTP 400"), (401, "authentication failed"), (429, "quota or rate limit"),
])
def test_http_errors_fall_back_without_logging_credentials(monkeypatch, tmp_path, caplog, status, reason_text):
    from app.services import plant_vision
    secret = _config()["CARE_AI_GEMINI_API_KEY"]
    body = json.dumps({"error": {"code": status, "status": "RESOURCE_EXHAUSTED", "message": secret}}).encode()
    error = urllib.error.HTTPError("https://generativelanguage.googleapis.com/test", status, "provider error", None, io.BytesIO(body))
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(error))
    _, provider, reason = analyze_uploaded_image(_image_file(tmp_path), {"recorded_species": "Tomato"}, _config())
    assert provider == "unavailable" and reason_text in reason
    assert secret not in caplog.text and "Authorization" not in caplog.text


def test_timeout_connection_malformed_json_and_invalid_assessment_fall_back(monkeypatch, tmp_path):
    from app.services import plant_vision
    path = _image_file(tmp_path)
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()))
    _, provider, reason = analyze_uploaded_image(path, {}, _config())
    assert provider == "unavailable" and "timed out" in reason
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    _, provider, reason = analyze_uploaded_image(path, {}, _config())
    assert provider == "unavailable" and "Could not connect" in reason

    class InvalidJSON(_Response):
        def read(self): return b"not json"
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: InvalidJSON(None))
    _, provider, reason = analyze_uploaded_image(path, {}, _config())
    assert provider == "unavailable" and "malformed JSON" in reason
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: _Response(_provider_payload(_assessment(overall_condition="uncalibrated probability 99%"))))
    _, provider, reason = analyze_uploaded_image(path, {}, _config())
    assert provider == "unavailable" and "incomplete or unsafe" in reason
    unsafe = _assessment(likely_causes=["The plant is definitely infected with a fungus."])
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: _Response(_provider_payload(unsafe)))
    _, provider, reason = analyze_uploaded_image(path, {}, _config())
    assert provider == "unavailable" and "incomplete or unsafe" in reason
    chemical = _assessment(recommended_next_steps=["Spray fungicide on all leaves."])
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: _Response(_provider_payload(chemical)))
    _, provider, reason = analyze_uploaded_image(path, {}, _config())
    assert provider == "unavailable" and "incomplete or unsafe" in reason


def test_missing_key_corrupt_and_oversized_images_do_not_call_provider(monkeypatch, tmp_path):
    from app.services import plant_vision
    monkeypatch.setattr(plant_vision.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network must not be called"))
    _, provider, reason = analyze_uploaded_image(_image_file(tmp_path), {}, {"CARE_AI_GEMINI_MODEL": "gemini-test"})
    assert provider == "unavailable" and "not configured" in reason
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not an image")
    _, provider, reason = analyze_uploaded_image(corrupt, {}, _config())
    assert provider == "unavailable" and "could not be prepared" in reason
    oversized = tmp_path / "large.jpg"
    with oversized.open("wb") as target:
        target.truncate(20 * 1024 * 1024 + 1)
    _, provider, reason = analyze_uploaded_image(oversized, {}, _config())
    assert provider == "unavailable" and "size limit" in reason
