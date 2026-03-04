import os
import sys

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask
from flask_book_recommendation.routes.main import _build_featured_lists

app = Flask(__name__)

with app.app_context():
    try:
        lists = _build_featured_lists()
        print("Success!")
        print(f"Got {len(lists)} lists.")
        for item in lists:
            print(f"- {item['title']}: {item['count']} books, {len(item['covers'])} covers")
    except Exception as e:
        import traceback
        traceback.print_exc()
