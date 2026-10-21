import json
import uuid

import cv2

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    current_app, abort
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Plant, Analysis, TimelineEvent, Notification, CareRecommendation, PlantVisionAssessment
from app.utils.uploads import validate_and_save, UploadError
from app.services.image_processor import analyze_leaf_image
from app.services.health_score import compute_health_score
from app.services.care_assistant import validate_form, generate as generate_care
from app.services.plant_vision import analyze_uploaded_image, get_ai_observed_concern

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analyze")

MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}


def _owned_plant_or_404(plant_id: int) -> Plant:
    plant = db.session.get(Plant, plant_id)
    if plant is None:
        abort(404)
    if plant.user_id != current_user.id:
        abort(403)
    return plant


@analysis_bp.route("/", methods=["GET", "POST"])
@login_required
def analyze_form():
    plants = current_user.plants.filter_by(is_archived=False).order_by(Plant.name).all()
    selected_plant_id = request.values.get("plant_id", type=int)

    if not plants:
        flash("Add a plant first, then come back to run a leaf analysis.", "info")
        return redirect(url_for("plants.create_plant"))

    if request.method == "POST":
        plant_id = request.form.get("plant_id", type=int)
        plant = _owned_plant_or_404(plant_id) if plant_id else None
        if not plant:
            flash("Please select a plant.", "error")
            return render_template(
                "analysis/analyze.html", plants=plants, selected_plant_id=selected_plant_id
            ), 400

        image_file = request.files.get("image")
        try:
            original_name = validate_and_save(
                image_file, current_app.config["UPLOAD_IMAGES_DIR"], ALLOWED_IMAGE_EXT, MAX_IMAGE_BYTES
            )
        except UploadError as exc:
            flash(str(exc), "error")
            return render_template(
                "analysis/analyze.html", plants=plants, selected_plant_id=plant.id
            ), 400

        source_path = current_app.config["UPLOAD_IMAGES_DIR"] / original_name

        try:
            metrics, processed_name, overlay_name = analyze_leaf_image(
                source_path, current_app.config["RESULTS_PROCESSED_DIR"]
            )
            score = compute_health_score(metrics)
        except ValueError as exc:
            if "No foliage could be detected" not in str(exc):
                current_app.logger.warning("Analysis failed for plant %s: %s", plant.id, exc)
                flash(str(exc), "error")
                return render_template(
                    "analysis/analyze.html", plants=plants, selected_plant_id=plant.id
                ), 400
            # Still permit image vision for unfamiliar foliage or non-plant photos.
            # Do not turn missing segmentation into a fabricated zero-health score.
            image = cv2.imread(str(source_path))
            if image is None:
                flash("Could not read the uploaded image. It may be corrupted or unsupported.", "error")
                return render_template(
                    "analysis/analyze.html", plants=plants, selected_plant_id=plant.id
                ), 400
            output_dir = current_app.config["RESULTS_PROCESSED_DIR"]
            output_dir.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            processed_name, overlay_name = f"{token}_processed.jpg", f"{token}_overlay.jpg"
            if not cv2.imwrite(str(output_dir / processed_name), image) or not cv2.imwrite(str(output_dir / overlay_name), image):
                flash("Could not prepare image previews.", "error")
                return render_template(
                    "analysis/analyze.html", plants=plants, selected_plant_id=plant.id
                ), 400
            metrics = {
                "leaf_area_px": 0, "leaf_coverage": None, "yellowing": None,
                "damage": None, "dark_spots": None, "affected_area": None,
            }
            score = {"overall": None, "label": "Not calculated", "components": {
                "leaf_vitality": None, "color_health": None,
                "damage_condition": None, "spot_condition": None,
            }}
            current_app.logger.info("OpenCV foliage segmentation unavailable; continuing with Gemini vision")

        analysis = Analysis(
            user_id=current_user.id,
            plant_id=plant.id,
            original_image=original_name,
            processed_image=processed_name,
            overlay_image=overlay_name,
            status="completed",
            leaf_coverage=metrics["leaf_coverage"],
            yellowing=metrics["yellowing"],
            damage=metrics["damage"],
            dark_spots=metrics["dark_spots"],
            affected_area=metrics["affected_area"],
            leaf_area_px=metrics["leaf_area_px"],
            health_score=score["overall"],
        )

        db.session.add(analysis)
        db.session.flush()  # get analysis.id before attaching its vision result

        try:
            vision_data, vision_provider, vision_error = analyze_uploaded_image(
                source_path,
                {
                    "plant_name": plant.name,
                    "recorded_species": plant.species,
                    "variety": plant.variety,
                    "measurements": {
                        "leaf_coverage": metrics["leaf_coverage"],
                        "yellowing": metrics["yellowing"],
                        "visible_damage": metrics["damage"],
                        "dark_spots": metrics["dark_spots"],
                    },
                },
                current_app.config,
            )
        except Exception as exc:
            current_app.logger.warning("Plant vision assessment unavailable (%s)", type(exc).__name__)
            vision_data, vision_provider, vision_error = None, "unavailable", "Vision analysis failed; IVP results remain available."
        db.session.add(PlantVisionAssessment(
            analysis_id=analysis.id, provider=vision_provider,
            assessment_json=json.dumps(vision_data, ensure_ascii=False) if vision_data else None,
            error_reason=vision_error,
        ))

        db.session.add(TimelineEvent(
            plant_id=plant.id,
            source_type="analysis",
            source_id=analysis.id,
            event_date=analysis.created_at,
            image_path=processed_name,
            health_score=score["overall"],
            leaf_area_px=metrics["leaf_area_px"],
            yellowing=metrics["yellowing"],
            damage=metrics["damage"],
        ))

        if current_user.notifications_enabled:
            db.session.add(Notification(
                user_id=current_user.id,
                title="Analysis completed",
                message=(f'Leaf analysis for "{plant.name}" scored {score["overall"]}/100.'
                         if score["overall"] is not None else
                         f'Image analysis for "{plant.name}" completed; OpenCV leaf measurements were unavailable.'),
                link=url_for("analysis.result", analysis_id=analysis.id),
            ))

        db.session.commit()
        current_app.logger.info(
            "Analysis completed: id=%s plant=%s score=%s", analysis.id, plant.id, score["overall"]
        )
        flash("Analysis complete.", "success")
        return redirect(url_for("analysis.result", analysis_id=analysis.id))

    return render_template("analysis/analyze.html", plants=plants, selected_plant_id=selected_plant_id)


