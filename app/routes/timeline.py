from datetime import datetime

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Plant, TimelineEvent, Analysis

timeline_bp = Blueprint("timeline", __name__, url_prefix="/timeline")


def _health_bucket(score):
    if score is None:
        return None
    if score >= 70:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


@timeline_bp.route("/")
@login_required
def timeline_view():
    plants = current_user.plants.order_by(Plant.name).all()
    plant_ids = [p.id for p in plants]

    plant_id = request.args.get("plant_id", type=int)
    source_type = request.args.get("type")  # 'analysis' | 'video_frame'
    health = request.args.get("health")  # 'good' | 'fair' | 'poor'
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    query = TimelineEvent.query.filter(TimelineEvent.plant_id.in_(plant_ids or [-1]))

    if plant_id:
        query = query.filter(TimelineEvent.plant_id == plant_id)
    if source_type in ("analysis", "video_frame"):
        query = query.filter(TimelineEvent.source_type == source_type)
    if date_from:
        try:
            query = query.filter(TimelineEvent.event_date >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(TimelineEvent.event_date <= datetime.strptime(date_to, "%Y-%m-%d"))
        except ValueError:
            pass

    events = query.order_by(TimelineEvent.event_date.desc()).limit(100).all()

    if health in ("good", "fair", "poor"):
        events = [e for e in events if _health_bucket(e.health_score) == health]

    # Attach AI info for analysis-sourced events, and the owning plant.
    plants_by_id = {p.id: p for p in plants}
    analysis_ids = [e.source_id for e in events if e.source_type == "analysis"]
    analyses_by_id = {}
    if analysis_ids:
        for a in Analysis.query.filter(Analysis.id.in_(analysis_ids)).all():
            analyses_by_id[a.id] = a

    enriched = []
    for e in events:
        enriched.append({
            "event": e,
            "plant": plants_by_id.get(e.plant_id),
            "analysis": analyses_by_id.get(e.source_id) if e.source_type == "analysis" else None,
            "media_category": "processed" if e.source_type == "analysis" else "frames",
        })

    return render_template(
        "timeline/timeline.html",
        plants=plants,
        events=enriched,
        filters={
            "plant_id": plant_id, "type": source_type, "health": health,
            "from": date_from or "", "to": date_to or "",
        },
    )
