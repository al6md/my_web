from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db, csrf
from ..models import User, UserPreference

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# صفحة تسجيل الدخول
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Email not found", "error")
            return redirect(url_for("auth.login"))

        try:
            ok = check_password_hash(user.password_hash, password)
        except Exception:
            flash("Stored password invalid format. Recreate user.", "error")
            return redirect(url_for("auth.login"))

        if not ok:
            flash("Wrong password", "error")
            return redirect(url_for("auth.login"))

        login_user(user)
        
        # إذا لم يكمل الـ onboarding، وجهه لصفحة الاهتمامات
        if not user.onboarding_completed:
            return redirect(url_for("auth.onboarding"))
        
        return redirect(url_for("explore.index"))

    return render_template("login.html")

# صفحة إنشاء الحساب
@auth_bp.route("/register", methods=["GET", "POST"])
@csrf.exempt  # استثناء مؤقت لحل مشكلة التسجيل
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not name or not email or not password:
            flash("All fields are required", "error")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "error")
            return redirect(url_for("auth.register"))

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            onboarding_completed=False
        )
        db.session.add(user)
        db.session.commit()
        
        # تسجيل دخول تلقائي وتوجيه لصفحة الاهتمامات
        login_user(user)
        return redirect(url_for("auth.onboarding"))

    return render_template("register.html")

# صفحة اختيار الاهتمامات (Onboarding)
@auth_bp.route("/onboarding", methods=["GET", "POST"])
@csrf.exempt  # استثناء من CSRF لأن المستخدم مسجل دخول بالفعل
@login_required
def onboarding():
    # إذا أكمل الـ onboarding، وجهه للصفحة الرئيسية
    if current_user.onboarding_completed:
        return redirect(url_for("explore.index"))
    
    if request.method == "POST":
        interests = request.form.getlist("interests")
        
        if len(interests) < 3:
            flash("يرجى اختيار 3 اهتمامات على الأقل", "error")
            return redirect(url_for("auth.onboarding"))
        
        # حفظ الاهتمامات في UserPreference
        for interest in interests:
            # تحقق من عدم التكرار
            existing = UserPreference.query.filter_by(
                user_id=current_user.id,
                topic=interest
            ).first()
            
            if not existing:
                pref = UserPreference(
                    user_id=current_user.id,
                    topic=interest,
                    weight=100.0  # وزن عالي للاهتمامات المختارة
                )
                db.session.add(pref)
        
        # تحديث حالة الـ onboarding
        current_user.onboarding_completed = True
        db.session.commit()
        
        flash("مرحباً! تم حفظ اهتماماتك بنجاح 🎉", "success")
        return redirect(url_for("explore.index"))
    
    return render_template("onboarding.html")

# تسجيل خروج
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

# مستخدم تجريبي جاهز للاختبار
@auth_bp.route("/seed/demo")
def seed_demo_user():
    if not User.query.filter_by(email="admin@example.com").first():
        u = User(
            name="Admin",
            email="admin@example.com",
            password_hash=generate_password_hash("1234"),
            onboarding_completed=True
        )
        db.session.add(u)
        db.session.commit()
    return "User: admin@example.com / 1234"
