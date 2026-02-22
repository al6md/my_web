import uvicorn
import os
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

# Import Flask App
from flask_book_recommendation.app import create_app

# Create Flask App
flask_app = create_app()

# Create Root App
root_app = FastAPI()

# Mount Flask at Root
root_app.mount("/", WSGIMiddleware(flask_app))

# Configuration
PORT = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    print(f"Starting Server on http://localhost:{PORT}")
    
    # Run using Uvicorn
    uvicorn.run(root_app, host="0.0.0.0", port=PORT)
