from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.models import Plant, Analysis, Report, TimelineEvent

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/")
@login_required
def search_view():
    q = (request.args.get("q") or "").strip()
    results = {"plants": [], "analyses": [], "reports": [], "timeline": []}

    if q:
        like = f"%{q}%"

        results["plants"] = (
            current_user.plants.filter(
                Plant.name.ilike(like) | Plant.species.ilike(like)
            ).limit(10).all()
        )

        plant_ids = [p.id for p in current_user.plants]
        results["analyses"] = (
            Analysis.query.filter(
                Analysis.user_id == current_user.id,
                Analysis.plant_id.in_(plant_ids or [-1]),
            )
            .join(Plant)
            .filter(Plant.name.ilike(like))
            .order_by(Analysis.created_at.desc())
            .limit(10)
            .all()
        )

        results["reports"] = (
            Report.query.filter_by(user_id=current_user.id)
            .filter(Report.title.ilike(like))
            .order_by(Report.created_at.desc())
            .limit(10)
            .all()
        )

        results["timeline"] = (
            TimelineEvent.query.filter(TimelineEvent.plant_id.in_(plant_ids or [-1]))
            .join(Plant, Plant.id == TimelineEvent.plant_id)
            .filter(Plant.name.ilike(like))
            .order_by(TimelineEvent.event_date.desc())
            .limit(10)
            .all()
        )

    total = sum(len(v) for v in results.values())
    return render_template("search/search.html", q=q, results=results, total=total)
