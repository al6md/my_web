import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask_book_recommendation.app import create_app
from flask_book_recommendation.routes.main import _build_featured_lists
from flask import render_template

app = create_app()
# Setting testing and proper template folder
app.testing = True

with app.test_request_context('/'):
    try:
        lists = _build_featured_lists()
        # Mock other required vars
        html = render_template(
            "components/home_feed.html",
            neural_sections={"recommended_for_you": []},
            top_interest="AI",
            deep_learning_books=[],
            mood_ai_books=[],
            mood_info={"name": "test", "color": "#000"},
            similar_minds=[],
            hot_right_now=[],
            featured_lists=lists
        )
        print("Template Rendered!")
    except Exception as e:
        import traceback
        traceback.print_exc()
