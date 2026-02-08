import sys
import os
import logging

# Setup Path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import _get_ai_embedding_recommendations
from flask_book_recommendation.ai_client import ai_client

# Log to stdout
logging.basicConfig(level=logging.INFO)

app = create_app()

def test_fallback_mechanism():
    print("\n--- Testing Recommender Fallback Logic ---")
    
    # We expect the AI Server to be offline or unreachable in this test script environment
    # unless user started it. We want to verify that the code DOES NOT CRASH.
    
    with app.app_context():
        # Dummy inputs
        print("Calling _get_ai_embedding_recommendations with user_id=1...")
        recs = _get_ai_embedding_recommendations(
            user_id=1, 
            viewed_book_ids=[1, 2],
            limit=5
        )
        
        print(f"Result Count: {len(recs)}")
        if recs:
            print("First Rec Source:", recs[0].get('source'))
            
        # Check source
        if recs and "AI Neural Brain" in recs[0].get('source', ''):
             print("SUCCESS: AI Engine responded!")
        elif recs:
             print("SUCCESS: Fallback to Local Logic worked!")
        else:
             print("WARNING: No recommendations returned (could be empty DB), but no crash.")

if __name__ == "__main__":
    test_fallback_mechanism()
