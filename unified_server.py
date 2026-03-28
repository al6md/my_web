import uvicorn
import os
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

# Import Flask App
from flask_book_recommendation.app import create_app

# Import AI Recommender App
from ai_book_recommender.api import app as engine_app

# Create Flask App
flask_app = create_app()

# Create Root App
root_app = FastAPI()

# Mount AI Engine API
root_app.mount("/api/engine", engine_app)

# Mount Flask at Root
root_app.mount("/", WSGIMiddleware(flask_app))

# Configuration
PORT = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    print(f"Starting Server on http://localhost:{PORT}")
    
    # Run using Uvicorn
    # Note: reload=True can cause restart loops if log files are in the same directory.
    # We disable it for stability, or you can use reload_dirs to watch specific folders.
    uvicorn.run(
        "unified_server:root_app", 
        host="0.0.0.0", 
        port=PORT, 
        reload=False  # Disabled to prevent restart loops from log files
    )
