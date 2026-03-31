import sys
import os
import numpy as np
import pickle

# Add project root to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding, SearchHistory, User
from flask_book_recommendation.recommender.search import semantic_search
from flask_book_recommendation.recommender.pipeline import get_deep_learning_recommendations

app = create_app()

def test_python_search():
    print("--- Testing Semantic Search for 'Python' ---")
    with app.app_context():
        results = semantic_search("Python", limit=5)
        if not results:
            print("No search results found for 'Python'.")
        else:
            print(f"Found {len(results)} results:")
            for i, r in enumerate(results):
                print(f"{i+1}. {r['title']} - {r['author']} (Reason: {r['reason']})")

def test_python_recommendations(user_id=2):
    print(f"\n--- Testing Recommendations for User ID {user_id} with Python intent ---")
    with app.app_context():
        # 1. Add "Python" to search history
        print("Injecting 'Python' into search history...")
        history = SearchHistory(user_id=user_id, query="Python")
        db.session.add(history)
        db.session.commit()

        # 2. Get recommendations
        print("Running Deep Learning Recommendations pipeline...")
        recs = get_deep_learning_recommendations(user_id, limit=20)
        
        if not recs:
            print("No recommendations returned.")
        else:
            print(f"Received {len(recs)} recommendations.")
            python_count = 0
            for i, r in enumerate(recs):
                is_python = "python" in r.get('title', '').lower() or "python" in r.get('category', '').lower()
                prefix = "[PYTHON] " if is_python else ""
                if is_python: python_count += 1
                
                print(f"{i+1}. {prefix}{r['title']} - {r['author']}")
                if 'extra_meta' in r:
                    print(f"   Algo: {r['extra_meta'].get('algorithm_used')} | Score: {r['extra_meta'].get('score')}")
            
            print(f"\nSummary: {python_count}/{len(recs)} recommendations relate to 'Python'.")

if __name__ == "__main__":
    try:
        test_python_search()
        test_python_recommendations()
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
