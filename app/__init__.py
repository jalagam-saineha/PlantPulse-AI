"""
PlantPulse AI - Application Factory
"""
import logging
from pathlib import Path

from flask import Flask

from config import Config
from app.extensions import db, login_manager, csrf


def create_app(config_class: type = Config) -> Flask:
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_object(config_class)

    _configure_logging(app)
    app.logger.info(
        "Care Assistant config active: provider=%s model=%s key_present=%s",
        app.config.get("CARE_AI_PROVIDER", "openai"),
        app.config.get("CARE_AI_GEMINI_MODEL") if app.config.get("CARE_AI_PROVIDER") == "gemini" else app.config.get("CARE_AI_MODEL"),
        bool(app.config.get("CARE_AI_GEMINI_API_KEY") if app.config.get("CARE_AI_PROVIDER") == "gemini" else app.config.get("CARE_AI_API_KEY")),
    )
    _ensure_directories(app)

    # --- Extensions ---
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # --- Models must be imported before create_all() ---
    from app import models  # noqa: F401

    with app.app_context():
        db.create_all()
        app.logger.info("Database ready at %s", app.config["SQLALCHEMY_DATABASE_URI"])
        _recover_stale_jobs(app)

    # --- User loader ---
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Blueprints ---
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.plants import plants_bp
    from app.routes.analysis import analysis_bp
    from app.routes.growth import growth_bp
    from app.routes.timeline import timeline_bp
    from app.routes.history import history_bp
    from app.routes.compare import compare_bp
    from app.routes.disease import disease_bp
    from app.routes.insights import insights_bp
    from app.routes.notifications import notifications_bp
    from app.routes.reports import reports_bp
    from app.routes.help import help_bp
    from app.routes.search import search_bp
    from app.routes.settings import settings_bp
    from app.routes.system import system_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(plants_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(growth_bp)
    app.register_blueprint(timeline_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(compare_bp)
    app.register_blueprint(disease_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(system_bp)

    # --- Error handlers ---
    _register_error_handlers(app)

    # --- Template context ---
    _register_context_processors(app)

    from app.utils.icons import icon_svg
    from markupsafe import Markup

    app.jinja_env.globals["icon"] = lambda name, size=18: Markup(icon_svg(name, size))

    app.logger.info("PlantPulse AI started in %s mode", app.config["APP_ENV"])
    return app


def _configure_logging(app: Flask) -> None:
    log_dir = Path(app.root_path).parent / "instance"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "plantpulse.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def _ensure_directories(app: Flask) -> None:
    dirs = [
        app.config["INSTANCE_DIR"],
        app.config["UPLOAD_IMAGES_DIR"],
        app.config["UPLOAD_VIDEOS_DIR"],
        app.config["UPLOAD_PLANTS_DIR"],
        app.config["RESULTS_PROCESSED_DIR"],
        app.config["RESULTS_FRAMES_DIR"],
        app.config["REPORTS_DIR"],
        app.config["MODELS_DIR"],
        app.config["DATA_DIR"],
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


def _register_error_handlers(app: Flask) -> None:
    from flask import render_template

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error: %s", e)
        return render_template("errors/500.html"), 500

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/413.html"), 413


def _register_context_processors(app: Flask) -> None:
    from flask_login import current_user

    @app.context_processor
    def inject_globals():
        return {
            "app_name": "PlantPulse AI",
            "app_tagline": "Visual Plant Health & Growth Intelligence",
            "current_user": current_user,
        }


def _recover_stale_jobs(app: Flask) -> None:
    """
    If the process was killed mid-processing (crash, forced restart) a
    VideoAnalysis row can be left stuck at QUEUED/PROCESSING forever,
    which would incorrectly block all future growth scans as "busy".
    On every startup, any such row is marked FAILED with an honest
    explanation, since no thread from a previous process is still running.
    """
    from app.models import VideoAnalysis

    stale = VideoAnalysis.query.filter(
        VideoAnalysis.status.in_(["QUEUED", "PROCESSING"])
    ).all()
    for video in stale:
        video.status = "FAILED"
        video.error_message = "Processing was interrupted by an application restart."
    if stale:
        db.session.commit()
        app.logger.warning("Recovered %d stale growth-scan job(s) on startup", len(stale))
