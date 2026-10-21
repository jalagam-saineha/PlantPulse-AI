"""Cautious Gemini image assessment for uploaded plant photographs."""
import base64
from io import BytesIO
import json
import logging
import re
import socket
import urllib.error
from urllib.parse import quote
import urllib.request
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from app.services.care_assistant import _safe_provider_detail, _prescribes_unsupported_chemical

logger = logging.getLogger(__name__)
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_DIMENSION = 1536
MAX_INLINE_BYTES = 5 * 1024 * 1024
FIELDS = (
    "observed_symptoms", "likely_causes", "overall_condition", "image_evidence",
    "uncertainty_notes", "identification_note", "recommended_care",
    "treatment_guidance", "follow_up", "recommended_next_steps", "non_plant_image",
)
CONDITIONS = {"healthy-looking", "mild symptoms", "moderate symptoms", "severe symptoms", "inconclusive"}
PEST_SIGNS = re.compile(
    r"\b(?:mealybugs?|aphids?|scale insects?|whiteflies|spider mites?|mites?|thrips|larvae|caterpillars?|pest infestation|pest damage|cottony clusters?|cotton-like masses?|webbing|egg masses?)\b",
    re.I,
)
VISIBLE_DAMAGE = re.compile(
    r"\b(?:lesions?|holes?|rot(?:ting)?|mold|mould|necrosis|severe wilting|extensive damage|substantial damage|widespread damage|significant damage|heavy spotting)\b",
    re.I,
)


def get_ai_observed_concern(assessment):
    """Build a separate concern indicator from Gemini's observed evidence only."""
    if not isinstance(assessment, dict) or assessment.get("non_plant_image"):
        return None
    observations = [
        item.strip() for item in assessment.get("observed_symptoms", [])
        if isinstance(item, str) and item.strip()
        and not re.match(r"(?i)^\s*(?:no|none|without|not visible|not observed)\b", item)
    ]
    if not observations:
        if assessment.get("overall_condition") in {"moderate symptoms", "severe symptoms"}:
            return {"kind": "Plant symptoms need attention", "evidence": []}
        return None

    pest_evidence = [item for item in observations if PEST_SIGNS.search(item)]
    if pest_evidence:
        kind = "Possible visible pest signs"
    else:
        concerning_evidence = [item for item in observations if VISIBLE_DAMAGE.search(item)]
        condition = assessment.get("overall_condition")
        if not concerning_evidence and condition not in {"moderate symptoms", "severe symptoms"}:
            # Gemini's observed-symptom list itself is visual evidence worth surfacing,
            # even when leaf-only OpenCV measurements look healthy.
            concerning_evidence = observations
        kind = "Plant symptoms need attention" if condition in {"moderate symptoms", "severe symptoms"} or concerning_evidence else "Symptoms to monitor"
        pest_evidence = concerning_evidence
    return {"kind": kind, "evidence": pest_evidence or observations}


def _prepare_image(path):
    """Validate and compress an upload to bounded JPEG bytes for Gemini inline input."""
    try:
        size = path.stat().st_size
        if size <= 0:
            raise ValueError("The uploaded image is empty.")
        if size > MAX_SOURCE_BYTES:
            raise ValueError("The uploaded image exceeds the vision analysis size limit.")
        raw = path.read_bytes()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported image format for vision analysis.")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image dimensions exceed the vision analysis limit.")
                image = ImageOps.exif_transpose(source)
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGB", rgba.size, "white")
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
                image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format="JPEG", quality=84, optimize=True)
                if output.tell() > MAX_INLINE_BYTES:
                    image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    image.save(output, format="JPEG", quality=76, optimize=True)
                if output.tell() > MAX_INLINE_BYTES:
                    raise ValueError("Image could not be reduced to the vision request size limit.")
                return output.getvalue(), "image/jpeg"
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded image could not be prepared for vision analysis.") from exc


