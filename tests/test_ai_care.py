import io
import json
import urllib.error

import cv2
import numpy as np
import pytest
from werkzeug.datastructures import MultiDict

from app.models import Analysis, CareRecommendation
from app.services.care_assistant import generate, validate_form
from config import care_ai_settings
from tests.conftest import get_csrf


def _image_bytes():
    image = np.full((240, 240, 3), (230, 230, 230), dtype=np.uint8)
    cv2.ellipse(image, (120, 120), (90, 65), 0, 0, 360, (40, 150, 40), -1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def _analysis(client, species="Tomato"):
    page = client.get("/plants/create")
    client.post("/plants/create", data={"name": "Garden tomato", "species": species,
                                        "csrf_token": get_csrf(page.get_data(as_text=True))},
                content_type="multipart/form-data")
    page = client.get("/analyze/")
    response = client.post("/analyze/", data={
        "plant_id": "1", "csrf_token": get_csrf(page.get_data(as_text=True)),
        "image": (io.BytesIO(_image_bytes()), "leaf.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200


def test_care_input_validation_and_symptom_recommendations():
    with pytest.raises(ValueError):
        validate_form(MultiDict())
    with pytest.raises(ValueError):
        validate_form(MultiDict([("notes", "x" * 1001)]))
    submitted = validate_form(MultiDict([("symptoms", "yellowing"), ("affected_area", "older_leaves"),
                                          ("notes", "Dry soil observed.\x00")]))
    assert submitted["symptoms"] == ["yellowing"]
    assert submitted["notes"] == "Dry soil observed."
    result = generate({"plant_name": "Tomato", "species": "Tomato", "yellowing": 4.2}, submitted, {})
    assert result[1] == "basic-care"
    assert "Missing API configuration" in result[2]
    assert any("Water stress" in cause for cause in result[0]["possible_causes"])
    assert "Tomato" in result[0]["condition_summary"]
    for section in ("possible_causes", "precautions", "care_plan"):
        assert "Tomato" in result[0][section][0]
    assert set(result[0]) == {"condition_summary", "possible_causes", "precautions", "care_plan", "treatment_guidance", "follow_up"}


def test_provider_timeout_and_invalid_response_fall_back(monkeypatch):
    import app.services.care_assistant as service
    config = {"CARE_AI_API_KEY": "configured-for-test", "CARE_AI_API_URL": "https://example.invalid", "CARE_AI_MODEL": "test-model", "CARE_AI_TIMEOUT": 0.01}
    context, symptoms = {}, {"symptoms": ["wilting"]}

    def timeout(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr(service.urllib.request, "urlopen", timeout)
    result, provider, error = generate(context, symptoms, config)
    assert provider == "basic-care" and error and result["care_plan"]

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"not-json"
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: Response())
    result, provider, error = generate(context, symptoms, config)
    assert provider == "basic-care" and "Invalid AI response" in error


def test_provider_environment_mapping():
    mapped = care_ai_settings({
        "PLANTPULSE_AI_PROVIDER": "gemini",
        "PLANTPULSE_AI_API_KEY": "secret-test-value",
        "PLANTPULSE_AI_API_URL": "https://test.invalid/chat/completions",
        "PLANTPULSE_AI_MODEL": "test-model",
        "PLANTPULSE_GEMINI_API_KEY": "gemini-secret-test-value",
        "PLANTPULSE_GEMINI_MODEL": "gemini-test-model",
        "PLANTPULSE_AI_TIMEOUT": "7.5",
    })
    assert mapped == {
        "CARE_AI_PROVIDER": "gemini",
        "CARE_AI_API_KEY": "secret-test-value",
        "CARE_AI_API_URL": "https://test.invalid/chat/completions",
        "CARE_AI_MODEL": "test-model",
        "CARE_AI_GEMINI_API_KEY": "gemini-secret-test-value",
        "CARE_AI_GEMINI_MODEL": "gemini-test-model",
        "CARE_AI_TIMEOUT": 7.5,
    }


def test_gemini_generate_content_success_uses_header_and_schema(monkeypatch):
    import app.services.care_assistant as service
    recommendation = {
        "condition_summary": "Reported yellowing is a symptom and does not establish a diagnosis.",
        "possible_causes": ["Water stress is possible; check soil moisture."],
        "precautions": ["Keep drainage clear."],
        "care_plan": ["Check soil moisture and record changes."],
        "treatment_guidance": "No specific treatment is supported by current evidence.",
        "follow_up": "Reassess in several days and upload a new image if symptoms spread.",
    }
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(recommendation)}]}}]}).encode()
    context = {"plant_name": "Hibiscus", "species": "Hibiscus rosa-sinensis"}
    def open_request(request, timeout):
        assert request.full_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
        assert request.get_header("X-goog-api-key") == "gemini-test-key"
        assert "key=" not in request.full_url
        body = json.loads(request.data)
        assert body["contents"][0]["role"] == "user"
        sent_prompt = body["contents"][0]["parts"][0]["text"]
        assert "Hibiscus" in sent_prompt and "Do not re-identify the plant" in sent_prompt
        response_format = body["generationConfig"]["responseFormat"]["text"]
        assert response_format["mimeType"] == "APPLICATION_JSON"
        assert response_format["schema"]["required"] == [
            "condition_summary", "possible_causes", "precautions", "care_plan", "treatment_guidance", "follow_up"
        ]
        assert "additionalProperties" not in response_format["schema"]
        assert response_format["schema"]["properties"]["possible_causes"]["type"] == "array"
        assert "responseSchema" not in body["generationConfig"]
        return Response()
    monkeypatch.setattr(service.urllib.request, "urlopen", open_request)
    result, provider, reason = generate(context, {"symptoms": ["yellowing"]}, {
        "CARE_AI_PROVIDER": "gemini", "CARE_AI_GEMINI_API_KEY": "gemini-test-key",
        "CARE_AI_GEMINI_MODEL": "gemini-3.5-flash-lite", "CARE_AI_TIMEOUT": 9,
    })
    assert provider == "configured-ai" and reason is None
    assert result["condition_summary"].startswith("Hibiscus:")
    for section in ("possible_causes", "precautions", "care_plan"):
        assert "Hibiscus" in result[section][0]
    assert "or similar broadleaf plant" not in str(result)


