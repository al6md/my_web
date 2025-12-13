# app/__init__.py أو flask_book_recommendation/__init__.py
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, redirect, url_for, jsonify, request
from flask_cors import CORS
from .config import Config
from .extensions import db, login_manager, migrate, csrf, cache, jwt
from .models import User
from .routes.main import main_bp
from .routes.auth import auth_bp
from .routes.preferences import prefs_bp
from .routes.my_google_books import google_bp
from .routes.explore import explore_bp
from .routes.public import public_bp
from .routes.api import api_bp


def setup_logging(app):
    """إعداد نظام Logging للتطبيق"""
    if not app.debug:
        # إنشاء ملف log مع rotation
        file_handler = RotatingFileHandler(
            app.config['LOG_FILE'],
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(getattr(logging, app.config['LOG_LEVEL']))
        app.logger.addHandler(file_handler)
        app.logger.setLevel(getattr(logging, app.config['LOG_LEVEL']))
        app.logger.info('Application startup')


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # تهيئة Extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    cache.init_app(app)
    jwt.init_app(app)  # JWT للـ API
    
    # تفعيل CORS للـ API فقط (للسماح لـ Flutter بالاتصال)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # إعداد Logging
    setup_logging(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))
    
    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect(url_for("auth.login"))

    # تسجيل المسارات (Blueprints)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(prefs_bp)
    app.register_blueprint(google_bp)
    app.register_blueprint(explore_bp)   # صفحة الاستكشاف
    app.register_blueprint(public_bp)
    
    # تسجيل REST API Blueprint
    app.register_blueprint(api_bp)
    csrf.exempt(api_bp)  # إعفاء API من CSRF (يستخدم JWT بدلاً منه)

    # الصفحة الرئيسية → Explore
    @app.route("/")
    def index():
        return redirect(url_for("explore.index"))

    # فحص سريع لحالة السيرفر
    @app.route("/ping")
    def ping():
        return jsonify(status="ok")

    # معالجة الأخطاء
    @app.errorhandler(404)
    def not_found(e):
        app.logger.warning(f"404 error: {request.url}")
        return "الصفحة غير موجودة، جرّب / أو /explore", 404
    
    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error(f"500 error: {e}", exc_info=True)
        db.session.rollback()
        return "حدث خطأ داخلي. يرجى المحاولة لاحقاً.", 500

    # إنشاء الجداول (فقط في حالة عدم وجود migrations)
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            app.logger.warning(f"Could not create tables (may already exist): {e}")

    return app


# For Gunicorn in production (Render)
# Usage: gunicorn flask_book_recommendation.app:app
app = create_app()
