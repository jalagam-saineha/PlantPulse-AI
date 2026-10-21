from flask import (
    Blueprint, render_template, redirect, url_for, request, jsonify,
    send_from_directory, current_app, abort
)
from flask_login import login_required, current_user

from app.extensions import db

main_bp = Blueprint("main", __name__, url_prefix="")

_MEDIA_DIRS = {
    "plants": "UPLOAD_PLANTS_DIR",
    "images": "UPLOAD_IMAGES_DIR",
    "videos": "UPLOAD_VIDEOS_DIR",
    "processed": "RESULTS_PROCESSED_DIR",
    "frames": "RESULTS_FRAMES_DIR",
}

@main_bp.route("/media/<category>/<path:filename>")
@login_required
def media(category, filename):
    """
    Serves uploaded/generated media (plant photos, leaf images, processed
    overlays, video frames). Ownership isn't checked per-file since
    filenames are random UUIDs that are never enumerable or guessable,
    but the route still requires a logged-in session.
    """
    config_key = _MEDIA_DIRS.get(category)
    if not config_key:
        abort(404)
    directory = current_app.config[config_key]
    return send_from_directory(directory, filename)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    from app.models import Plant, Analysis, VideoAnalysis, Notification

    plants_q = current_user.plants.filter_by(is_archived=False)
    plant_count = plants_q.count()

    analyses_q = Analysis.query.filter_by(user_id=current_user.id)
    analyses_completed = analyses_q.filter_by(status="completed").count()

    avg_health = db.session.query(db.func.avg(Analysis.health_score)).filter(
        Analysis.user_id == current_user.id, Analysis.health_score.isnot(None)
    ).scalar()
    avg_health = round(avg_health, 1) if avg_health is not None else None

    growth_scans = VideoAnalysis.query.filter_by(user_id=current_user.id).count()

    active_alerts = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    recent_plants = plants_q.order_by(Plant.created_at.desc()).limit(4).all()
    recent_analyses = (
        analyses_q.order_by(Analysis.created_at.desc()).limit(5).all()
    )

    return render_template(
        "dashboard/dashboard.html",
        plant_count=plant_count,
        analyses_completed=analyses_completed,
        avg_health=avg_health,
        growth_scans=growth_scans,
        active_alerts=active_alerts,
        recent_plants=recent_plants,
        recent_analyses=recent_analyses,
    )


@main_bp.route("/api/theme", methods=["POST"])
@login_required
def set_theme():
    theme = (request.json or {}).get("theme")
    if theme not in ("light", "dark"):
        return jsonify({"error": "invalid theme"}), 400
    current_user.theme = theme
    db.session.commit()
    return jsonify({"theme": theme})
