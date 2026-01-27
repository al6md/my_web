
import sys
import os
import random

sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, UserBookView, Book

app = create_app()
ctx = app.app_context()
ctx.push()

user_email = "almagd1020@gmail.com"
user = User.query.filter_by(email=user_email).first()

if not user:
    print(f"❌ User {user_email} not found!")
    sys.exit(1)

print(f"User found: {user.name} (ID: {user.id})")

# Get some random books
books = Book.query.limit(50).all()
if not books:
    print("❌ No books found in DB!")
    sys.exit(1)

# Simulate 5 views
books_to_view = random.sample(books, 5)
print(f"Simulating views for {len(books_to_view)} books...")

for book in books_to_view:
    view = UserBookView(
        user_id=user.id,
        book_id=book.id,
        google_id=book.google_id,
        view_count=random.randint(1, 5)
    )
    db.session.add(view)
    print(f" - Viewed: {book.title}")

db.session.commit()
print("✅ Views added successfully!")
