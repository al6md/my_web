
import sys
import os

# Add parent directory to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, UserBookView, BookEmbedding, Book
from flask_book_recommendation.recommender import get_view_based_recommendations
import numpy as np

app = create_app()
ctx = app.app_context()
ctx.push()

print("\n--- Debugging View-Based Recommendations ---\n")

# 1. Check logged in user (simulated)
user = User.query.filter_by(email="almagd1020@gmail.com").first()
if not user:
    print("❌ User not found!")
    sys.exit(1)

print(f"User: {user.name} (ID: {user.id})")

# 2. Check UserBookView
views = UserBookView.query.filter_by(user_id=user.id).all()
print(f"Total Views: {len(views)}")
if views:
    for v in views[:5]:
        print(f" - View: Book ID {v.book_id} / Google {v.google_id}")
else:
    print("⚠️ No views found! The feature needs views to work.")

# 3. Check Embeddings
print(f"\nTotal Book Embeddings: {BookEmbedding.query.count()}")
if views:
    book_ids = [v.book_id for v in views if v.book_id]
    embeddings = BookEmbedding.query.filter(BookEmbedding.book_id.in_(book_ids)).all()
    print(f"Embeddings for viewed books: {len(embeddings)}")
    
    if len(embeddings) == 0:
        print("❌ WARNING: No embeddings found for the viewed books! AI cannot work without embeddings.")
        print("   -> Run 'python generate_embeddings.py' to generate embeddings.")

# 4. Try the function
print("\nTesting get_view_based_recommendations()...")
try:
    recs = get_view_based_recommendations(user.id)
    print(f"Recommendations returned: {len(recs)}")
    for r in recs:
        print(f" - {r['title']} ({r['reason']})")
except Exception as e:
    print(f"❌ FUNCTION ERROR: {e}")

print("\nDone.")
