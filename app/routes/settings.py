import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User
from app.services.system_status import get_full_status

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@settings_bp.route("/")
@login_required
def settings_view():
    status = get_full_status(current_app._get_current_object())
    return render_template("settings/settings.html", status=status)


@settings_bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()

    if len(name) < 2:
        flash("Please enter your full name.", "error")
        return redirect(url_for("settings.settings_view"))
    if not EMAIL_RE.match(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("settings.settings_view"))

    existing = User.query.filter(User.email == email, User.id != current_user.id).first()
    if existing:
        flash("That email is already in use by another account.", "error")
        return redirect(url_for("settings.settings_view"))

    current_user.name = name
    current_user.email = email
    db.session.commit()
    current_app.logger.info("Profile updated for user %s", current_user.id)
    flash("Profile updated.", "success")
    return redirect(url_for("settings.settings_view"))


@settings_bp.route("/password", methods=["POST"])
@login_required
def update_password():
    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("settings.settings_view"))
    if len(new_password) < 8:
        flash("New password must be at least 8 characters long.", "error")
        return redirect(url_for("settings.settings_view"))
    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(url_for("settings.settings_view"))

    current_user.set_password(new_password)
    db.session.commit()
    current_app.logger.info("Password changed for user %s", current_user.id)
    flash("Password updated.", "success")
    return redirect(url_for("settings.settings_view"))


@settings_bp.route("/notifications", methods=["POST"])
@login_required
def update_notifications():
    current_user.notifications_enabled = bool(request.form.get("notifications_enabled"))
    db.session.commit()
    flash("Notification preferences updated.", "success")
    return redirect(url_for("settings.settings_view"))
