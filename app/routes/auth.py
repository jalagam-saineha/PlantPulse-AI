import re

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, current_app
)
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models import User, PasswordResetToken

auth_bp = Blueprint("auth", __name__, url_prefix="")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        errors = []
        if len(name) < 2:
            errors.append("Please enter your full name.")
        if not _valid_email(email):
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not errors and User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html", name=name, email=email), 400

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        current_app.logger.info("New user registered: %s", email)
        flash("Account created. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            current_app.logger.info("User logged in: %s", email)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("main.dashboard"))

        current_app.logger.info("Failed login attempt for: %s", email)
        flash("Incorrect email or password.", "error")
        return render_template("auth/login.html", email=email), 401

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    current_app.logger.info("User logged out: %s", current_user.email)
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    reset_url = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first()

        # Always show the same generic confirmation, whether or not the
        # account exists, so the form can't be used to enumerate users.
        if user:
            token = PasswordResetToken.generate(
                user.id, current_app.config["RESET_TOKEN_MAX_AGE_SECONDS"]
            )
            db.session.add(token)
            db.session.commit()

            reset_url = url_for("auth.reset_password", token=token.token, _external=True)

            if current_app.config["MAIL_ENABLED"]:
                _send_reset_email(user, reset_url)
                current_app.logger.info("Password reset email sent to %s", email)
            else:
                # Development-friendly fallback: print to the terminal log
                # and (only outside production) display it on screen.
                current_app.logger.info("Password reset link for %s: %s", email, reset_url)
                print(f"[PlantPulse AI] Password reset link for {email}: {reset_url}")

        flash(
            "If an account exists for that email, a password reset link has been generated.",
            "success",
        )

        show_dev_link = (
            current_app.config["APP_ENV"] != "production"
            and not current_app.config["MAIL_ENABLED"]
            and reset_url is not None
        )

        return render_template(
            "auth/forgot_password.html",
            reset_url=reset_url if show_dev_link else None,
            submitted=True,
        )

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    reset_token = PasswordResetToken.query.filter_by(token=token).first()

    if not reset_token or not reset_token.is_valid:
        flash("This password reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("auth/reset_password.html", token=token), 400
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token), 400

        user = db.session.get(User, reset_token.user_id)
        user.set_password(password)
        reset_token.mark_used()
        db.session.commit()

        current_app.logger.info("Password reset completed for %s", user.email)
        flash("Your password has been updated. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


def _send_reset_email(user: User, reset_url: str) -> None:
    """Best-effort SMTP send using the standard library, gated by MAIL_ENABLED."""
    import smtplib
    from email.mime.text import MIMEText

    cfg = current_app.config
    body = (
        f"Hello {user.name},\n\n"
        f"A password reset was requested for your PlantPulse AI account.\n"
        f"Reset your password using the link below (valid for a limited time):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, you can safely ignore this email."
    )
    msg = MIMEText(body)
    msg["Subject"] = "Reset your PlantPulse AI password"
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = user.email

    try:
        with smtplib.SMTP(cfg["MAIL_HOST"], cfg["MAIL_PORT"], timeout=10) as server:
            if cfg["MAIL_USE_TLS"]:
                server.starttls()
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.sendmail(cfg["MAIL_FROM"], [user.email], msg.as_string())
    except Exception as exc:  # pragma: no cover - best effort, logged only
        current_app.logger.error("Failed to send reset email to %s: %s", user.email, exc)
