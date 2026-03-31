from flask_book_recommendation.app import create_app
from ai_book_recommender.unified_pipeline import get_unified_engine

app = create_app()

with app.app_context():
    pipeline = get_unified_engine()
    pipeline.flask_app = app
    results = pipeline.recommend_full_stack(user_id=1, top_k=60)
    print("FINAL RESULTS LENGTH:", len(results))
