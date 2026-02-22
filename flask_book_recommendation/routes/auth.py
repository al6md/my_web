import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from ..extensions import db, csrf, cache
from ..models import User, UserPreference

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        
        # مسح الكاش لضمان بيانات جديدة لهذا المستخدم
        try:
            cache.clear()
        except Exception:
            pass
        
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
        
        # مسح الكاش لتفعيل الاهتمامات الجديدة فوراً
        try:
            cache.clear()
        except Exception:
            pass
        
        flash("مرحباً! تم حفظ اهتماماتك بنجاح 🎉", "success")
        return redirect(url_for("explore.index"))
    
    return render_template("onboarding.html")

# تسجيل خروج
@auth_bp.route("/logout")
@login_required
def logout():
    # مسح الكاش قبل تسجيل الخروج لمنع تسرب البيانات
    try:
        cache.clear()
    except Exception:
        pass
    # مسح كاش pipeline العصبي للمستخدم الحالي
    try:
        from ai_book_recommender.unified_pipeline import get_unified_engine
        engine = get_unified_engine()
        engine.clear_user_cache(current_user.id)
    except Exception:
        pass
    logout_user()
    return redirect(url_for("auth.login"))

# صفحة الملف الشخصي
@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        
        # معالجة صورة الملف الشخصي
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename and allowed_file(file.filename):
                # إنشاء اسم فريد للملف
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
                
                # مسار الحفظ
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
                os.makedirs(upload_folder, exist_ok=True)
                
                # حذف الصورة القديمة إن وجدت
                if current_user.profile_picture:
                    old_path = os.path.join(current_app.root_path, 'static', current_user.profile_picture.lstrip('/static/'))
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except:
                            pass
                
                # حفظ الصورة الجديدة
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                current_user.profile_picture = f"/static/uploads/profiles/{filename}"
        
        # تحديث الاسم
        if name and name != current_user.name:
            current_user.name = name
        
        # تحديث البريد الإلكتروني
        if email and email != current_user.email:
            # تحقق من عدم وجود البريد لمستخدم آخر
            existing = User.query.filter_by(email=email).first()
            if existing and existing.id != current_user.id:
                flash("هذا البريد الإلكتروني مستخدم بالفعل", "error")
                return redirect(url_for("auth.profile"))
            current_user.email = email
        
        # تغيير كلمة المرور
        if new_password:
            if not current_password:
                flash("أدخل كلمة المرور الحالية", "error")
                return redirect(url_for("auth.profile"))
            
            if not check_password_hash(current_user.password_hash, current_password):
                flash("كلمة المرور الحالية غير صحيحة", "error")
                return redirect(url_for("auth.profile"))
            
            current_user.password_hash = generate_password_hash(new_password)
        
        db.session.commit()
        flash("تم تحديث معلومات الحساب بنجاح ✅", "success")
        return redirect(url_for("auth.profile"))
    
    # جلب اهتمامات المستخدم
    interests = UserPreference.query.filter_by(user_id=current_user.id).all()
    
    return render_template("profile.html", interests=interests)

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

