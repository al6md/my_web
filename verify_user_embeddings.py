import os
import sys
import numpy as np

# Ensure project root is in path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book, BookEmbedding, UserEmbedding
from ai_book_recommender.feature_store.user_embeddings import user_embedding_manager

def test_embeddings():
    app = create_app()
    with app.app_context():
        # 1. Setup Mock Data
        print("--- Setting up test data ---")
        user = User.query.first()
        if not user:
            print("❌ No user found in DB. Run seed_db.py first.")
            return
        
        book = Book.query.first()
        if not book:
            print("❌ No book found in DB. Run seed_db.py first.")
            return
            
        # Ensure book has embedding
        book_emb = BookEmbedding.query.filter_by(book_id=book.id).first()
        if not book_emb or book_emb.vector is None:
            print(f"--- Creating mock embedding for book {book.id} ---")
            mock_vector = np.random.rand(384).tolist()
            if not book_emb:
                book_emb = BookEmbedding(book_id=book.id, vector=mock_vector)
                db.session.add(book_emb)
            else:
                book_emb.vector = mock_vector
            db.session.commit()
        
        target_vector = np.array(book_emb.vector)
        
        # 2. Test Update
        print(f"--- Testing update for user {user.id} with book {book.id} ---")
        success = user_embedding_manager.update_user_embedding(user.id, book_id=book.id)
        
        if success:
            print("✅ update_user_embedding returned True")
            
            # 3. Verify in DB
            user_emb = UserEmbedding.query.filter_by(user_id=user.id).first()
            if user_emb:
                print(f"✅ UserEmbedding found in DB. Count: {user_emb.interaction_count}")
                db_vector = np.array(user_emb.vector)
                
                # Check if matches (since it's the first interaction, it should match exactly)
                if np.allclose(db_vector, target_vector):
                    print("✅ Vector matches expected running mean (exact match for 1st interaction)")
                else:
                    print("❌ Vector does not match!")
            else:
                print("❌ UserEmbedding NOT found in DB!")
        else:
            print("❌ update_user_embedding failed!")

if __name__ == "__main__":
    test_embeddings()