@pytest.mark.parametrize(("status", "expected"), [
    (401, "Gemini authentication failed"),
    (429, "Gemini quota or rate limit"),
    (400, "Gemini request failed"),
])
def test_gemini_http_failures_keep_key_out_of_logs(monkeypatch, caplog, status, expected):
    import app.services.care_assistant as service
    secret = "gemini-secret-do-not-log"
    config = {"CARE_AI_PROVIDER": "gemini", "CARE_AI_GEMINI_API_KEY": secret, "CARE_AI_GEMINI_MODEL": "gemini-test"}
    body = json.dumps({"error": {"code": status, "status": "INVALID_ARGUMENT", "message": "bad request"}}).encode()
    error = urllib.error.HTTPError("https://generativelanguage.googleapis.com/test", status, "error", None, io.BytesIO(body))
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(error))
    result, provider, reason = generate({}, {"symptoms": ["yellowing"]}, config)
    assert provider == "basic-care" and expected in reason
    assert secret not in caplog.text and "Authorization" not in caplog.text
    assert f"HTTP {status}" in caplog.text


def test_gemini_timeout_invalid_json_and_missing_key_use_fallback(monkeypatch, caplog):
    import app.services.care_assistant as service
    config = {"CARE_AI_PROVIDER": "gemini", "CARE_AI_GEMINI_API_KEY": "test-key", "CARE_AI_GEMINI_MODEL": "gemini-test"}
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()))
    _, provider, reason = generate({}, {"symptoms": []}, config)
    assert provider == "basic-care" and "timed out" in reason
    assert "timeout" in caplog.text

    class InvalidResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"not-json"
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: InvalidResponse())
    _, provider, reason = generate({}, {"symptoms": []}, config)
    assert provider == "basic-care" and "invalid response JSON" in reason

    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    _, provider, reason = generate({}, {"symptoms": []}, config)
    assert provider == "basic-care" and "Could not connect to Gemini" in reason
    assert "connection failure" in caplog.text

    _, provider, reason = generate({}, {"symptoms": []}, {"CARE_AI_PROVIDER": "gemini"})
    assert provider == "basic-care" and "key or model is missing" in reason


