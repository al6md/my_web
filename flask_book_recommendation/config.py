import os
from dotenv import load_dotenv

# تحميل ملف .env من نفس المجلد
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-fallback-key"

    # إذا موجود DB_URL في env نستخدمه كما هو (مثلاً MySQL في السيرفر)
    db_url = os.environ.get("DB_URL")
    if db_url:
        SQLALCHEMY_DATABASE_URI = db_url
    else:
        # SQLite محلي لتسهيل التطوير
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "app.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # إعدادات Caching
    CACHE_TYPE = "SimpleCache"  # للبيئة المحلية، استخدم Redis في الإنتاج
    CACHE_DEFAULT_TIMEOUT = 300  # 5 دقائق
    
    # إعدادات CSRF و Session
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # إعدادات Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.path.join(BASE_DIR, "app.log")