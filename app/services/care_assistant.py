"""Structured and evidence-grounded plant care recommendations."""
import json
import logging
import re
import socket
import urllib.error
from urllib.parse import quote
import urllib.request

SECTIONS = ("condition_summary", "possible_causes", "precautions", "care_plan", "treatment_guidance", "follow_up")
SYMPTOMS = {"yellowing", "brown_spots", "curling", "wilting", "holes", "white_coating", "stunted_growth", "other"}
AREAS = {"older_leaves", "new_leaves", "stems", "fruit", "whole_plant", "unknown"}
logger = logging.getLogger(__name__)


def validate_form(form):
    symptoms = [s for s in form.getlist("symptoms") if s in SYMPTOMS]
    area = form.get("affected_area", "unknown")
    clean = lambda value: re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", (value or "")).strip()
    duration = clean(form.get("duration"))
    watering = clean(form.get("watering"))
    sunlight = clean(form.get("sunlight"))
    notes = clean(form.get("notes"))
    if not symptoms and not notes:
        raise ValueError("Select at least one symptom or add a short note.")
    if area not in AREAS:
        raise ValueError("Choose a valid affected area.")
    limits = (("duration", duration, 80), ("watering", watering, 80), ("sunlight", sunlight, 80), ("notes", notes, 1000))
    for label, value, limit in limits:
        if len(value) > limit:
            raise ValueError(f"{label.capitalize()} must be {limit} characters or fewer.")
    return {"symptoms": symptoms, "affected_area": area, "duration": duration,
            "watering": watering, "sunlight": sunlight, "notes": notes}


def _fallback(context, symptoms):
    observations = []
    for metric, label in (("yellowing", "yellowing"), ("damage", "visible damage"), ("dark_spots", "dark spots")):
        value = context.get(metric)
        if value is not None and value > 0:
            observations.append(f"Image processing measured {value}% {label}.")
    labels = {"yellowing": "yellowing", "brown_spots": "brown spots", "curling": "curling", "wilting": "wilting", "holes": "holes", "white_coating": "white coating", "stunted_growth": "stunted growth", "other": "other"}
    selected = symptoms.get("symptoms", [])
    reported = ", ".join(labels.get(s, s) for s in selected) or (symptoms.get("notes") or "no selected symptom")
    plant = context.get("plant_name", "this plant")
    species = context.get("species") or "species not recorded"
    observed = " ".join(observations) or "No measurable yellowing, damage, or dark spots were established by image processing."
    causes = ["Cause is not established from the current screening. The reported symptoms are nonspecific; check soil moisture and drainage, recent sunlight or temperature changes, and whether the issue is spreading."]
    if "yellowing" in selected or "wilting" in selected:
        causes.append("Water stress is one possibility when yellowing or wilting is reported. The report alone does not show whether soil is too wet or dry; check soil moisture and drainage before changing watering.")
    if any(s in selected for s in ("brown_spots", "white_coating", "holes")):
        causes.append("Pest or infectious damage is possible when spots, coating, or holes are reported. No specific pest or pathogen was identified; inspect both leaf surfaces and nearby plants for visible spread before considering treatment.")
    if "curling" in selected or "stunted_growth" in selected:
        causes.append("Environmental or growing-condition stress may contribute to curling or slow growth. The available evidence does not isolate a cause; note recent changes in light, temperature, and watering.")
    score = context.get("health_score")
    score_text = score if score is not None else "unavailable"
    return {
        "condition_summary": f"{plant} ({species}). Visual health score: {score_text}/100. Reported: {reported}. {observed} These observations are screening signals, not a diagnosis.",
        "possible_causes": causes,
        "precautions": ["Avoid abrupt changes to watering or fertilizer. Keep drainage holes clear, water according to the plant's needs and soil moisture, and avoid wetting foliage if leaf spotting is present. Inspect for pests before isolating the plant; isolate only if pests or spreading symptoms are observed."],
        "care_plan": ["Record which leaves or plant parts are affected.", "Check soil moisture and confirm excess water can drain.", "Inspect leaf undersides and stems for pests or spreading marks.", "Keep growing conditions steady and reassess in 3–5 days; record whether symptoms spread or new growth is affected."],
        "treatment_guidance": "No pesticide, fungicide, fertilizer dose, or chemical treatment is supported by the current evidence. Consult a local plant specialist or agricultural extension officer if symptoms spread rapidly, affect stems or fruit, or the plant continues to decline.",
        "follow_up": "Record symptom type, affected area, duration, watering, and sunlight. Upload a clear image of the same area in 3–5 days, or sooner if deterioration is rapid.",
    }


