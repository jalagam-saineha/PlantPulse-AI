"""
PlantPulse AI - Application Configuration
Loads settings from environment variables (see .env.example).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def care_ai_settings(environ=None) -> dict:
    """Map project environment names to Flask's server-side Care AI settings."""
    env = os.environ if environ is None else environ
    return {
        "CARE_AI_PROVIDER": env.get("PLANTPULSE_AI_PROVIDER", "openai").strip().lower(),
        "CARE_AI_API_KEY": env.get("PLANTPULSE_AI_API_KEY", ""),
        "CARE_AI_API_URL": env.get("PLANTPULSE_AI_API_URL", "https://api.openai.com/v1/chat/completions"),
        "CARE_AI_MODEL": env.get("PLANTPULSE_AI_MODEL", "gpt-4o-mini"),
        "CARE_AI_GEMINI_API_KEY": env.get("PLANTPULSE_GEMINI_API_KEY", ""),
        "CARE_AI_GEMINI_MODEL": env.get("PLANTPULSE_GEMINI_MODEL", "gemini-3.5-flash-lite"),
        "CARE_AI_TIMEOUT": float(env.get("PLANTPULSE_AI_TIMEOUT", "12")),
    }


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- Core ---
    APP_ENV = os.getenv("APP_ENV", "development")  # development | production
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-secret-change-me")
    DEBUG = APP_ENV == "development"

    # --- Database ---
    INSTANCE_DIR = BASE_DIR / "instance"
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{(INSTANCE_DIR / 'plantpulse.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15}}

    # --- Uploads ---
    MAX_CONTENT_LENGTH = 160 * 1024 * 1024  # Keep above the 150 MB Growth Studio upload limit
    AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "60"))
    CARE_AI_API_KEY = care_ai_settings()["CARE_AI_API_KEY"]
    CARE_AI_API_URL = care_ai_settings()["CARE_AI_API_URL"]
    CARE_AI_MODEL = care_ai_settings()["CARE_AI_MODEL"]
    CARE_AI_PROVIDER = care_ai_settings()["CARE_AI_PROVIDER"]
    CARE_AI_GEMINI_API_KEY = care_ai_settings()["CARE_AI_GEMINI_API_KEY"]
    CARE_AI_GEMINI_MODEL = care_ai_settings()["CARE_AI_GEMINI_MODEL"]
    CARE_AI_TIMEOUT = care_ai_settings()["CARE_AI_TIMEOUT"]
    UPLOAD_IMAGES_DIR = BASE_DIR / "uploads" / "images"
    UPLOAD_VIDEOS_DIR = BASE_DIR / "uploads" / "videos"
    UPLOAD_PLANTS_DIR = BASE_DIR / "uploads" / "plants"
    RESULTS_PROCESSED_DIR = BASE_DIR / "results" / "processed"
    RESULTS_FRAMES_DIR = BASE_DIR / "results" / "frames"
    REPORTS_DIR = BASE_DIR / "reports"
    MODELS_DIR = BASE_DIR / "models"
    DATA_DIR = BASE_DIR / "data"

    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "webm"}

    # --- Auth / password reset ---
    # In development, the reset link is displayed on screen and printed to the
    # terminal instead of being emailed, so the flow can be demonstrated
    # without configuring SMTP. This must never happen in production.
    RESET_TOKEN_MAX_AGE_SECONDS = 60 * 60  # 1 hour

    # --- Optional SMTP (used only when MAIL_ENABLED=true) ---
    MAIL_ENABLED = _bool_env("MAIL_ENABLED", "false")
    MAIL_HOST = os.getenv("MAIL_HOST", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587") or 587)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@plantpulse.local")
    MAIL_USE_TLS = _bool_env("MAIL_USE_TLS", "true")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


config = Config()
