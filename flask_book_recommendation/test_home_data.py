import sys
import logging
from flask import Flask
from models import db
from routes.main import _generate_home_data
from app import create_app

logging.basicConfig(level=logging.INFO)

app = create_app()

with app.app_context():
    print("Testing _generate_home_data for guest (user_id=None)...")
    try:
        data = _generate_home_data(None)
        unified, buckets, top_rated, most_viewed, trending_libs = data
        print(f"Unified count: {len(unified)}")
        print(f"Buckets keys: {list(buckets.keys())}")
        for k, v in buckets.items():
            print(f"  {k} count: {len(v)}")
        print(f"Top rated count: {len(top_rated)}")
        print(f"Most viewed count: {len(most_viewed)}")
        print(f"Trending libs count: {len(trending_libs)}")
        
        if unified:
            print("\nSample unified book keys:")
            print(unified[0].keys() if isinstance(unified[0], dict) else dir(unified[0]))
    except Exception as e:
        print(f"Error during generation: {e}")
