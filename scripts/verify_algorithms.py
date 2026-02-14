import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User
from flask_book_recommendation.recommender import (
    get_last_search_recommendations,
    get_topic_based,
    get_behavior_based_recommendations,
    get_deep_learning_recommendations,
    get_cf_similar,
    get_content_similar,
    get_view_based_recommendations
)

def verify_algorithms():
    app = create_app()
    with app.app_context():
        user = User.query.first()
        if not user:
            print("No users found in database.")
            return

        print(f"Testing algorithms for User ID: {user.id} ({user.name})")
        print("-" * 50)

        algorithms = [
            ("Search History", get_last_search_recommendations, {"limit": 5}),
            ("Interest Match", get_topic_based, {"limit": 5}),
            ("Hybrid Behavior", get_behavior_based_recommendations, {"limit": 5}),
            ("Deep Learning", get_deep_learning_recommendations, {"limit": 5}),
            ("Collaborative Filtering", get_cf_similar, {"top_n": 5}),
            ("Content Based", get_content_similar, {"top_n": 5}),
            ("Neural Reranker", get_view_based_recommendations, {"top_n": 5}),
        ]

        for name, func, kwargs in algorithms:
            print(f"Testing {name}...", end=" ", flush=True)
            try:
                # Adjust args based on function signature
                if name == "Search History":
                    # returns (query, books)
                    result = func(user.id, **kwargs)
                    books = result[1] if result else []
                elif name == "Interest Match":
                    # returns dict or list
                    result = func(user.id, **kwargs)
                    books = result.get('books', []) if isinstance(result, dict) else result
                else:
                    books = func(user.id, **kwargs)
                
                count = len(books) if books else 0
                print(f"✅ OK ({count} results)")
                if count > 0:
                    first = books[0]
                    print(f"   Sample: {first.get('title')} (Score: {first.get('score') or first.get('confidence')})")
            except Exception as e:
                print(f"❌ FAILED: {str(e)}")

if __name__ == "__main__":
    verify_algorithms()
