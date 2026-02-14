import sys
import os
import time

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding

def debug_generation():
    print(f"DEBUG_START: PID {os.getpid()}")
    app = create_app()
    with app.app_context():
        print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Test 1: Check existing
        count = BookEmbedding.query.count()
        print(f"Initial Embedding Count: {count}")
        
        # Test 2: Helper - Load Model
        print("Loading SentenceTransformer...")
        start = time.time()
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            print(f"Model loaded in {time.time() - start:.2f}s")
        except Exception as e:
            print(f"FATAL: Model load failed: {e}")
            return
            
        # Test 3: Generate ONE embedding
        book = Book.query.first()
        if not book:
            print("FATAL: No books in DB!")
            return
            
        print(f"Target Book: {book.title} (ID: {book.id})")
        text = f"{book.title}"
        
        try:
            print("Encoding...")
            vec = model.encode(text).tolist()
            print(f"Encoded vector length: {len(vec)}")
            
            print("Saving to DB...")
            # Check if exists first to avoid PK error
            existing = BookEmbedding.query.filter_by(book_id=book.id).first()
            if existing:
                print("Updating existing record...")
                existing.vector = vec
                existing.model_name = 'debug-model'
            else:
                print("Creating new record...")
                new_emb = BookEmbedding(book_id=book.id, vector=vec, model_name='debug-model')
                db.session.add(new_emb)
            
            db.session.commit()
            print("Commit successful.")
        except Exception as e:
            print(f"FATAL: DB Operation failed: {e}")
            db.session.rollback()
            return
            
        # Test 4: Verify
        current = BookEmbedding.query.filter_by(book_id=book.id).first()
        if current and current.vector:
             print("VERIFICATION: Record found and vector is present.")
        else:
             print("VERIFICATION FAIL: Record not found after commit!")

if __name__ == "__main__":
    debug_generation()
