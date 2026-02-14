
import sys
import os
import traceback

sys.path.append(os.getcwd())

# Mock setup_logging
import flask_book_recommendation.app as app_module
app_module.setup_logging = lambda app: None

from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import (
    get_trending, 
    get_behavior_based_recommendations
)

print("Starting test_recs.py...", flush=True)

app = create_app()

with app.app_context():
    print("\n--- Testing get_trending ---", flush=True)
    try:
        res = get_trending(limit=5)
        print(f"Result count: {len(res)}", flush=True)
        if res:
             print(f"Sample: {res[0].get('title')}", flush=True)
    except Exception:
        traceback.print_exc()

    print("\n--- Testing get_behavior_based_recommendations ---", flush=True)
    try:
        res = get_behavior_based_recommendations(1, limit=5)
        print(f"Result count: {len(res)}", flush=True)
    except Exception:
        traceback.print_exc()
