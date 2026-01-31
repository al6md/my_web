
import sys
import os
import random
from datetime import datetime

# Add project path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book, SearchHistory, UserRatingCF, BookStatus, PublicRating
from flask_book_recommendation.recommender import get_behavior_based_recommendations

def create_test_data(app):
    with app.app_context():
        print("🛠️ Setting up test data...")
        
        # 1. Create/Get Test User
        user = User.query.filter_by(email="test_rec_v2@example.com").first()
        if user:
            # Clean up old data for this user
            db.session.query(SearchHistory).filter_by(user_id=user.id).delete()
            db.session.query(UserRatingCF).filter_by(user_id=user.id).delete()
            db.session.query(BookStatus).filter_by(user_id=user.id).delete()
            db.session.query(PublicRating).filter_by(user_id=user.id).delete()
            print(f"  Existing user cleaned: {user.email}")
        else:
            user = User(
                name="Test Rec V2",
                email="test_rec_v2@example.com",
                password_hash="dummy"
            )
            db.session.add(user)
            db.session.commit()
            print(f"  New user created: {user.email}")

        # 2. Insert Signal 1: Search for "Python Programming" (Weight: Moderate/High)
        print("  Signal 1: Search 'Python Programming'")
        sh = SearchHistory(user_id=user.id, query="Python Programming")
        db.session.add(sh)

        # 3. Insert Signal 2: High Rating (5 stars) for a specialized topic, e.g., "Italian Cooking"
        # We need a book with an embedding for this to work effectively with AI
        # Let's try to find an existing book or insert a dummy one with embedding (requires real embedding gen, might be slow)
        # Instead, we will rely on the text search fallback or existing logic if embedding is missing, 
        # BUT for AI embedding to work, we need books with embeddings.
        # Assuming database has some populated books. If not, this test might be partial.
        
        # Let's insert a "Cooking" book and pretend it has an embedding (or just rely on the fact that existing logic might pick it up)
        # Ideally we search for a real book ID to rate. 
        # For this test, we will assume standard flow:
        # We'll rely on the recommender picking up the "High Rating" signal. 
        # To make it robust without mocking vectors, we will just insert the record and see if it's passed to AI.
        
        # Let's create a dummy book for Cooking
        book_cooking = Book.query.filter_by(title="Mastering Italian Cooking").first()
        if not book_cooking:
            book_cooking = Book(
                title="Mastering Italian Cooking",
                author="Chef Mario",
                google_id="test_cooking_123", # Fake
                categories="Cooking, Food"
            )
            db.session.add(book_cooking)
            db.session.commit()
            
        print(f"  Signal 2: Rate 'Mastering Italian Cooking' (5 stars) - ID: {book_cooking.id}")
        ur = UserRatingCF(user_id=user.id, google_id=book_cooking.google_id, rating=5.0)
        db.session.add(ur)
        
        # 4. Insert Signal 3: Like (Favorite) for "Space Exploration"
        book_space = Book.query.filter_by(title="The Mars Mystery").first()
        if not book_space:
             book_space = Book(
                title="The Mars Mystery",
                author="Space Explorer",
                google_id="test_space_456",
                categories="Science, Space"
             )
             db.session.add(book_space)
             db.session.commit()
             
        print(f"  Signal 3: Like 'The Mars Mystery' - ID: {book_space.id}")
        bs = BookStatus(user_id=user.id, book_id=book_space.id, status="favorite")
        db.session.add(bs)
        
        db.session.commit()
        return user.id

def verify_recommendations(app, user_id):
    with app.app_context():
        print("\n🚀 Running get_behavior_based_recommendations (Page 1 - Limit 100)...")
        # Test Limit 100
        recs_page_1 = get_behavior_based_recommendations(user_id, limit=100)
        print(f"  📊 Page 1 Count: {len(recs_page_1)}")
        
        print("\n🚀 Running get_behavior_based_recommendations (Page 2 - Offset 100)...")
        # Test Pagination
        recs_page_2 = get_behavior_based_recommendations(user_id, limit=100, offset=100)
        print(f"  📊 Page 2 Count: {len(recs_page_2)}")
        
        # Check intersection
        ids_1 = {b['id'] for b in recs_page_1}
        ids_2 = {b['id'] for b in recs_page_2}
        
        intersection = ids_1.intersection(ids_2)
        print(f"  🔄 Intersection (Duplicates across pages): {len(intersection)}")
        
        if len(intersection) == 0:
            print("  ✅ Pagination Success: No duplicates between pages.")
        else:
            print(f"  ⚠️ Pagination Warning: {len(intersection)} duplicates found.")

        print(f"\n📊 Recommendation Analysis (First 10 of Page 1):")
        found_signals = {
            "python": False,
            "cooking": False,
            "space": False
        }
        
        for i, book in enumerate(recs_page_1[:10]):
            title = book.get("title", "")
            reason = book.get("reason", "")
            score = book.get("score", 0)
            
            print(f"  {i+1}. [{score:.2f}] {title} | {reason}")
            
            txt = (title + " " + reason).lower()
            if "python" in txt or "code" in txt or "programming" in txt: found_signals["python"] = True
            if "cooking" in txt or "food" in txt: found_signals["cooking"] = True
            if "space" in txt or "mars" in txt or "science" in txt: found_signals["space"] = True

        print("\n✅ Signal Verification:")
        for signal, found in found_signals.items():
            status = "PASS" if found else "WARN (Might need real embeddings)"
            print(f"  Signal '{signal}': {status}")

if __name__ == "__main__":
    app = create_app()
    user_id = create_test_data(app)
    verify_recommendations(app, user_id)
