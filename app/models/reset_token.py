import secrets
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.user import utcnow


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(128), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def generate(user_id: int, max_age_seconds: int = 3600) -> "PasswordResetToken":
        token = secrets.token_urlsafe(32)
        return PasswordResetToken(
            user_id=user_id,
            token=token,
            expires_at=utcnow() + timedelta(seconds=max_age_seconds),
        )

    @property
    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return utcnow() < expires

    def mark_used(self) -> None:
        self.used_at = utcnow()

    def __repr__(self):
        return f"<PasswordResetToken user={self.user_id} valid={self.is_valid}>"
