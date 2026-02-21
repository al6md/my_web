import sys
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Define a minimal app and model to avoid loading the large recommender package
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///flask_book_recommendation/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class UserEvent(db.Model):
    __tablename__ = "user_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    event_type = db.Column(db.String(20), nullable=False, index=True)
    book_google_id = db.Column(db.String(128), nullable=True, index=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    scroll_depth = db.Column(db.Float, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("Minimal UserEvent table creation check complete.")
