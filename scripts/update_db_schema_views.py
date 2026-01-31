
import logging
from flask import Flask
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import UserBookView
from flask_book_recommendation.config import Config

# Setup simplistic app to work with Flask-SQLAlchemy
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)

def update_schema():
    with app.app_context():
        print("Checking for existing tables...")
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        target_table = "user_book_views"
        if target_table in existing_tables:
            print(f"Table '{target_table}' already exists.")
        else:
            print(f"Creating table '{target_table}'...")
            # Create specific table associated with the model
            UserBookView.__table__.create(db.engine)
            print(f"Table '{target_table}' created successfully.")

if __name__ == "__main__":
    update_schema()
