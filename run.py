from dotenv import load_dotenv
load_dotenv()

import os
import subprocess

# تحديد المسارات
venv_python = os.path.join(os.getcwd(), "venv", "Scripts", "python.exe")

# إعداد متغيرات البيئة
os.environ["FLASK_APP"] = "flask_book_recommendation.app:create_app"
os.environ["FLASK_DEBUG"] = "1"

print(f"Starting server using: {venv_python}")

# تشغيل السيرفر مباشرة باستخدام بايثون البيئة الافتراضية
try:
    subprocess.call([venv_python, "-m", "flask", "run", "--host=0.0.0.0"])
except KeyboardInterrupt:
    print("\nServer stopped.")
