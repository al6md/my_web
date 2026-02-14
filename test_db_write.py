import sys
import os
import random

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding

def fake_write():
    app = create_app()
    with app.app_context():
        print("Testing DB write with FAKE embeddings...")
        
        # 1. Clean first (optional, but good for test)
        BookEmbedding.query.delete()
        db.session.commit()
        
        # 2. Add for ONE book
        book = Book.query.first()
        if not book:
            print("No books found.")
            return

        print(f"Generating fake for: {book.title}")
        fake_vec = [random.random() for _ in range(384)]
        
        emb = BookEmbedding(
            book_id=book.id,
            vector=fake_vec,
            model_name='fake-random'
        )
        db.session.add(emb)
        db.session.commit()
        print("Commit successful.")
        
        # 3. Verify
        saved = BookEmbedding.query.filter_by(book_id=book.id).first()
        if saved:
            print(f"Verified: Found embedding with len {len(saved.vector)}")
        else:
            print("Verified: FAILED - Not found.")

if __name__ == "__main__":
    fake_write()
