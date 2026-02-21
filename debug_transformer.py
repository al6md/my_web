import sys
import os
sys.path.append(os.getcwd())

# Fix for Windows encoding
sys.stdout.reconfigure(encoding='utf-8')

from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import get_deep_learning_recommendations, get_last_search_recommendations

app = create_app()

with app.app_context():
    # User ID 1 is likely the user. (Or try to find valid user)
    # Using 1 for test.
    uid = 1
    print(f"--- Debugging for User {uid} ---")
    
    print("\n[1] Testing Transformer (Deep Learning)...")
    try:
        res = get_deep_learning_recommendations(uid, limit=10)
        print(f"Transformer returned: {len(res)} items")
        if res:
            for i, b in enumerate(res[:3]):
                print(f"  {i+1}. {b.get('title')} (Score: {b.get('ai_score')})")
        else:
            print("  Result is EMPTY. Check if user has history or if model/API fails.")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n[2] Testing Search History...")
    try:
        # returns (reason, list_of_books)
        val = get_last_search_recommendations(uid, limit=10)
        if val:
            reason, res = val
            print(f"Search History returned: {len(res)} items")
            print(f"  Reason: {reason}")
            if res:
                for i, b in enumerate(res[:3]):
                    print(f"  {i+1}. {b.get('title')}")
        else:
             print("  Result is None/Empty.")
    except Exception as e:
        print(f"  ERROR: {e}")
