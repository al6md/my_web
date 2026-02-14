import time
import sys
import os
from unittest.mock import MagicMock

# Mock deep learning deps before they are imported
from unittest.mock import MagicMock
import types

class MockTensor: pass
class MockModule: pass

mock_torch = MagicMock()
mock_torch.Tensor = MockTensor
mock_torch.nn = MagicMock()
mock_torch.nn.Module = MockModule
mock_torch.nn.functional = MagicMock()

sys.modules['torch'] = mock_torch
sys.modules['torch.nn'] = mock_torch.nn
sys.modules['torch.nn.functional'] = mock_torch.nn.functional
sys.modules['flask_book_recommendation.advanced_recommender'] = MagicMock()
sys.modules['flask_book_recommendation.advanced_recommender.neural_model'] = MagicMock()

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask_book_recommendation.app import create_app, db
from flask_book_recommendation.recommender import get_behavior_based_recommendations
from flask_book_recommendation.models import User

app = create_app()

def verify_speed():
    with app.app_context():
        user = User.query.first()
        if not user:
            print("No user found in DB")
            return
        
        user_id = user.id
        print(f"Testing speed for User: {user.name} (ID: {user_id})")
        
        # Test 1: Cold Start (might involve matrix loading)
        start = time.perf_counter()
        recs1 = get_behavior_based_recommendations(user_id, limit=12, randomize=True)
        end = time.perf_counter()
        t1 = (end - start) * 1000
        print(f"Run 1 (Cold/Matrix Load): {t1:.2f}ms | Results: {len(recs1)}")
        
        # Test 2: Refresh (should use cached candidates + fast sampling)
        start = time.perf_counter()
        recs2 = get_behavior_based_recommendations(user_id, limit=12, randomize=True)
        end = time.perf_counter()
        t2 = (end - start) * 1000
        print(f"Run 2 (Refresh/Sample): {t2:.2f}ms | Results: {len(recs2)}")
        
        # Test 3: Multiple Refreshes
        timings = []
        for i in range(5):
            s = time.perf_counter()
            _ = get_behavior_based_recommendations(user_id, limit=12, randomize=True)
            e = time.perf_counter()
            timings.append((e - s) * 1000)
        
        avg_refresh = sum(timings) / len(timings)
        print(f"Average Refresh Time (5 runs): {avg_refresh:.2f}ms")
        
        # Verify Variety
        titles1 = set(r['title'] for r in recs1)
        titles2 = set(r['title'] for r in recs2)
        overlap = titles1.intersection(titles2)
        print(f"Variety Check: Run 1 has {len(titles1)} books, Run 2 has {len(titles2)} books.")
        print(f"Overlap: {len(overlap)} books (Randomization is working if overlap < 12)")

if __name__ == "__main__":
    verify_speed()
