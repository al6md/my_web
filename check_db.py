import sys
import os

# Set up path to include the project root
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding

def check_db():
    app = create_app()
    with app.app_context():
        try:
            book_count = Book.query.count()
            emb_count = BookEmbedding.query.count()
            print(f"DEBUG_DB: Total Books: {book_count}")
            print(f"DEBUG_DB: Total Embeddings: {emb_count}")
            
            if emb_count == 0 and book_count > 0:
                print("DEBUG_DB: ALERT - No embeddings found! Transformer needs embeddings.")
            elif emb_count > 0:
                 # Check if vectors are actually populated (not None)
                 valid_emb = BookEmbedding.query.filter(BookEmbedding.vector.isnot(None)).count()
                 print(f"DEBUG_DB: Valid Embeddings (non-null vector): {valid_emb}")
        except Exception as e:
            print(f"DEBUG_DB: Error querying DB: {e}")

if __name__ == "__main__":
    check_db()
