"""
Optional AI disease-screening adapter.

TensorFlow and a trained model are both OPTIONAL. If either is missing,
get_model_status() reports that honestly and predict() returns None —
the caller must show "AI disease model not installed" rather than any
fabricated prediction. The model (once present) is loaded lazily and
cached for the lifetime of the process.
"""
import json
import threading
from pathlib import Path

_cache = {"model": None, "labels": None, "loaded": False}
_cache_lock = threading.Lock()


def get_model_status(models_dir: Path) -> dict:
    model_path = Path(models_dir) / "plant_disease_model.keras"
    labels_path = Path(models_dir) / "labels.json"

    try:
        import tensorflow  # noqa: F401
        tf_available = True
        tf_version = tensorflow.__version__
    except ImportError:
        tf_available = False
        tf_version = None

    files_present = model_path.exists() and labels_path.exists()
    labels_valid = False
    label_count = 0
    if labels_path.exists():
        try:
            with open(labels_path, "r", encoding="utf-8") as fh:
                labels = json.load(fh)
            labels_valid = (
                isinstance(labels, list)
                and len(labels) > 0
                and all(isinstance(label, str) and label.strip() for label in labels)
                and len(set(labels)) == len(labels)
            )
            label_count = len(labels) if labels_valid else 0
        except (json.JSONDecodeError, OSError):
            labels_valid = False

    return {
        "tensorflow_available": tf_available,
        "tensorflow_version": tf_version,
        "files_present": files_present,
        "labels_valid": labels_valid,
        "label_count": label_count,
        "ready": tf_available and files_present and labels_valid,
        "model_path": str(model_path),
    }


def get_species_mismatch(plant_species: str | None, prediction: str | None, models_dir: Path) -> str | None:
    """Return the predicted crop only when both species are known and differ."""
    if not isinstance(plant_species, str) or not plant_species.strip():
        return None
    if not isinstance(prediction, str) or "___" not in prediction:
        return None

    try:
        with open(Path(models_dir) / "labels.json", "r", encoding="utf-8") as fh:
            labels = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(labels, list):
        return None

    def normalize(value: str) -> str:
        return "".join(char.casefold() for char in value if char.isalnum())

    known_species = {
        normalize(label.partition("___")[0].strip())
        for label in labels
        if isinstance(label, str) and "___" in label
    }
    selected_species = normalize(plant_species.strip())
    prediction_species = prediction.partition("___")[0].strip()
    normalized_prediction_species = normalize(prediction_species)

    if (
        not selected_species
        or selected_species not in known_species
        or normalized_prediction_species not in known_species
        or selected_species == normalized_prediction_species
    ):
        return None
    return prediction_species


def is_species_compatible(plant_species: str | None, prediction: str | None, models_dir: Path) -> bool | None:
    """Return whether the label crop matches a known recorded crop; None means insufficient evidence."""
    if not isinstance(plant_species, str) or not plant_species.strip() or not isinstance(prediction, str) or "___" not in prediction:
        return None
    try:
        with open(Path(models_dir) / "labels.json", "r", encoding="utf-8") as fh:
            labels = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(labels, list):
        return None
    normalize = lambda value: "".join(ch.casefold() for ch in value if ch.isalnum())
    known_species = {normalize(label.partition("___")[0]) for label in labels if isinstance(label, str) and "___" in label}
    plant = normalize(plant_species)
    predicted = normalize(prediction.partition("___")[0])
    if not plant or plant not in known_species or predicted not in known_species:
        return None
    return plant == predicted


def predict(image_path: Path, models_dir: Path, input_size: int = 224):
    """
    Returns None (no fake prediction) unless TensorFlow, the model file,
    and labels.json are all present and valid.
    """
    status = get_model_status(models_dir)
    if not status["ready"]:
        return None

    import numpy as np
    import tensorflow as tf
    from PIL import Image

    with _cache_lock:
        if not _cache["loaded"]:
            model = tf.keras.models.load_model(str(Path(models_dir) / "plant_disease_model.keras"))
            with open(Path(models_dir) / "labels.json", "r", encoding="utf-8") as fh:
                labels = json.load(fh)
            output_shape = model.output_shape
            if isinstance(output_shape, list) or len(output_shape) != 2:
                raise ValueError("Disease model must return one class-probability vector.")
            if output_shape[-1] != len(labels):
                raise ValueError(
                    f"Disease model returns {output_shape[-1]} classes but labels.json contains {len(labels)} labels."
                )
            _cache["model"] = model
            _cache["labels"] = labels
            _cache["loaded"] = True

    model = _cache["model"]
    labels = _cache["labels"]

    with Image.open(image_path) as source:
        img = source.convert("RGB").resize((input_size, input_size))
    arr = (np.asarray(img, dtype=np.float32) / 255.0)[None, ...]

    preds = np.asarray(model.predict(arr, verbose=0))[0]
    if preds.ndim != 1 or len(preds) != len(labels):
        raise ValueError("Disease model output does not match the saved class labels.")
    if not np.all(np.isfinite(preds)) or np.any(preds < 0) or np.any(preds > 1):
        raise ValueError("Disease model returned invalid class probabilities.")
    order = np.argsort(preds)[::-1]

    top_idx = int(order[0])
    alternatives = [
        {"label": labels[int(i)], "confidence": round(float(preds[int(i)]) * 100, 1)}
        for i in order[1:4]
        if int(i) < len(labels)
    ]

    return {
        "prediction": labels[top_idx] if top_idx < len(labels) else "Unknown",
        "confidence": round(float(preds[top_idx]) * 100, 1),
        "alternatives": alternatives,
        "model_name": "plant_disease_model.keras",
    }
