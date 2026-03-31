import os
import sys

# Adding app dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask_book_recommendation.app import create_app
from flask_book_recommendation.routes.main import _build_featured_lists

app = create_app()
with app.app_context():
    print("Fetching featured lists...")
    lists = _build_featured_lists()
    print(f"Got {len(lists)} featured lists:")
    for l in lists:
        print(f" - {l['title']}: {len(l['covers'])} covers displayed")
        for i, url in enumerate(l['covers']):
             print(f"      Cover {i+1}: {url}")
