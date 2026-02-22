import os
import sys
import requests
import json
import numpy as np

# Ensure project root is in path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book, BookEmbedding, UserEmbedding
from ai_book_recommender.feature_store.user_embeddings import user_embedding_manager

def setup_test_data():
    app = create_app()
    with app.app_context():
        print("--- Setting up test data ---")
        user = User.query.first()
        if not user:
            print("❌ No user found. Run seed_db.py first.")
            return None
            
        # Get 5 random books to "interact" with
        books = Book.query.limit(5).all()
        if len(books) < 5:
            print("❌ Not enough books found. Run seed_db.py first.")
            return None
            
        print(f"Testing with User ID: {user.id}")
        
        # Ensure user has an embedding by interacting with books
        for b in books:
            # Ensure book has embedding
            book_emb = BookEmbedding.query.filter_by(book_id=b.id).first()
            if not book_emb or book_emb.vector is None:
                mock_vector = np.random.rand(384).tolist()
                if not book_emb:
                    book_emb = BookEmbedding(book_id=b.id, vector=mock_vector)
                    db.session.add(book_emb)
                else:
                    book_emb.vector = mock_vector
                db.session.commit()
                
            user_embedding_manager.update_user_embedding(user.id, book_id=b.id)
            
        return user.id

def test_endpoint(user_id):
    print("\n--- Testing /api/recommend/realtime endpoint ---")
    
    # We call the function directly since we don't have the Uvicorn server running
    import asyncio
    from ai_engine.main import realtime_recommend, RealtimeRecommendRequest
    
    req = RealtimeRecommendRequest(user_id=user_id, k=5)
    
    try:
        # It's an async function
        data = asyncio.run(realtime_recommend(req))
        
        print("✅ Endpoint returned success!")
        print(f"Status: {data.get('status')}")
        print(f"Recommended Books:")
        for idx, rec in enumerate(data.get('recommendations', [])):
            print(f"  {idx+1}. Book ID {rec['book_id']} (Score: {rec['score']:.4f})")
            
        if len(data.get('recommendations', [])) == 5:
             print("✅ Returned correct number of recommendations.")
        else:
             print("❌ Returned incorrect number of recommendations.")
             
    except Exception as e:
        print(f"❌ Core function failed: {e}")

if __name__ == "__main__":
    test_user_id = setup_test_data()
    if test_user_id:
        test_endpoint(test_user_id)
