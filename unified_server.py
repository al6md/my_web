import uvicorn
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.staticfiles import StaticFiles
import os

# 1. Import AI Engine (FastAPI)
try:
    from ai_engine.main import app as ai_app
except ImportError:
    # Fallback if run from different dir
    import sys
    sys.path.append(os.path.join(os.getcwd(), 'ai_engine'))
    from ai_engine.main import app as ai_app

# 2. Import Flask App
from flask_book_recommendation.app import create_app

# Create Flask App
flask_app = create_app()

# 3. Create Root App
root_app = FastAPI()

# 4. Mount Apps
# Mount AI Engine at /api to avoid collision with Flask
root_app.mount("/api", ai_app)

# Mount Flask at Root
# This handles everything else
root_app.mount("/", WSGIMiddleware(flask_app))

# 5. Configuration
PORT = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    print(f"🚀 Starting Unified Server on http://localhost:{PORT}")
    print(f"📘 Flask (Website): http://localhost:{PORT}/")
    print(f"🤖 AI Engine (API): http://localhost:{PORT}/api/docs")
    
    # Run using Uvicorn
    uvicorn.run(root_app, host="0.0.0.0", port=PORT)