@analysis_bp.route("/<int:analysis_id>", methods=["GET", "POST"])
@login_required
def result(analysis_id):
    analysis = db.session.get(Analysis, analysis_id)
    if analysis is None:
        abort(404)
    if analysis.user_id != current_user.id:
        abort(403)

    vision_record = analysis.vision_assessment
    vision_assessment = json.loads(vision_record.assessment_json) if vision_record and vision_record.assessment_json else None
    if vision_assessment:
        # Older saved assessments included an unreliable model-generated plant label.
        # Keep those rows intact, but do not expose that stale label to the page or Care AI.
        vision_assessment.pop("plant_identification", None)
        vision_assessment.pop("species_confidence", None)
    ai_observed_concern = get_ai_observed_concern(vision_assessment)
    vision_error = vision_record.error_reason if vision_record else None

    if request.method == "POST":
        try:
            symptoms = validate_form(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("analysis.result", analysis_id=analysis.id))
        context = {
            "plant_name": analysis.plant.name, "species": analysis.plant.species,
            "variety": analysis.plant.variety, "health_score": analysis.health_score,
            "leaf_coverage": analysis.leaf_coverage, "yellowing": analysis.yellowing,
            "damage": analysis.damage, "dark_spots": analysis.dark_spots,
            "affected_area": analysis.affected_area,
            "vision_assessment": vision_assessment,
        }
        recommendation, provider, error = generate_care(context, symptoms, current_app.config)
        if error and isinstance(recommendation, dict):
            recommendation = dict(recommendation)
            recommendation["_fallback_reason"] = error
        if error:
            current_app.logger.warning("Care Assistant submission result: provider=%s outcome=fallback reason=%s", provider, error)
        else:
            current_app.logger.info("Care Assistant submission result: provider=%s outcome=success", provider)
        saved = CareRecommendation(
            analysis_id=analysis.id, user_id=current_user.id,
            symptoms_json=json.dumps(symptoms), recommendation_json=json.dumps(recommendation), provider=provider,
        )
        db.session.add(saved)
        db.session.commit()
        flash(error or "Care recommendations updated.", "warning" if error else "success")
        return redirect(url_for("analysis.result", analysis_id=analysis.id))

    score_components = compute_health_score({
        "leaf_coverage": analysis.leaf_coverage,
        "yellowing": analysis.yellowing,
        "damage": analysis.damage,
        "dark_spots": analysis.dark_spots,
    }) if analysis.health_score is not None else {
        "label": "Not calculated (no foliage segmented)",
        "components": {"leaf_vitality": None, "color_health": None,
                       "damage_condition": None, "spot_condition": None},
    }

    care_recommendation = analysis.care_recommendations.first()
    care_symptoms = json.loads(care_recommendation.symptoms_json) if care_recommendation else {}
    care_content = json.loads(care_recommendation.recommendation_json) if care_recommendation else None
    care_error = care_content.get("_fallback_reason") if isinstance(care_content, dict) else None
    return render_template(
        "analysis/result.html",
        analysis=analysis,
        score=score_components,
        vision_assessment=vision_assessment,
        ai_observed_concern=ai_observed_concern,
        vision_error=vision_error,
        care_recommendation=care_recommendation,
        care_symptoms=care_symptoms,
        care_content=care_content,
        care_error=care_error,
    )
