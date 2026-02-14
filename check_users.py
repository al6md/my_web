
import sys
import os
sys.path.append(os.getcwd())

# Mock setup_logging to prevent any file usage
import flask_book_recommendation.app as app_module
app_module.setup_logging = lambda app: None

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book

print("Starting check_users.py (logging disabled)...", flush=True)

app = create_app()

with app.app_context():
    print("--- User Check ---", flush=True)
    user = User.query.first()
    if not user:
        print("No users found!", flush=True)
    else:
        print(f"Found User: {user.id} ({user.email})", flush=True)

    print("\n--- Book Check ---", flush=True)
    total_books = Book.query.count()
    user_books = Book.query.filter(Book.owner_id.isnot(None)).count()
    print(f"Total Books: {total_books}", flush=True)
    print(f"User Books (owner_id != None): {user_books}", flush=True)
