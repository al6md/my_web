import sys
import os
import random

# Add project root to path
sys.path.append(os.getcwd())

from flask import Flask
from flask_book_recommendation.extensions import cache, db
from flask_book_recommendation.app import create_app

app = create_app()

def verify_logic():
    with app.app_context():
        # 1. Mock a "Large Pool" as if it was cached
        mock_pool = [{'id': i, 'title': f'Book {i}', 'score': 0.9} for i in range(200)]
        
        # 2. Simulate Home Sections Logic
        print("--- Simulation 1 ---")
        candidate_slice = mock_pool[:100]
        sample1 = random.sample(candidate_slice, 12)
        print(f"Sample 1 IDs: {[b['id'] for b in sample1]}")
        
        print("--- Simulation 2 ---")
        sample2 = random.sample(candidate_slice, 12)
        print(f"Sample 2 IDs: {[b['id'] for b in sample2]}")
        
        # Verify intersection is low
        s1_ids = set([b['id'] for b in sample1])
        s2_ids = set([b['id'] for b in sample2])
        overlap = s1_ids.intersection(s2_ids)
        print(f"Overlap count: {len(overlap)} (Target: < 5)")
        
        if len(overlap) < 8:
            print("✅ SUCCESS: Samples are sufficiently different.")
        else:
            print("❌ FAILURE: Samples are too similar.")

if __name__ == "__main__":
    verify_logic()
