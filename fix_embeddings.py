import sys
import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding
from flask_book_recommendation.recommender import get_deep_learning_recommendations

def fix_and_verify():
    app = create_app()
    with app.app_context():
        print("--- 1. Checking Embeddings ---")
        books = Book.query.all()
        start_count = BookEmbedding.query.count()
        print(f"Total Books: {len(books)}")
        print(f"Current Embeddings: {start_count}")
        
        missing_books = []
        for b in books:
            if not BookEmbedding.query.filter_by(book_id=b.id).first():
                missing_books.append(b)
        
        print(f"Books missing embeddings: {len(missing_books)}")
        
        if missing_books:
            print("--- 2. Generating Embeddings ---")
            try:
                model = SentenceTransformer('all-MiniLM-L6-v2')
                print("Model loaded.")
                
                new_embs = []
                for b in missing_books:
                    text_to_embed = f"{b.title} {b.author or ''} {b.desc or ''}"
                    embedding = model.encode(text_to_embed).tolist()
                    
                    new_emb = BookEmbedding(
                        book_id=b.id,
                        vector=embedding,
                        model_name='all-MiniLM-L6-v2'
                    )
                    db.session.add(new_emb)
                    new_embs.append(new_emb)
                    
                    if len(new_embs) % 10 == 0:
                        print(f"Generated {len(new_embs)}...")
                
                db.session.commit()
                print(f"SUCCESS: Generated {len(new_embs)} new embeddings.")
            except Exception as e:
                print(f"ERROR generating embeddings: {e}")
                db.session.rollback()
        else:
            print("All books have embeddings.")
            
        print("--- 3. Verifying Transformer Recommendations ---")
        try:
            # Test with user_id=1 (assuming exists, or fallback 0)
            user_id = 1
            print(f"Requesting recommendations for User {user_id}...")
            recs = get_deep_learning_recommendations(user_id=user_id, limit=5)
            print(f"Result count: {len(recs)}")
            for r in recs:
                print(f" - {r.get('title')} (Score: {r.get('extra_meta', {}).get('score')}) [Source: {r.get('source')}]")
                
            if len(recs) == 0:
                print("WARNING: Still returning 0 results. Check logic or model loading.")
            else:
                 print("VERIFICATION SUCCESS: Transformer is working!")
                 
        except Exception as e:
            print(f"ERROR verifying recommendations: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    fix_and_verify()