def _validate_assessment(value):
    if not isinstance(value, dict) or any(field not in value for field in FIELDS):
        raise ValueError("Vision response is missing required fields.")
    if not isinstance(value["overall_condition"], str) or value["overall_condition"].strip().lower() not in CONDITIONS:
        raise ValueError("Vision response has an invalid overall condition.")
    value["overall_condition"] = value["overall_condition"].strip().lower()
    if not isinstance(value["non_plant_image"], bool):
        raise ValueError("Vision response has an invalid image classification.")
    for field in ("observed_symptoms", "likely_causes", "recommended_care", "recommended_next_steps"):
        entries = value[field]
        if not isinstance(entries, list) or any(not isinstance(item, str) or not item.strip() for item in entries):
            raise ValueError("Vision response has an invalid list field.")
        value[field] = [item.strip()[:600] for item in entries[:8]]
        for item in value[field]:
            if re.search(r"(?<!not a )(?<!not )(?<!never )\b(?:definitely|certainly|confirmed (?:diagnosis|disease)|diagnosed with|is infected with)\b", item, re.I):
                raise ValueError("Vision response contains a definitive diagnosis claim.")
            if field in {"likely_causes", "recommended_care", "recommended_next_steps"} and _prescribes_unsupported_chemical(item):
                raise ValueError("Vision response prescribes an unsupported chemical treatment.")
    for field in ("image_evidence", "uncertainty_notes", "identification_note", "treatment_guidance", "follow_up"):
        content = value[field]
        if not isinstance(content, str) or (field != "identification_note" and not content.strip()):
            raise ValueError("Vision response has an invalid evidence field.")
        value[field] = content.strip()[:1200]
        if field == "treatment_guidance" and _prescribes_unsupported_chemical(value[field]):
            raise ValueError("Vision response prescribes an unsupported chemical treatment.")
    if value["non_plant_image"]:
        value["observed_symptoms"] = []
        value["likely_causes"] = []
        value["overall_condition"] = "inconclusive"
        value["recommended_care"] = []
        value["treatment_guidance"] = "No plant treatment can be recommended from this image."
        value["follow_up"] = "Upload a clear close-up of the plant or affected leaf."
        value["recommended_next_steps"] = ["Upload a clear photo showing the plant or affected leaf."]
    else:
        if value["overall_condition"] == "inconclusive":
            value["likely_causes"] = []
        if not value["recommended_next_steps"]:
            raise ValueError("Vision response has no recommended next steps.")
    return value


