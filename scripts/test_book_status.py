"""
Script to test the book status functionality.
"""
import sys
import os

sys.path.append(os.getcwd())
from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import BookStatus, Book, User

app = create_app()

def test_book_status():
    with app.app_context():
        print("Testing book status functionality...")
        
        # Check if we have any users and books
        user = User.query.first()
        book = Book.query.first()
        
        if not user:
            print("ERROR: No users found in database")
            return
        
        if not book:
            print("ERROR: No books found in database")
            return
            
        print(f"User: {user.email}")
        print(f"Book: {book.title}")
        
        # Check existing statuses
        statuses = BookStatus.query.filter_by(user_id=user.id).all()
        print(f"\nExisting statuses for user {user.id}: {len(statuses)}")
        for s in statuses:
            print(f"  - Book ID {s.book_id}: {s.status}")
        
        # Try to add a new status
        print("\nTrying to add book to favorites...")
        existing = BookStatus.query.filter_by(user_id=user.id, book_id=book.id).first()
        if existing:
            print(f"  Already has status: {existing.status}")
        else:
            new_status = BookStatus(user_id=user.id, book_id=book.id, status="favorite")
            db.session.add(new_status)
            db.session.commit()
            print("  SUCCESS: Added to favorites!")
        
        # Verify
        favorites = BookStatus.query.filter_by(user_id=user.id, status="favorite").all()
        print(f"\nFavorites count: {len(favorites)}")
        for f in favorites:
            b = Book.query.get(f.book_id)
            if b:
                print(f"  - {b.title}")

if __name__ == "__main__":
    try:
        test_book_status()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
