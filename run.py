from dotenv import load_dotenv
load_dotenv()

import os
import subprocess

# تحديد المسارات
venv_path = os.path.join(os.getcwd(), "venv", "Scripts", "activate.bat")

print("Activating virtual environment...")

# تعريف التطبيق الرئيسي لفلَسك
flask_app = "flask_book_recommendation.app:create_app"

# نص الأمر الكامل
activate_cmd = f'"{venv_path}" && set FLASK_APP={flask_app} && python -m flask run --debug --host=0.0.0.0'

# تشغيل السيرفر
subprocess.call(activate_cmd, shell=True)
