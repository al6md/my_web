from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Genre, UserGenre

prefs_bp = Blueprint("prefs", __name__, url_prefix="/prefs")

@prefs_bp.route("/preferences", methods=["GET","POST"])
@login_required
def form():
    genres = Genre.query.order_by(Genre.name.asc()).all()
    if request.method == "POST":
        UserGenre.query.filter_by(user_id=current_user.id).delete()
        for gid in request.form.getlist("genres"):
            db.session.add(UserGenre(user_id=current_user.id, genre_id=int(gid)))
        db.session.commit()
        return redirect(url_for("main.books"))
    chosen = {x.genre_id for x in UserGenre.query.filter_by(user_id=current_user.id).all()}
    return render_template("preferences.html", genres=genres, chosen=chosen)
