import uuid

from flask import (
    Blueprint, render_template, redirect, url_for, flash, current_app,
    abort, send_file, request
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Analysis, Report
from app.services.report_generator import generate_report_pdf

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@login_required
def reports_view():
    reports = (
        Report.query.filter_by(user_id=current_user.id)
        .order_by(Report.created_at.desc())
        .all()
    )
    return render_template("reports/reports.html", reports=reports)


@reports_bp.route("/generate/<int:analysis_id>", methods=["POST"])
@login_required
def generate(analysis_id):
    analysis = db.session.get(Analysis, analysis_id)
    if analysis is None:
        abort(404)
    if analysis.user_id != current_user.id:
        abort(403)

    plant = analysis.plant

    previous_analysis = (
        Analysis.query.filter(
            Analysis.plant_id == plant.id, Analysis.created_at < analysis.created_at
        )
        .order_by(Analysis.created_at.desc())
        .first()
    )

    media_paths = {
        "original": current_app.config["UPLOAD_IMAGES_DIR"] / analysis.original_image,
        "processed": (
            current_app.config["RESULTS_PROCESSED_DIR"] / analysis.processed_image
            if analysis.processed_image else None
        ),
        "overlay": (
            current_app.config["RESULTS_PROCESSED_DIR"] / analysis.overlay_image
            if analysis.overlay_image else None
        ),
    }

    reports_dir = current_app.config["REPORTS_DIR"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.pdf"
    output_path = reports_dir / filename

    try:
        generate_report_pdf(analysis, plant, output_path, media_paths, previous_analysis)
    except Exception as exc:
        current_app.logger.error("Report generation failed for analysis %s: %s", analysis_id, exc)
        flash("Report generation failed. Please try again.", "error")
        return redirect(url_for("analysis.result", analysis_id=analysis_id))

    report = Report(
        user_id=current_user.id,
        plant_id=plant.id,
        analysis_id=analysis.id,
        file_path=filename,
        title=f"PlantPulse AI Report — {plant.name}",
    )
    db.session.add(report)
    db.session.commit()

    current_app.logger.info("Report generated: id=%s analysis=%s", report.id, analysis_id)
    flash("Report generated.", "success")
    return redirect(url_for("reports.reports_view"))


def _owned_report_or_404(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        abort(404)
    if report.user_id != current_user.id:
        abort(403)
    return report


@reports_bp.route("/<int:report_id>")
@login_required
def view_report(report_id):
    report = _owned_report_or_404(report_id)
    path = current_app.config["REPORTS_DIR"] / report.file_path
    if not path.exists():
        abort(404)
    return send_file(str(path), mimetype="application/pdf")


@reports_bp.route("/<int:report_id>/download")
@login_required
def download_report(report_id):
    report = _owned_report_or_404(report_id)
    path = current_app.config["REPORTS_DIR"] / report.file_path
    if not path.exists():
        abort(404)
    safe_name = f"PlantPulse_Report_{report.plant.name.replace(' ', '_')}_{report.id}.pdf"
    return send_file(str(path), mimetype="application/pdf", as_attachment=True, download_name=safe_name)


@reports_bp.route("/<int:report_id>/delete", methods=["POST"])
@login_required
def delete_report(report_id):
    report = _owned_report_or_404(report_id)
    path = current_app.config["REPORTS_DIR"] / report.file_path
    if path.exists():
        path.unlink()
    db.session.delete(report)
    db.session.commit()
    flash("Report deleted.", "success")
    return redirect(url_for("reports.reports_view"))
