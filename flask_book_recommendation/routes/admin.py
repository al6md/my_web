from flask import Blueprint, render_template, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from ..ai_client import ai_client

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.before_request
@login_required
def require_admin():
    # Simplest check: assume user ID 1 is admin or check email
    # TODO: Add real role check
    if current_user.id != 1 and current_user.email != "admin@example.com":
        return "Access Denied", 403

@admin_bp.route("/dashboard")
def dashboard():
    health = ai_client.get_health()
    stats = ai_client.get_stats()
    
    return render_template("admin_dashboard.html", health=health, stats=stats)

@admin_bp.route("/trigger-index", methods=["POST"])
def trigger_index():
    res = ai_client.trigger_index_rebuild()
    flash(f"Index rebuild triggered: {res.get('status')}", "info")
    return redirect(url_for("admin.dashboard"))
