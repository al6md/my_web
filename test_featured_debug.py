import os
import sys
import logging
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask
from flask_book_recommendation.routes.main import _build_featured_lists

logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)

with app.app_context():
    lists = _build_featured_lists()
    print(f"Success! Got {len(lists)} lists.")
    for item in lists:
        print(f"- {item['title']}: {item['count']} books, {len(item['covers'])} covers")
