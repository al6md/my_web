import sys
sys.path.append('C:\\Users\\al6md\\Desktop\\project alham\\flask_book_recommendation_starter')
from flask_book_recommendation.app import create_app
from flask_book_recommendation.routes.main import _generate_home_data
from flask_book_recommendation.extensions import cache
app = create_app()
with app.app_context():
    print("Clearing all cache...")
    cache.clear()
    print("Generating for user 1...")
    data = _generate_home_data(1)
    unified, buckets, top_rated, most_viewed, trending_libs = data
    print(f"Unified count: {len(unified)}")
    print(f"Top Rated count: {len(top_rated)}")
    print(f"Most Viewed count: {len(most_viewed)}")
    print(f"Trending Libs count: {len(trending_libs)}")
    if unified:
        import json
        print(f"First unified book: {unified[0].get('title')}")
