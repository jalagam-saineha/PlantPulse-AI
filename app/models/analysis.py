from app.extensions import db
from app.models.user import utcnow


class Analysis(db.Model):
    """
    A single leaf-image analysis: source image, computer-vision measurements,
    optional AI disease screening, and the derived visual health score.
    """
    __tablename__ = "analyses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False, index=True)

    original_image = db.Column(db.String(255), nullable=False)   # uploads/images/<file>
    processed_image = db.Column(db.String(255), nullable=True)   # results/processed/<file>
    overlay_image = db.Column(db.String(255), nullable=True)     # results/processed/<file> (health map)

    status = db.Column(db.String(20), nullable=False, default="completed")  # completed | failed

    # --- Computer-vision measurements (percentages, 0-100 unless noted) ---
    leaf_coverage = db.Column(db.Float, nullable=True)
    yellowing = db.Column(db.Float, nullable=True)
    damage = db.Column(db.Float, nullable=True)
    dark_spots = db.Column(db.Float, nullable=True)
    affected_area = db.Column(db.Float, nullable=True)
    leaf_area_px = db.Column(db.Integer, nullable=True)  # measured foliage area in pixels

    # --- Derived visual health score ---
    health_score = db.Column(db.Float, nullable=True)  # 0-100

    # --- AI disease screening (nullable when no model installed) ---
    ai_prediction = db.Column(db.String(120), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)  # 0-100
    ai_alternatives_json = db.Column(db.Text, nullable=True)  # JSON list of {label, confidence}
    ai_model_name = db.Column(db.String(120), nullable=True)

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    reports = db.relationship(
        "Report", backref="analysis", lazy="dynamic", cascade="all, delete-orphan"
    )
    care_recommendations = db.relationship(
        "CareRecommendation", backref="analysis", lazy="dynamic", cascade="all, delete-orphan",
        order_by="CareRecommendation.created_at.desc()",
    )
    vision_assessment = db.relationship(
        "PlantVisionAssessment", back_populates="analysis", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Analysis id={self.id} plant={self.plant_id} score={self.health_score}>"
