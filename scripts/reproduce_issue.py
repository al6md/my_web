import sys
import os
from flask import Flask
from datetime import datetime

# Add the project directory to sys.path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app, db
from flask_book_recommendation.models import User, Book, UserBookView, BookEmbedding
from flask_book_recommendation.recommender import get_behavior_based_recommendations

def reproduce():
    app = create_app()
    with app.app_context():
        # 1. Create a test user
        user = User.query.filter_by(email="test_behavior@example.com").first()
        if not user:
            user = User(name="Test User", email="test_behavior@example.com", password_hash="dummy")
            db.session.add(user)
            db.session.commit()
            print(f"Created user {user.id}")
        else:
            print(f"Using existing user {user.id}")
            # Clear previous views for clean test
            UserBookView.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            print("Cleared previous views")

        # 2. Get initial recommendations (should be empty or based on nothing)
        print("\n--- Initial Recommendations ---")
        recs_initial = get_behavior_based_recommendations(user.id, limit=5)
        for r in recs_initial:
            print(f"- {r['title']} ({r.get('reason')})")

        # 3. Simulate viewing 5 Classic Books
        # IDs for known classics (using Google IDs)
        classic_books = [
            {"id": "5NomkK4XVmkC", "title": "Emma", "author": "Jane Austen", "categories": "Fiction"}, # Austen
            {"id": "s1gVAAAAYAAJ", "title": "Pride and Prejudice", "author": "Jane Austen", "categories": "Fiction"}, # Austen
            {"id": "3b5QAAAAMAAJ", "title": "Jane Eyre", "author": "Charlotte Brontë", "categories": "Fiction"}, # Bronte
            {"id": "fW_yyW5hXzUC", "title": "Wuthering Heights", "author": "Emily Brontë", "categories": "Fiction"}, # Bronte
            {"id": "1", "title": "Great Expectations", "author": "Charles Dickens", "categories": "Fiction"}, # Dickens (system book?)
        ]

        print(f"\n--- Simulating Views for {len(classic_books)} Classic Books ---")
        for b_data in classic_books:
            # Ensure book exists in DB for proper tracking
            book = Book.query.filter_by(google_id=b_data["id"]).first()
            if not book:
                book = Book(
                    google_id=b_data["id"],
                    title=b_data["title"],
                    author=b_data["author"],
                    categories=b_data["categories"],
                    owner_id=None
                )
                db.session.add(book)
                db.session.commit()
            
            # Record view
            view = UserBookView(
                user_id=user.id,
                google_id=b_data["id"],
                book_id=book.id,
                view_count=1,
                last_viewed_at=datetime.utcnow()
            )
            db.session.add(view)
        db.session.commit()
        print("Views recorded.")

        # 4. Get recommendations again
        print("\n--- Recommendations After Views ---")
        recs_after = get_behavior_based_recommendations(user.id, limit=10)
        for r in recs_after:
            print(f"- {r['title']} ({r.get('reason')})")

        # 5. Check if they are related to "Fiction" or "Authors"
        related_count = 0
        for r in recs_after:
            reason = r.get('reason', '')
            if 'Austen' in reason or 'Brontë' in reason or 'Fiction' in reason or 'تصنيف' in reason or 'أعمال' in reason:
                related_count += 1
        
        print(f"\nFound {related_count} related recommendations out of {len(recs_after)}")

if __name__ == "__main__":
    reproduce()
