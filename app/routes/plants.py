from datetime import datetime, date

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    current_app, abort
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Plant
from app.utils.uploads import validate_and_save, UploadError

plants_bp = Blueprint("plants", __name__, url_prefix="/plants")

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB, matches Leaf Analysis limit


def _get_owned_plant_or_404(plant_id: int) -> Plant:
    plant = db.session.get(Plant, plant_id)
    if plant is None:
        abort(404)
    if plant.user_id != current_user.id:
        abort(403)
    return plant


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@plants_bp.route("/")
@login_required
def list_plants():
    query = current_user.plants
    show_archived = request.args.get("archived") == "1"
    query = query.filter_by(is_archived=show_archived)

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(Plant.name.ilike(like), Plant.species.ilike(like))
        )

    plants = query.order_by(Plant.created_at.desc()).all()
    return render_template(
        "plants/list.html", plants=plants, search=search, show_archived=show_archived
    )


@plants_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_plant():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        species = (request.form.get("species") or "").strip()
        variety = (request.form.get("variety") or "").strip()
        location = (request.form.get("location") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        planting_date = _parse_date(request.form.get("planting_date"))

        errors = []
        if len(name) < 2:
            errors.append("Please give the plant a name.")

        image_filename = None
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            try:
                image_filename = validate_and_save(
                    image_file,
                    current_app.config["UPLOAD_PLANTS_DIR"],
                    {"jpg", "jpeg", "png", "webp"},
                    MAX_IMAGE_BYTES,
                )
            except UploadError as exc:
                errors.append(str(exc))

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("plants/form.html", plant=None, form=request.form), 400

        plant = Plant(
            user_id=current_user.id,
            name=name,
            species=species or None,
            variety=variety or None,
            location=location or None,
            notes=notes or None,
            planting_date=planting_date,
            image_path=image_filename,
        )
        db.session.add(plant)
        db.session.commit()
        current_app.logger.info("Plant created: id=%s name=%r user=%s", plant.id, plant.name, current_user.id)
        flash(f'"{plant.name}" was added to your workspace.', "success")
        return redirect(url_for("plants.view_plant", plant_id=plant.id))

    return render_template("plants/form.html", plant=None, form=None)


@plants_bp.route("/<int:plant_id>")
@login_required
def view_plant(plant_id):
    plant = _get_owned_plant_or_404(plant_id)

    age_days = None
    if plant.planting_date:
        age_days = (date.today() - plant.planting_date).days

    analyses = plant.analyses.limit(6).all()
    video_scans = plant.video_analyses.limit(6).all()

    return render_template(
        "plants/detail.html",
        plant=plant,
        age_days=age_days,
        analyses=analyses,
        video_scans=video_scans,
        analysis_count=plant.analyses.count(),
        scan_count=plant.video_analyses.count(),
    )


@plants_bp.route("/<int:plant_id>/edit", methods=["GET", "POST"])
@login_required
def edit_plant(plant_id):
    plant = _get_owned_plant_or_404(plant_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        species = (request.form.get("species") or "").strip()
        variety = (request.form.get("variety") or "").strip()
        location = (request.form.get("location") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        planting_date = _parse_date(request.form.get("planting_date"))

        if len(name) < 2:
            flash("Please give the plant a name.", "error")
            return render_template("plants/form.html", plant=plant, form=request.form), 400

        image_file = request.files.get("image")
        if image_file and image_file.filename:
            try:
                plant.image_path = validate_and_save(
                    image_file,
                    current_app.config["UPLOAD_PLANTS_DIR"],
                    {"jpg", "jpeg", "png", "webp"},
                    MAX_IMAGE_BYTES,
                )
            except UploadError as exc:
                flash(str(exc), "error")
                return render_template("plants/form.html", plant=plant, form=request.form), 400

        plant.name = name
        plant.species = species or None
        plant.variety = variety or None
        plant.location = location or None
        plant.notes = notes or None
        plant.planting_date = planting_date
        db.session.commit()

        current_app.logger.info("Plant updated: id=%s", plant.id)
        flash("Plant profile updated.", "success")
        return redirect(url_for("plants.view_plant", plant_id=plant.id))

    return render_template("plants/form.html", plant=plant, form=None)


@plants_bp.route("/<int:plant_id>/archive", methods=["POST"])
@login_required
def archive_plant(plant_id):
    plant = _get_owned_plant_or_404(plant_id)
    plant.is_archived = not plant.is_archived
    db.session.commit()
    state = "archived" if plant.is_archived else "restored"
    current_app.logger.info("Plant %s: id=%s", state, plant.id)
    flash(f'"{plant.name}" was {state}.', "success")
    return redirect(request.referrer or url_for("plants.list_plants"))


@plants_bp.route("/<int:plant_id>/delete", methods=["POST"])
@login_required
def delete_plant(plant_id):
    plant = _get_owned_plant_or_404(plant_id)
    name = plant.name
    db.session.delete(plant)
    db.session.commit()
    current_app.logger.info("Plant deleted: %r", name)
    flash(f'"{name}" and all of its analyses were deleted.', "success")
    return redirect(url_for("plants.list_plants"))