def analyze_uploaded_image(image_path, plant_context, config):
    """Return (assessment, provider, safe_reason); failures preserve IVP results."""
    api_key = config.get("CARE_AI_GEMINI_API_KEY")
    model = config.get("CARE_AI_GEMINI_MODEL")
    if not api_key or not model:
        logger.warning("Plant vision unavailable: Gemini configuration missing (key_present=%s model_present=%s)", bool(api_key), bool(model))
        return None, "unavailable", "Gemini vision is not configured; IVP results remain available."
    try:
        image_bytes, mime_type = _prepare_image(image_path)
    except ValueError as exc:
        logger.warning("Plant vision unavailable: image preparation failed")
        return None, "unavailable", str(exc)

    prompt = {
        "task": (
            "Analyze the attached image itself. The recorded plant identity is supplied context from the user's plant record, not an image-confirmed fact. "
            "Do not unnecessarily identify or re-identify the plant. Focus on visible symptoms and evidence: affected areas, yellowing, other discoloration, "
            "spots, holes, lesions, curling, wilting, pest signs, mold-like growth, and other observable abnormalities. "
            "Set identification_note to an empty string when the image does not genuinely appear inconsistent with the recorded identity. "
            "Only mention identification uncertainty in identification_note if clear visible evidence genuinely conflicts with that record; do not say "
            "'or similar broadleaf plant' or speculate about alternatives. Never claim visual confirmation of the recorded identity. "
            "Choose overall_condition from healthy-looking, mild symptoms, moderate symptoms, severe symptoms, or inconclusive. "
            "List possible causes only when supported; distinguish fungal, bacterial, pest-related, nutritional, environmental and other "
            "non-disease explanations, and explain the visible evidence for each candidate in likely_causes. Distinguish observations "
            "from hypotheses; a photo cannot establish pathogen identity, root or soil conditions, or other unseen facts. "
            "Give practical plant-appropriate care for watering, sunlight, drainage, sanitation, pruning, and monitoring in recommended_care. "
            "Recommend further inspection before disease-specific treatments and do not prescribe chemicals when uncertain. Include what "
            "to observe and when to take another image in follow_up. If blurry, distant, poorly lit, contains multiple plants, or lacks "
            "leaf detail, set overall_condition=inconclusive, describe the image limitations, leave likely_causes empty, and request a clear close-up. "
            "Use qualitative uncertainty, never probabilities. If not a plant image, set non_plant_image=true and provide no symptoms "
            "or causes. Return only one JSON object matching the schema."
        ),
        "recorded_plant": {
            "name": plant_context.get("plant_name") or "not recorded",
            "species": plant_context.get("recorded_species") or "not recorded",
            "variety": plant_context.get("variety") or "not recorded",
        },
        "open_cv_measurements": plant_context.get("measurements", {}),
    }
    properties = {
        "observed_symptoms": {"type": "array", "items": {"type": "string"}},
        "likely_causes": {"type": "array", "items": {"type": "string"}},
        "overall_condition": {"type": "string", "enum": sorted(CONDITIONS)},
        "image_evidence": {"type": "string"},
        "uncertainty_notes": {"type": "string"},
        "identification_note": {"type": "string"},
        "recommended_care": {"type": "array", "items": {"type": "string"}},
        "treatment_guidance": {"type": "string"},
        "follow_up": {"type": "string"},
        "recommended_next_steps": {"type": "array", "items": {"type": "string"}},
        "non_plant_image": {"type": "boolean"},
    }
    request_body = {
        "contents": [{"role": "user", "parts": [
            {"text": json.dumps(prompt, ensure_ascii=False)},
            {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
        ]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseFormat": {
                "text": {
                    "mimeType": "APPLICATION_JSON",
                    "schema": {"type": "object", "properties": properties, "required": list(FIELDS)},
                },
            },
        },
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(quote(str(model), safe=""))
    request = urllib.request.Request(url, data=json.dumps(request_body).encode("utf-8"), headers={
        "x-goog-api-key": api_key, "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=config.get("CARE_AI_TIMEOUT", 12)) as response:
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read(4096).decode("utf-8"))
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            error = {}
        status = _safe_provider_detail(error.get("status"), api_key) or "unknown"
        logger.warning("Plant vision Gemini HTTP failure: status=%s error_status=%s", exc.code, status)
        if exc.code == 429:
            reason = "Gemini vision quota or rate limit reached; IVP results remain available."
        elif exc.code in (401, 403):
            reason = "Gemini vision authentication failed; check the key and API restrictions."
        else:
            reason = f"Gemini vision request failed (HTTP {exc.code}); IVP results remain available."
        return None, "unavailable", reason
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        timed_out = isinstance(exc, (TimeoutError, socket.timeout)) or (
            isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, (TimeoutError, socket.timeout))
        )
        logger.warning("Plant vision Gemini request %s (%s)", "timed out" if timed_out else "connection failed", type(exc).__name__)
        reason = "Gemini vision request timed out; IVP results remain available." if timed_out else "Could not connect to Gemini vision; IVP results remain available."
        return None, "unavailable", reason

    try:
        payload = json.loads(response_body.decode("utf-8"))
        parts = payload["candidates"][0]["content"]["parts"]
        raw = "".join(part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))
        if not raw:
            raise ValueError("No readable Gemini candidate")
        assessment = _validate_assessment(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Plant vision Gemini response JSON parsing failed")
        return None, "unavailable", "Gemini vision returned malformed JSON; IVP results remain available."
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Plant vision Gemini response validation failed (%s)", type(exc).__name__)
        return None, "unavailable", "Gemini vision returned an incomplete or unsafe assessment; IVP results remain available."
    logger.info("Plant vision assessment completed: provider=gemini condition=%s non_plant=%s", assessment["overall_condition"], assessment["non_plant_image"])
    return assessment, "gemini", None
