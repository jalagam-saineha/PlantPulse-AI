"""
Import every model here so that a single `from app import models` (done in
the app factory) registers all tables with SQLAlchemy's metadata before
db.create_all() runs.
"""
from app.models.user import User
from app.models.reset_token import PasswordResetToken
from app.models.plant import Plant
from app.models.analysis import Analysis
from app.models.care_recommendation import CareRecommendation
from app.models.plant_vision_assessment import PlantVisionAssessment
from app.models.video_analysis import VideoAnalysis, VideoFrame
from app.models.timeline import TimelineEvent, Report, Notification

__all__ = [
    "User",
    "PasswordResetToken",
    "Plant",
    "Analysis",
    "CareRecommendation",
    "PlantVisionAssessment",
    "VideoAnalysis",
    "VideoFrame",
    "TimelineEvent",
    "Report",
    "Notification",
]
