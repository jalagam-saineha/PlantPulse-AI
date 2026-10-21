from flask import Blueprint, render_template, current_app
from flask_login import login_required

from app.services.system_status import get_full_status

system_bp = Blueprint("system", __name__, url_prefix="/system-status")


@system_bp.route("/")
@login_required
def system_status_view():
    status = get_full_status(current_app._get_current_object())
    return render_template("system/status.html", status=status)
