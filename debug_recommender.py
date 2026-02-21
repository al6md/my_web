import sys
import os
from flask import Flask

# Add project root to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import db, User
from flask_book_recommendation.recommender import (
    get_deep_learning_recommendations,
    get_behavior_based_recommendations,
    get_trending
)

def debug_algorithms():
    app = create_app()
    with app.app_context():
        # Get a user (first user)
        user = User.query.first()
        user_id = user.id if user else 1
        print(f"Debug User ID: {user_id}")
        
        print("\n--- Testing Transformer (Deep Learning) ---")
        try:
            res = get_deep_learning_recommendations(user_id, limit=5, randomize=True)
            print(f"Count: {len(res)}")
            if res:
                print(f"First Item: {res[0].get('title')} [{res[0].get('rec_type')}]")
            else:
                print("❌ Returned EMPTY")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

        print("\n--- Testing Hybrid (Behavior Based) ---")
        try:
            res = get_behavior_based_recommendations(user_id, limit=5, randomize=True)
            print(f"Count: {len(res)}")
            if res:
                print(f"First Item: {res[0].get('title')} [{res[0].get('rec_type')}]")
            else:
                print("❌ Returned EMPTY")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_algorithms()