def test_successful_provider_response_uses_configured_ai_and_auth_header(monkeypatch):
    import app.services.care_assistant as service
    recommendation = {
        "condition_summary": "Reported yellowing is a symptom and does not establish a diagnosis.",
        "possible_causes": ["Water stress is possible; check soil moisture."],
        "precautions": ["Keep drainage clear."],
        "care_plan": ["Check soil moisture and record changes."],
        "treatment_guidance": "No specific treatment is supported by current evidence.",
        "follow_up": "Reassess in several days and upload a new image if symptoms spread.",
    }
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": json.dumps(recommendation)}}]}).encode()
    def open_request(request, timeout):
        assert request.full_url == "https://example.invalid/v1/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-key"
        assert timeout == 5
        sent = json.loads(request.data)
        assert sent["model"] == "gpt-test"
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["messages"][0]["role"] == "user"
        return Response()
    monkeypatch.setattr(service.urllib.request, "urlopen", open_request)
    result, provider, reason = generate({}, {"symptoms": ["yellowing"]}, {
        "CARE_AI_API_KEY": "test-key", "CARE_AI_API_URL": "https://example.invalid/v1/chat/completions",
        "CARE_AI_MODEL": "gpt-test", "CARE_AI_TIMEOUT": 5,
    })
    assert provider == "configured-ai" and reason is None
    assert result == recommendation


@pytest.mark.parametrize(("status", "error_code", "expected"), [
    (400, "bad_request", "Provider request failure"),
    (401, "invalid_api_key", "Provider authentication failure"),
    (429, "rate_limit_exceeded", "rate limit reached"),
    (429, "credit_balance_exhausted", "quota is exhausted"),
])
def test_http_provider_failures_are_specific_and_secret_safe(monkeypatch, caplog, status, error_code, expected):
    import app.services.care_assistant as service
    secret = "never-log-this-api-key"
    config = {"CARE_AI_API_KEY": secret, "CARE_AI_API_URL": "https://example.invalid", "CARE_AI_MODEL": "test-model"}
    error_type = "insufficient_quota" if error_code == "credit_balance_exhausted" else "invalid_request_error"
    body = json.dumps({"error": {"type": error_type, "code": error_code, "message": f"bad input {secret} yellowing"}}).encode()
    error = urllib.error.HTTPError(config["CARE_AI_API_URL"], status, "provider error", None, io.BytesIO(body))
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(error))
    result, provider, reason = generate({}, {"symptoms": ["yellowing"]}, config)
    assert provider == "basic-care" and expected in reason
    assert secret not in caplog.text and secret not in reason and "yellowing" not in caplog.text
    assert f"HTTP {status}" in caplog.text
    assert error_type in caplog.text and error_code in caplog.text
    assert "bad input" in caplog.text


def test_connection_failure_and_missing_response_fields_fall_back(monkeypatch, caplog):
    import app.services.care_assistant as service
    config = {"CARE_AI_API_KEY": "test-secret", "CARE_AI_API_URL": "https://example.invalid", "CARE_AI_MODEL": "test-model"}
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    result, provider, reason = generate({}, {"symptoms": []}, config)
    assert provider == "basic-care" and "Provider request failure" in reason
    assert "URLError" in caplog.text and "test-secret" not in caplog.text

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b'{"choices": []}'
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **kw: Response())
    result, provider, reason = generate({}, {"symptoms": []}, config)
    assert provider == "basic-care" and "Invalid AI response" in reason


