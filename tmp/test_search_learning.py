# test_search_learning.py
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_book_recommender.engine import get_engine
from ai_book_recommender.user_intelligence.online_learning import FeedbackEvent
import numpy as np

def test_search_feedback():
    engine = get_engine()
    user_id = 999
    item_id = "test_book_123"
    
    print(f"--- Testing Search Feedback for User {user_id} ---")
    
    # 1. Record search feedback
    engine.record_feedback(user_id, item_id, "search", 1.0)
    print(f"Recorded 'search' feedback for book: {item_id}")
    
    # 2. Check signal in FeedbackProcessor
    processor = engine.online_learner.feedback_processor
    signal = processor._compute_signal(FeedbackEvent(user_id, item_id, "search", 1.0, None))
    print(f"Computed signal for 'search': {signal}")
    assert signal == 0.2, f"Expected 0.2, got {signal}"
    
    # 3. Check if score adjustment is non-zero (might need more events for Wilson score)
    # Let's add multiple to see the trend
    for _ in range(5):
        engine.record_feedback(user_id, item_id, "search", 1.0)
        
    adj = processor.get_item_score_adjustment(item_id)
    print(f"Score adjustment for {item_id}: {adj}")
    
    # 4. Ensure it doesn't affect bandit trials (since success rate for search is passive)
    trials, successes = engine.online_learner._arms.get(item_id, (0, 0.0))
    print(f"Bandit stats for {item_id}: Trials={trials}, Successes={successes}")
    assert trials == 0, "Search results should not increase bandit trials directly (passive exposure)"

    print("\n✅ Search feedback integration test PASSED!")

if __name__ == "__main__":
    test_search_feedback()
