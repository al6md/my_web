import sys
import os

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import SearchHistory
from flask_book_recommendation.recommender import get_last_search_recommendations

def test_search_recs():
    app = create_app()
    with app.app_context():
        user_id = 1
        query = "artificial intelligence"
        
        print(f"1. Simulating search for: {query}")
        # Add search history
        sh = SearchHistory(user_id=user_id, query=query)
        db.session.add(sh)
        db.session.commit()
        
        print("2. Fetching recommendations...")
        result = get_last_search_recommendations(user_id, limit=5)
        
        if not result or not result[1]:
            print("❌ No results returned.")
            return

        display_query, books = result
        print(f"Returned Query: {display_query}")
        print(f"Books Found: {len(books)}")
        for b in books:
            print(f" - {b.get('title')} ({b.get('source')})")
            print(f"   Reason: {b.get('reason')}")

if __name__ == "__main__":
    test_search_recs()
