import sys
import os
import time

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding

def fix_embeddings_robust():
    print("Initializing Flask App...")
    app = create_app()
    with app.app_context():
        print("Checking books...")
        books = Book.query.all()
        missing = []
        for b in books:
            if not BookEmbedding.query.filter_by(book_id=b.id).first():
                missing.append(b)
        
        print(f"Found {len(missing)} books without embeddings.")
        if not missing:
            print("Nothing to do.")
            return

        print("Loading SentenceTransformer (this may take a few seconds)...")
        start_time = time.time()
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            print(f"Model loaded in {time.time() - start_time:.2f}s")
        except Exception as e:
            print(f"FATAL: Failed to load model: {e}")
            return

        print("Starting generation...")
        count = 0
        success_count = 0
        
        for b in missing:
            try:
                text = f"{b.title} {b.author or ''} {b.description or ''}"
                vec = model.encode(text).tolist()
                
                emb = BookEmbedding(
                    book_id=b.id,
                    vector=vec
                    # model_name removed as it does not exist in DB schema
                )
                db.session.add(emb)
                count += 1
                success_count += 1
                
                if count % 10 == 0:
                    db.session.commit()
                    print(f"Committed {count}/{len(missing)}...")
            except Exception as e:
                print(f"Error processing book {b.id}: {e}")
                db.session.rollback() # Rollback current transaction to keep connection alive
        
        # Final commit
        try:
            db.session.commit()
            print(f"Final commit. Total success: {success_count}")
        except Exception as e:
            print(f"Error in final commit: {e}")

if __name__ == "__main__":
    fix_embeddings_robust()
