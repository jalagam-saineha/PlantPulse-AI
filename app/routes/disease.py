import json
from pathlib import Path

from flask import Blueprint, render_template, current_app, request
from flask_login import login_required

disease_bp = Blueprint("disease", __name__, url_prefix="/diseases")


def _load_labels(models_dir: Path):
    labels_path = models_dir / "labels.json"
    if not labels_path.exists():
        return []
    try:
        with open(labels_path, "r", encoding="utf-8") as fh:
            labels = json.load(fh)
        return labels if isinstance(labels, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _load_disease_info(data_dir: Path) -> dict:
    info_path = data_dir / "disease_info.json"
    if not info_path.exists():
        return {}
    try:
        with open(info_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


@disease_bp.route("/")
@login_required
def disease_library():
    labels = _load_labels(current_app.config["MODELS_DIR"])
    info = _load_disease_info(current_app.config["DATA_DIR"])

    search = (request.args.get("q") or "").strip().lower()

    diseases = []
    for label in labels:
        if search and search not in label.lower():
            continue
        entry = info.get(label)
        diseases.append({
            "label": label,
            "has_info": entry is not None,
            "species": entry.get("species") if entry else None,
            "symptoms": entry.get("symptoms") if entry else None,
            "prevention": entry.get("prevention") if entry else None,
            "treatment": entry.get("treatment") if entry else None,
        })

    return render_template(
        "disease/library.html", diseases=diseases, search=search, model_installed=bool(labels)
    )
