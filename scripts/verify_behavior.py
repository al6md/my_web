
import logging
from flask import Flask
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book, UserBookView
from flask_book_recommendation.recommender import log_user_view
from flask_book_recommendation.config import Config

# Setup app
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def verify():
    with app.app_context():
        # Get first user
        u = User.query.first()
        if not u:
            print("No user found to test.")
            return

        # Get first book
        b = Book.query.first()
        if not b:
            print("No book found to test.")
            return

        print(f"Testing logging for User: {u.id}, Book: {b.id}")
        
        # Log view
        log_user_view(u.id, b)
        
        # Check DB
        view = UserBookView.query.filter_by(user_id=u.id, book_id=b.id).first()
        if view:
            print(f"✅ Success! View found. Count: {view.view_count}")
        else:
            print("❌ Failed! View not found.")

if __name__ == "__main__":
    verify()
