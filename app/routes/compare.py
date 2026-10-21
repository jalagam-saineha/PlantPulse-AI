from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Plant, Analysis

compare_bp = Blueprint("compare", __name__, url_prefix="/compare")

_METRICS = [
    ("health_score", "Health Score", ""),
    ("leaf_coverage", "Leaf Coverage", "%"),
    ("yellowing", "Yellowing", "%"),
    ("damage", "Visible Damage", "%"),
    ("dark_spots", "Dark Spots", "%"),
    ("affected_area", "Affected Area", "%"),
]


def _owned_analysis(analysis_id):
    if not analysis_id:
        return None
    a = db.session.get(Analysis, analysis_id)
    if a is None or a.user_id != current_user.id:
        return None
    return a


@compare_bp.route("/")
@login_required
def compare_view():
    plants = current_user.plants.order_by(Plant.name).all()
    plant_id = request.args.get("plant_id", type=int)

    plant_analyses = []
    if plant_id:
        plant_analyses = (
            Analysis.query.filter_by(user_id=current_user.id, plant_id=plant_id)
            .order_by(Analysis.created_at.desc())
            .all()
        )

    a_id = request.args.get("a", type=int)
    b_id = request.args.get("b", type=int)
    analysis_a = _owned_analysis(a_id)
    analysis_b = _owned_analysis(b_id)

    rows = None
    if analysis_a and analysis_b:
        if analysis_a.created_at > analysis_b.created_at:
            analysis_a, analysis_b = analysis_b, analysis_a

        rows = []
        for field, label, unit in _METRICS:
            before = getattr(analysis_a, field)
            after = getattr(analysis_b, field)
            if before is None or after is None:
                rows.append({"label": label, "unit": unit, "before": before, "after": after,
                             "delta": None, "pct_change": None})
                continue
            delta = round(after - before, 2)
            pct_change = round((delta / before) * 100, 1) if before != 0 else None
            rows.append({
                "label": label, "unit": unit, "before": before, "after": after,
                "delta": delta, "pct_change": pct_change,
            })

    return render_template(
        "compare/compare.html",
        plants=plants,
        plant_id=plant_id,
        plant_analyses=plant_analyses,
        analysis_a=analysis_a,
        analysis_b=analysis_b,
        rows=rows,
        a_id=a_id,
        b_id=b_id,
    )
