
import sys
import os
import random
from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import (
    get_topic_based,
    get_behavior_based_recommendations,
    get_deep_learning_recommendations,
    get_last_search_recommendations
)

app = create_app()

def test_randomization():
    with app.app_context():
        user_id = 1
        
        print("\n--- Testing get_behavior_based_recommendations (Salt Logic) ---")
        res1 = get_behavior_based_recommendations(user_id, limit=5, randomize=True)
        res2 = get_behavior_based_recommendations(user_id, limit=5, randomize=True)
        
        ids1 = [b['id'] for b in res1]
        ids2 = [b['id'] for b in res2]
        
        print(f"Run 1 IDs: {ids1}")
        print(f"Run 2 IDs: {ids2}")
        
        if ids1 != ids2:
            print("✅ SUCCESS: Hybrid Results changed (Salt working)!")
        else:
            print("❌ FAILURE: Hybrid Results are identical!")

        print("\n--- Testing get_topic_based (Offset Logic) ---")
        # Ensure we have some topics for this user or mock it
        res3 = get_topic_based(user_id, limit=5, randomize=True)
        res4 = get_topic_based(user_id, limit=5, randomize=True)
        
        # get_topic_based returns dict with 'books' key
        if isinstance(res3, dict): res3 = res3.get('books', [])
        if isinstance(res4, dict): res4 = res4.get('books', [])

        ids3 = [b['id'] for b in res3]
        ids4 = [b['id'] for b in res4]
        
        print(f"Run 1 IDs: {ids3}")
        print(f"Run 2 IDs: {ids4}")
        
        if ids3 != ids4:
             print("✅ SUCCESS: Topic Results changed (Global Offset working)!")
        else:
             print("⚠️ WARN: Topic Results are identical! (Might be due to limited topics/books)")

        print("\n--- Testing get_last_search_recommendations (Start Index Logic) ---")
        try:
            _, res5 = get_last_search_recommendations(user_id, limit=5, randomize=True)
            _, res6 = get_last_search_recommendations(user_id, limit=5, randomize=True)
            
            if res5 and res6:
                ids5 = [b['id'] for b in res5]
                ids6 = [b['id'] for b in res6]
                
                print(f"Run 1 IDs: {ids5}")
                print(f"Run 2 IDs: {ids6}")
                
                if ids5 != ids6:
                    print("✅ SUCCESS: Search History Results changed!")
                else:
                    print("❌ FAILURE: Search History Results are identical!")
            else:
                print("⚠️ WARN: No search history found for user.")
        except Exception as e:
            print(f"Error testing search: {e}")

if __name__ == "__main__":
    test_randomization()
