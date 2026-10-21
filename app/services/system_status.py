"""
Real runtime status checks for the System Status page and Settings →
System Information tab. Every value here is the result of an actual
check performed at request time — nothing is a hardcoded "READY".
"""
import platform
import shutil
import sys
from pathlib import Path

from app.services.disease_predictor import get_model_status


def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def get_full_status(app) -> dict:
    from app.extensions import db
    from sqlalchemy import text

    # --- Database ---
    db_state, db_detail = "ERROR", "Could not query the database."
    try:
        db.session.execute(text("SELECT 1"))
        db_state, db_detail = "READY", "Connected"
    except Exception as exc:
        db_detail = str(exc)

    # --- Computer Vision (OpenCV) ---
    cv_state, cv_detail = "NOT INSTALLED", "OpenCV is not importable."
    try:
        import cv2
        cv_state, cv_detail = "READY", f"OpenCV {cv2.__version__}"
    except ImportError:
        pass

    # --- TensorFlow / AI model ---
    model_status = get_model_status(app.config["MODELS_DIR"])
    if model_status["ready"]:
        ai_state, ai_detail = "READY", f"Model loaded ({model_status['label_count']} classes)"
    elif not model_status["tensorflow_available"]:
        ai_state, ai_detail = "NOT INSTALLED", "TensorFlow is not installed (see requirements-ai.txt)."
    elif not model_status["files_present"]:
        ai_state, ai_detail = "NOT INSTALLED", "models/plant_disease_model.keras or labels.json is missing."
    else:
        ai_state, ai_detail = "WARNING", "Model files present but labels.json is invalid."

    tf_state = "READY" if model_status["tensorflow_available"] else "NOT INSTALLED"
    tf_detail = model_status["tensorflow_version"] or "Not installed"

    # --- Video processor (thread-based; always available if OpenCV is) ---
    video_state = "READY" if cv_state == "READY" else "NOT INSTALLED"

    # --- Report generator (ReportLab) ---
    rl_state, rl_detail = "NOT INSTALLED", "ReportLab is not importable."
    try:
        import reportlab
        rl_state, rl_detail = "READY", f"ReportLab {reportlab.Version}"
    except ImportError:
        pass

    # --- Storage ---
    storage_state, storage_detail = "READY", ""
    try:
        test_file = Path(app.config["INSTANCE_DIR"]) / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        total, used, free = shutil.disk_usage(app.config["INSTANCE_DIR"])
        storage_detail = f"{free // (1024**3)} GB free of {total // (1024**3)} GB"
    except Exception as exc:
        storage_state, storage_detail = "ERROR", str(exc)

    return {
        "database": {"state": db_state, "detail": db_detail},
        "computer_vision": {"state": cv_state, "detail": cv_detail},
        "tensorflow": {"state": tf_state, "detail": tf_detail},
        "ai_model": {"state": ai_state, "detail": ai_detail},
        "video_processor": {"state": video_state, "detail": "Background-thread processing"},
        "report_generator": {"state": rl_state, "detail": rl_detail},
        "storage": {"state": storage_state, "detail": storage_detail},
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }
