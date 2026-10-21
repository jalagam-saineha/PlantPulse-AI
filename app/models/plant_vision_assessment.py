from app.extensions import db
from app.models.user import utcnow


class PlantVisionAssessment(db.Model):
    __tablename__ = "plant_vision_assessments"

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analyses.id"), nullable=False, unique=True, index=True)
    provider = db.Column(db.String(32), nullable=False, default="unavailable")
    assessment_json = db.Column(db.Text, nullable=True)
    error_reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    analysis = db.relationship("Analysis", back_populates="vision_assessment")