def _bind_recorded_identity(recommendation, context):
    """Keep every main care section anchored to the saved plant name."""
    name = str(context.get("plant_name") or "").strip()
    if not name or not isinstance(recommendation, dict):
        return recommendation
    similar_identity = re.compile(
        rf"(?i)\s+or\s+(?:a\s+)?similar(?:\s+(?:broadleaf|flowering|ornamental|house|garden)\s+plant|\s+species)"
    )

    def clean(text):
        return similar_identity.sub("", text)

    def normalize(text):
        text = clean(text)
        if name.casefold() not in text.casefold():
            return f"{name}: {text}"
        return text

    recommendation["condition_summary"] = normalize(recommendation.get("condition_summary", ""))
    for section in ("possible_causes", "precautions", "care_plan"):
        items = recommendation.get(section)
        if isinstance(items, list) and items:
            items[:] = [clean(item) for item in items]
            if name.casefold() not in items[0].casefold():
                items[0] = f"For {name}: {items[0]}"
    return recommendation


def _validate_recommendation(value):
    if not isinstance(value, dict) or any(k not in value for k in SECTIONS):
        raise ValueError("AI response is missing required recommendation sections.")
    for key in SECTIONS:
        content = value[key]
        if key in ("possible_causes", "precautions", "care_plan"):
            if not isinstance(content, list) or not content or any(not isinstance(x, str) or not x.strip() for x in content):
                raise ValueError("AI response contains an invalid list section.")
            cleaned = [x.strip()[:800] for x in content[:8]]
            if any(_unsafe_claim(x) for x in cleaned):
                raise ValueError("AI response contains unsupported certainty or visual claims.")
            value[key] = cleaned
        elif not isinstance(content, str) or not content.strip():
            raise ValueError("AI response contains an invalid text section.")
        else:
            cleaned = content.strip()[:2000]
            if _unsafe_claim(cleaned) or (key == "treatment_guidance" and _prescribes_unsupported_chemical(cleaned)):
                raise ValueError("AI response contains unsupported certainty or treatment claims.")
            value[key] = cleaned
    return value


def _unsafe_claim(text):
    # Avoid treating cautious negations such as "not a confirmed diagnosis"
    # as positive diagnostic claims.
    patterns = (
        r"(?<!not )(?<!never )(?<!cannot )(?<!can't )\b(?:definitely|certainly)\b",
        r"(?<!not a )(?<!not )(?<!never a )(?<!never )\bconfirmed diagnosis\b",
        r"(?<!not )\bis infected with\b",
        r"\bI can see\b",
        r"(?<!not )\bthe image shows\b",
        r"(?<!not )\bvisible on the image\b",
    )
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _prescribes_unsupported_chemical(text):
    """Reject recommendations to apply chemicals, while allowing safety warnings about them."""
    chemical = r"(?:pesticide|fungicide|herbicide|chemical mixture|chemical solution)"
    prescription = rf"\b(?:apply|use|spray|mix|dose|treat(?:ment)?\s+with)\b.{{0,35}}\b{chemical}\b"
    dosage = r"\b(?:apply|mix|spray|use)\b.{0,50}\b\d+(?:\.\d+)?\s*(?:ml|mg|g|oz|tsp|tbsp)\b"
    return bool(re.search(prescription, text, re.I) or re.search(dosage, text, re.I))


def _safe_provider_detail(value, api_key, private_values=()):
    if value is None or isinstance(value, (dict, list)):
        return ""
    text = str(value)
    # Provider error messages can echo credential fragments even when the full
    # configured key is unknown to this process. Strip common provider formats.
    text = re.sub(r"(?i)(?:incorrect|invalid)\s+api\s+key\s+provided\s*:\s*[^\s,;]+", "API credential details redacted", text)
    text = re.sub(r"(?i)\b(?:AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_*.-]{8,}|sk-[A-Za-z0-9_-]{8,})", "[redacted credential]", text)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = re.sub(r"(?i)Bearer\s+[^\s,;]+", "Bearer [redacted]", text)
    for private in sorted((str(v) for v in private_values if v and len(str(v)) >= 3), key=len, reverse=True):
        text = text.replace(private, "[redacted]")
    text = re.sub(r"[\r\n\t\x00-\x1f\x7f]", " ", text)
    return text[:240]


def _private_values(context, symptoms):
    """Collect user supplied strings only for redaction from provider error text."""
    values = []
    for source in (context, symptoms):
        if isinstance(source, dict):
            for value in source.values():
                values.extend(value if isinstance(value, list) else [value])
    return [value for value in values if isinstance(value, str)]


