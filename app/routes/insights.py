from datetime import timedelta

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Plant, Analysis, user as user_module

insights_bp = Blueprint("insights", __name__, url_prefix="/insights")

WINDOW_DAYS = 14
MIN_CHANGE_PCT = 3.0  # ignore noise smaller than this


def _generate_insights_for_plant(plant: Plant) -> list:
    cutoff = user_module.utcnow() - timedelta(days=WINDOW_DAYS)
    analyses = (
        Analysis.query.filter(Analysis.plant_id == plant.id, Analysis.created_at >= cutoff)
        .order_by(Analysis.created_at.asc())
        .all()
    )
    if len(analyses) < 2:
        return []

    first, last = analyses[0], analyses[-1]
    days = max(1, (last.created_at - first.created_at).days)
    insights = []

    def compare(field, label, higher_is_better=True):
        before, after = getattr(first, field), getattr(last, field)
        if before is None or after is None:
            return
        delta = after - before
        if abs(delta) < MIN_CHANGE_PCT:
            return
        direction = "increased" if delta > 0 else "decreased"
        good = (delta > 0) == higher_is_better
        insights.append({
            "text": f'{label} for "{plant.name}" {direction} from {before:.1f}% to {after:.1f}% over the last {days} day(s).',
            "positive": good,
        })

    compare("leaf_coverage", "Leaf coverage", higher_is_better=True)
    compare("yellowing", "Yellowing", higher_is_better=False)
    compare("damage", "Visible damage", higher_is_better=False)
    compare("dark_spots", "Dark-spot presence", higher_is_better=False)

    if len(analyses) >= 3:
        recent_scores = [a.health_score for a in analyses[-3:] if a.health_score is not None]
        if len(recent_scores) == 3 and recent_scores[0] < recent_scores[1] < recent_scores[2]:
            insights.append({
                "text": f'Visual health score for "{plant.name}" has improved across the last three analyses.',
                "positive": True,
            })
        elif len(recent_scores) == 3 and recent_scores[0] > recent_scores[1] > recent_scores[2]:
            insights.append({
                "text": f'Visual health score for "{plant.name}" has declined across the last three analyses.',
                "positive": False,
            })

    return insights


@insights_bp.route("/")
@login_required
def insights_view():
    plants = current_user.plants.filter_by(is_archived=False).all()
    all_insights = []
    for plant in plants:
        all_insights.extend(_generate_insights_for_plant(plant))

    return render_template("insights/insights.html", insights=all_insights, window_days=WINDOW_DAYS)
