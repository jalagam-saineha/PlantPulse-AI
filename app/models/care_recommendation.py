from app.extensions import db
from app.models.user import utcnow


class CareRecommendation(db.Model):
    __tablename__ = "care_recommendations"

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analyses.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    symptoms_json = db.Column(db.Text, nullable=False)
    recommendation_json = db.Column(db.Text, nullable=False)
    provider = db.Column(db.String(40), nullable=False, default="basic-care")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