def _gemini_generate(context, symptoms, config, fallback):
    api_key = config.get("CARE_AI_GEMINI_API_KEY")
    model = config.get("CARE_AI_GEMINI_MODEL")
    if not api_key or not model:
        logger.warning("Care AI fallback: Gemini configuration missing (key_present=%s model_present=%s)",
                       bool(api_key), bool(model))
        return fallback, "basic-care", "Gemini API key or model is missing; showing basic-care guidance."

    url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(quote(model, safe=""))
    prompt = {
        "task": "Return one JSON object with condition_summary, possible_causes, precautions, care_plan, treatment_guidance, follow_up. Use strings for condition_summary, treatment_guidance, follow_up and arrays of strings for possible_causes, precautions, care_plan. The saved plant_name is the user's recorded identity: refer to that exact name consistently in condition_summary and the first item of possible_causes, precautions, and care_plan. Do not re-identify the plant or add phrases such as 'or similar broadleaf plant'. Base visual claims only on saved vision observations and reported symptoms. Treat disease labels as uncertain, never infer unseen visual findings, and do not recommend chemical treatments without sufficient evidence.",
        "evidence": context,
        "user_report": symptoms,
    }
    properties = {
        "condition_summary": {"type": "string"},
        "possible_causes": {"type": "array", "items": {"type": "string"}},
        "precautions": {"type": "array", "items": {"type": "string"}},
        "care_plan": {"type": "array", "items": {"type": "string"}},
        "treatment_guidance": {"type": "string"},
        "follow_up": {"type": "string"},
    }
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.2,
            # Use the current GenerateContent structured-output format and JSON
            # Schema types. responseSchema is deprecated by the Gemini REST API.
            "responseFormat": {
                "text": {
                    "mimeType": "APPLICATION_JSON",
                    "schema": {"type": "object", "properties": properties, "required": list(SECTIONS)},
                },
            },
        },
    }).encode("utf-8")
    try:
        request = urllib.request.Request(url, data=body, headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(request, timeout=config.get("CARE_AI_TIMEOUT", 12)) as response:
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read(4096).decode("utf-8"))
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            error = {}
        private = _private_values(context, symptoms)
        status = _safe_provider_detail(error.get("status"), api_key, private) or "unknown"
        code = _safe_provider_detail(error.get("code"), api_key, private) or "unknown"
        message = _safe_provider_detail(error.get("message"), api_key, private) or "unavailable"
        logger.warning("Care AI Gemini fallback: HTTP %s (error_status=%s error_code=%s message=%s)",
                       exc.code, status, code, message)
        if exc.code in (401, 403):
            reason = "Gemini authentication failed; check the key and its API restrictions. Showing basic-care guidance."
        elif exc.code == 429:
            reason = "Gemini quota or rate limit reached; showing basic-care guidance."
        else:
            reason = f"Gemini request failed (HTTP {exc.code}); showing basic-care guidance."
        return fallback, "basic-care", reason
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        timed_out = isinstance(exc, (TimeoutError, socket.timeout)) or (
            isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, (TimeoutError, socket.timeout))
        )
        category = "timeout" if timed_out else "connection failure"
        logger.warning("Care AI Gemini fallback: %s (%s)", category, type(exc).__name__)
        if timed_out:
            return fallback, "basic-care", "Gemini request timed out; showing basic-care guidance."
        return fallback, "basic-care", "Could not connect to Gemini; showing basic-care guidance."

    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Care AI Gemini fallback: response JSON parsing failure (%s)", type(exc).__name__)
        return fallback, "basic-care", "Gemini returned invalid response JSON; showing basic-care guidance."
    try:
        candidate = payload["candidates"][0]
        parts = candidate["content"]["parts"]
        raw = "".join(part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))
        if not raw:
            raise ValueError("candidate contained no text")
    except (KeyError, IndexError, TypeError, ValueError):
        block_reason = payload.get("promptFeedback", {}).get("blockReason", "unknown") if isinstance(payload, dict) else "unknown"
        safe_block_reason = _safe_provider_detail(block_reason, api_key, _private_values(context, symptoms)) or "unknown"
        logger.warning("Care AI Gemini fallback: no readable candidate (block_reason=%s)", safe_block_reason)
        return fallback, "basic-care", "Gemini returned no readable recommendation; showing basic-care guidance."
    try:
        recommendation = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Care AI Gemini fallback: recommendation JSON parsing failure (%s)", type(exc).__name__)
        return fallback, "basic-care", "Gemini recommendation was not valid JSON; showing basic-care guidance."
    try:
        result = _validate_recommendation(recommendation)
    except ValueError as exc:
        logger.warning("Care AI Gemini fallback: recommendation validation failure (%s)", str(exc))
        return fallback, "basic-care", "Gemini recommendation did not meet safety and format requirements; showing basic-care guidance."
    return result, "configured-ai", None


