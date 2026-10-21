from app.extensions import db
from app.models.user import utcnow


class VideoAnalysis(db.Model):
    """A growth video submitted for frame-by-frame visual analysis."""
    __tablename__ = "video_analyses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False, index=True)

    video_path = db.Column(db.String(255), nullable=False)
    duration_seconds = db.Column(db.Float, nullable=True)
    fps = db.Column(db.Float, nullable=True)
    resolution = db.Column(db.String(30), nullable=True)  # "1920x1080"
    sampling_interval_seconds = db.Column(db.Integer, nullable=False, default=5)

    # QUEUED | PROCESSING | COMPLETED | FAILED
    status = db.Column(db.String(20), nullable=False, default="QUEUED", index=True)
    progress_percent = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    frames = db.relationship(
        "VideoFrame", backref="video_analysis", lazy="dynamic",
        cascade="all, delete-orphan", order_by="VideoFrame.timestamp_seconds.asc()",
    )

    def __repr__(self):
        return f"<VideoAnalysis id={self.id} status={self.status}>"


class VideoFrame(db.Model):
    """A single extracted + analyzed frame from a growth video."""
    __tablename__ = "video_frames"

    id = db.Column(db.Integer, primary_key=True)
    video_analysis_id = db.Column(
        db.Integer, db.ForeignKey("video_analyses.id"), nullable=False, index=True
    )

    timestamp_seconds = db.Column(db.Float, nullable=False)
    frame_path = db.Column(db.String(255), nullable=False)

    leaf_area_px = db.Column(db.Integer, nullable=True)
    green_coverage = db.Column(db.Float, nullable=True)
    yellowing = db.Column(db.Float, nullable=True)
    damage = db.Column(db.Float, nullable=True)
    health_score = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f"<VideoFrame t={self.timestamp_seconds}s>"
