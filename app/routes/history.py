from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Analysis, Plant

history_bp = Blueprint("history", __name__, url_prefix="/history")

PER_PAGE = 10


@history_bp.route("/")
@login_required
def history_view():
    plants = current_user.plants.order_by(Plant.name).all()

    plant_id = request.args.get("plant_id", type=int)
    q = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)

    query = Analysis.query.filter_by(user_id=current_user.id)
    if plant_id:
        query = query.filter(Analysis.plant_id == plant_id)
    if q:
        query = query.join(Plant).filter(Plant.name.ilike(f"%{q}%"))

    if sort == "oldest":
        query = query.order_by(Analysis.created_at.asc())
    elif sort == "highest":
        query = query.order_by(Analysis.health_score.desc())
    elif sort == "lowest":
        query = query.order_by(Analysis.health_score.asc())
    else:
        query = query.order_by(Analysis.created_at.desc())

    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)

    return render_template(
        "history/history.html",
        plants=plants,
        analyses=pagination.items,
        pagination=pagination,
        filters={"plant_id": plant_id, "q": q, "sort": sort},
    )


@history_bp.route("/<int:analysis_id>/delete", methods=["POST"])
@login_required
def delete_analysis(analysis_id):
    analysis = db.session.get(Analysis, analysis_id)
    if analysis is None:
        abort(404)
    if analysis.user_id != current_user.id:
        abort(403)

    plant_name = analysis.plant.name
    db.session.delete(analysis)
    db.session.commit()
    current_app.logger.info("Analysis deleted: id=%s", analysis_id)
    flash(f'Analysis for "{plant_name}" was deleted.', "success")
    return redirect(request.referrer or url_for("history.history_view"))
