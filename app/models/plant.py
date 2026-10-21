from app.extensions import db
from app.models.user import utcnow


class Plant(db.Model):
    __tablename__ = "plants"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    name = db.Column(db.String(120), nullable=False)
    species = db.Column(db.String(120), nullable=True)
    variety = db.Column(db.String(120), nullable=True)
    planting_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)  # relative path under uploads/plants

    is_archived = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships (populated starting in later phases)
    analyses = db.relationship(
        "Analysis", backref="plant", lazy="dynamic",
        cascade="all, delete-orphan", order_by="Analysis.created_at.desc()",
    )
    video_analyses = db.relationship(
        "VideoAnalysis", backref="plant", lazy="dynamic",
        cascade="all, delete-orphan", order_by="VideoAnalysis.created_at.desc()",
    )
    timeline_events = db.relationship(
        "TimelineEvent", backref="plant", lazy="dynamic",
        cascade="all, delete-orphan", order_by="TimelineEvent.event_date.desc()",
    )

    @property
    def latest_analysis(self):
        return self.analyses.first()

    def __repr__(self):
        return f"<Plant {self.name!r} user={self.user_id}>"