def test_recommendation_schema_validation():
    from app.services.care_assistant import _validate_recommendation
    with pytest.raises(ValueError):
        _validate_recommendation({"condition_summary": "Only one field"})
    with pytest.raises(ValueError):
        _validate_recommendation({
            "condition_summary": "Definitely a disease.",
            "possible_causes": ["possible"], "precautions": ["observe"], "care_plan": ["inspect"],
            "treatment_guidance": "No treatment indicated.", "follow_up": "Check later.",
        })
    safe = {
        "condition_summary": "Symptoms do not establish a diagnosis.",
        "possible_causes": ["Water stress is possible."], "precautions": ["Observe before treating."],
        "care_plan": ["Check soil moisture."],
        "treatment_guidance": "No pesticide or fungicide is supported by current evidence.",
        "follow_up": "Record changes over the next few days.",
    }
    assert _validate_recommendation(safe)["treatment_guidance"].startswith("No pesticide")
    safe["condition_summary"] = "Symptoms are not a confirmed diagnosis and remain uncertain."
    assert _validate_recommendation(safe)["condition_summary"].startswith("Symptoms are not")
    unsafe = dict(safe, treatment_guidance="Apply pesticide to affected leaves.")
    with pytest.raises(ValueError):
        _validate_recommendation(unsafe)


def test_follow_up_persists_without_duplicate_analysis(auth_client, app, monkeypatch):
    _analysis(auth_client)
    # Never let this route test use credentials loaded from the developer's .env.
    fallback, _, _ = generate({}, {"symptoms": ["yellowing"]}, {})
    monkeypatch.setattr("app.routes.analysis.generate_care", lambda *args: (
        fallback, "basic-care", "Gemini request failed (HTTP 400); showing basic-care guidance."
    ))
    response = auth_client.get("/analyze/1")
    csrf = get_csrf(response.get_data(as_text=True))
    response = auth_client.post("/analyze/1", data={"csrf_token": csrf, "symptoms": "yellowing",
        "affected_area": "older_leaves", "duration": "one week", "watering": "twice a week",
        "sunlight": "morning sun", "notes": "Some older leaves affected."}, follow_redirects=True)
    assert response.status_code == 200
    assert b"BASIC-CARE FALLBACK" in response.data
    assert b"Gemini request failed (HTTP 400)" in response.data
    assert b"AI provider diagnostic:" in response.data
    assert b"Plant Condition Summary" in response.data
    with app.app_context():
        assert Analysis.query.count() == 1
        saved = CareRecommendation.query.one()
        assert saved.analysis_id == 1 and saved.user_id == 1
        assert json.loads(saved.symptoms_json)["symptoms"] == ["yellowing"]
        assert json.loads(saved.recommendation_json)["_fallback_reason"] == "Gemini request failed (HTTP 400); showing basic-care guidance."


def test_empty_follow_up_rejected_and_legacy_prediction_hidden(auth_client, app, monkeypatch):
    _analysis(auth_client)
    page = auth_client.get("/analyze/1")
    response = auth_client.post("/analyze/1", data={"csrf_token": get_csrf(page.get_data(as_text=True))}, follow_redirects=True)
    assert b"Select at least one symptom" in response.data

    model_dir = app.config["MODELS_DIR"]
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "labels.json").write_text(json.dumps(["Tomato___Early_blight", "Tomato___healthy"]), encoding="utf-8")
    with app.app_context():
        analysis = app.extensions["sqlalchemy"].session.get(Analysis, 1)
        analysis.ai_prediction = "Tomato___Early_blight"
        analysis.ai_confidence = 99.0
        app.extensions["sqlalchemy"].session.commit()
    response = auth_client.get("/analyze/1")
    assert b"Inconclusive disease screening" not in response.data
    assert b"Model screening result" not in response.data
    assert b"Tomato___Early_blight" not in response.data



def test_provider_error_redacts_masked_key_fragments():
    from app.services.care_assistant import _safe_provider_detail
    echoed = "Incorrect API key provided: AQ.AbC123456789**********Last9."
    safe = _safe_provider_detail(echoed, "")
    assert "AQ." not in safe
    assert "Last9" not in safe
    assert "credential details redacted" in safe
