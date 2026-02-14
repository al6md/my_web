
import sys
import os
import random
from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import get_deep_learning_recommendations

app = create_app()

def test_transformer():
    with app.app_context():
        user_id = 1
        print("\n--- Testing get_deep_learning_recommendations (Transformer) ---")
        try:
            res1 = get_deep_learning_recommendations(user_id, limit=5, randomize=True)
            res2 = get_deep_learning_recommendations(user_id, limit=5, randomize=True)
            
            ids1 = [b['id'] for b in res1]
            ids2 = [b['id'] for b in res2]
            
            print(f"Run 1 IDs: {ids1}")
            print(f"Run 2 IDs: {ids2}")
            
            if ids1 != ids2:
                print("✅ SUCCESS: Transformer results changed!")
            else:
                print("⚠️ WARN: Transformer results are identical!")
        except Exception as e:
            print(f"Error testing transformer: {e}")

if __name__ == "__main__":
    test_transformer()
