from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    current_app, abort, jsonify
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Plant, VideoAnalysis
from app.utils.uploads import validate_and_save, UploadError
from app.services.video_processor import process_video_async, probe_video

growth_bp = Blueprint("growth", __name__, url_prefix="/growth")

MAX_VIDEO_BYTES = 150 * 1024 * 1024  # 150 MB
ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "webm"}


def _owned_plant_or_404(plant_id: int) -> Plant:
    plant = db.session.get(Plant, plant_id)
    if plant is None:
        abort(404)
    if plant.user_id != current_user.id:
        abort(403)
    return plant


def _owned_video_or_404(video_id: int) -> VideoAnalysis:
    video = db.session.get(VideoAnalysis, video_id)
    if video is None:
        abort(404)
    if video.user_id != current_user.id:
        abort(403)
    return video


def _recent_scans():
    return (
        VideoAnalysis.query.filter_by(user_id=current_user.id)
        .order_by(VideoAnalysis.created_at.desc())
        .limit(10)
        .all()
    )


@growth_bp.route("/", methods=["GET", "POST"])
@login_required
def growth_home():
    plants = current_user.plants.filter_by(is_archived=False).order_by(Plant.name).all()
    selected_plant_id = request.values.get("plant_id", type=int)

    if not plants:
        flash("Add a plant first, then come back to start a growth scan.", "info")
        return redirect(url_for("plants.create_plant"))

    if request.method == "POST":
        plant_id = request.form.get("plant_id", type=int)
        plant = _owned_plant_or_404(plant_id) if plant_id else None
        if not plant:
            flash("Please select a plant.", "error")
            return render_template("growth/growth.html", plants=plants, scans=_recent_scans(),
                                    selected_plant_id=selected_plant_id), 400

        busy = VideoAnalysis.query.filter(
            VideoAnalysis.user_id == current_user.id,
            VideoAnalysis.status.in_(["QUEUED", "PROCESSING"]),
        ).first()
        if busy:
            flash("A growth scan is already processing. Please wait for it to finish.", "error")
            return redirect(url_for("growth.growth_home"))

        video_file = request.files.get("video")
        try:
            video_name = validate_and_save(
                video_file, current_app.config["UPLOAD_VIDEOS_DIR"], ALLOWED_VIDEO_EXT, MAX_VIDEO_BYTES
            )
        except UploadError as exc:
            flash(str(exc), "error")
            return render_template("growth/growth.html", plants=plants, scans=_recent_scans(),
                                    selected_plant_id=plant.id), 400

        interval_raw = request.form.get("interval", "5")
        interval = {"1": 1, "5": 5, "10": 10}.get(interval_raw, 5)
        if interval_raw == "auto":
            try:
                meta = probe_video(current_app.config["UPLOAD_VIDEOS_DIR"] / video_name)
                duration = meta["duration_seconds"] or 30
                interval = max(2, min(15, int(duration / 10) or 2))
            except ValueError:
                interval = 5

        video = VideoAnalysis(
            user_id=current_user.id,
            plant_id=plant.id,
            video_path=video_name,
            sampling_interval_seconds=interval,
            status="QUEUED",
        )
        db.session.add(video)
        db.session.commit()

        process_video_async(current_app._get_current_object(), video.id)

        current_app.logger.info("Growth scan queued: id=%s plant=%s", video.id, plant.id)
        flash("Growth scan queued and processing in the background.", "success")
        return redirect(url_for("growth.growth_result", video_id=video.id))

    return render_template(
        "growth/growth.html", plants=plants, scans=_recent_scans(), selected_plant_id=selected_plant_id
    )


@growth_bp.route("/<int:video_id>")
@login_required
def growth_result(video_id):
    video = _owned_video_or_404(video_id)
    frames = video.frames.all()
    chart_data = {
        "labels": [f.timestamp_seconds for f in frames],
        "leaf_area": [f.leaf_area_px for f in frames],
        "health_score": [f.health_score for f in frames],
        "green_coverage": [f.green_coverage for f in frames],
        "damage": [f.damage for f in frames],
    }
    return render_template("growth/result.html", video=video, frames=frames, chart_data=chart_data)


@growth_bp.route("/<int:video_id>/status.json")
@login_required
def growth_status(video_id):
    video = _owned_video_or_404(video_id)
    return jsonify({
        "status": video.status,
        "progress_percent": video.progress_percent,
        "error_message": video.error_message,
        "frame_count": video.frames.count(),
    })