def generate(context, symptoms, config):
    fallback = _bind_recorded_identity(_fallback(context, symptoms), context)
    provider = str(config.get("CARE_AI_PROVIDER", "openai")).strip().lower()
    if provider == "gemini":
        recommendation, actual_provider, error = _gemini_generate(context, symptoms, config, fallback)
        return _bind_recorded_identity(recommendation, context), actual_provider, error
    if provider != "openai":
        logger.warning("Care AI fallback: unsupported provider configured")
        return fallback, "basic-care", "Unsupported AI provider; showing basic-care guidance."
    api_key = config.get("CARE_AI_API_KEY")
    api_url = config.get("CARE_AI_API_URL")
    model = config.get("CARE_AI_MODEL")
    if not api_key or not api_url or not model:
        logger.warning("Care AI fallback: missing API configuration (key_present=%s url_present=%s model_present=%s)",
                       bool(api_key), bool(api_url), bool(model))
        return fallback, "basic-care", "Missing API configuration; showing basic-care guidance."
    prompt = {
        "task": "Return JSON with condition_summary, possible_causes, precautions, care_plan, treatment_guidance, follow_up. Use short text for summary/treatment/follow_up and arrays of strings for causes/precautions/care_plan. Treat disease labels as uncertain, use only supplied observations, never infer unseen visual findings, avoid chemicals without sufficient evidence.",
        "evidence": context, "user_report": symptoms,
    }
    body = json.dumps({"model": model, "temperature": 0.2,
                       "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": json.dumps(prompt)}]}).encode()
    try:
        request = urllib.request.Request(api_url, data=body, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        })
        with urllib.request.urlopen(request, timeout=config.get("CARE_AI_TIMEOUT", 12)) as response:
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            error_payload = json.loads(exc.read(4096).decode("utf-8"))
            error_data = error_payload.get("error", {}) if isinstance(error_payload, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            error_data = {}
        private = _private_values(context, symptoms)
        error_type = _safe_provider_detail(error_data.get("type"), api_key, private) or "unknown"
        error_code = _safe_provider_detail(error_data.get("code"), api_key, private) or "unknown"
        error_message = _safe_provider_detail(error_data.get("message"), api_key, private) or "unavailable"
        raw_error_code = str(error_data.get("code") or "").casefold()
        raw_error_type = str(error_data.get("type") or "").casefold()
        if status in (401, 403):
            reason = "Provider authentication failure; check the configured API credential."
            category = "authentication failure"
        elif status == 429:
            if raw_error_code in {"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"} or raw_error_type == "insufficient_quota":
                reason = "AI provider quota is exhausted; add API credits or check project billing. Showing basic-care guidance."
                category = "quota exhausted"
            else:
                reason = "AI provider rate limit reached; retry later. Showing basic-care guidance."
                category = "rate limit"
        else:
            reason = "Provider request failure; showing basic-care guidance."
            category = "provider request failure"
        logger.warning("Care AI fallback: %s (HTTP %s; OpenAI error_type=%s error_code=%s message=%s)",
                       category, status, error_type, error_code, error_message)
        return fallback, "basic-care", reason
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        logger.warning("Care AI fallback: provider request failure (%s)", type(exc).__name__)
        return fallback, "basic-care", "Provider request failure; showing basic-care guidance."

    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Care AI fallback: response JSON parsing failure (%s)", type(exc).__name__)
        return fallback, "basic-care", "Invalid AI response; showing basic-care guidance."
    try:
        raw = payload["choices"][0]["message"]["content"]
        if not isinstance(raw, str):
            raise TypeError("assistant content was not text")
    except (KeyError, IndexError, TypeError):
        logger.warning("Care AI fallback: response is missing expected choices/message/content fields")
        return fallback, "basic-care", "Invalid AI response; showing basic-care guidance."
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Care AI fallback: recommendation JSON parsing failure (%s)", type(exc).__name__)
        return fallback, "basic-care", "Invalid AI response; showing basic-care guidance."
    try:
        result = _validate_recommendation(decoded)
    except ValueError as exc:
        # Validation errors are fixed internal messages, not provider payloads.
        logger.warning("Care AI fallback: recommendation validation failure (%s)", str(exc))
        return fallback, "basic-care", "AI recommendation did not meet safety and format requirements; showing basic-care guidance."
    return _bind_recorded_identity(result, context), "configured-ai", None
