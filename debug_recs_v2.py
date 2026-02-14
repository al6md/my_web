
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

print("Starting debug_recs_v2.py...", flush=True)

app = create_app()

with app.app_context():
    print("STEP 1: Testing get_trending", flush=True)
    try:
        res = get_trending(limit=5)
        print(f"STEP 1 DONE. Result count: {len(res)}", flush=True)
    except BaseException as e:
        print(f"STEP 1 FAILED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    print("\nSTEP 2: Testing get_behavior_based_recommendations", flush=True)
    try:
        res = get_behavior_based_recommendations(1, limit=5)
        print(f"STEP 2 DONE. Result count: {len(res) if res is not None else 'None'}", flush=True)
    except BaseException as e:
        print(f"STEP 2 FAILED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    
    print("\nScript Finished.", flush=True)
