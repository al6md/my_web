
import sys
import os
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book, UserRatingCF
from flask_book_recommendation.recommender import (
    get_trending, 
    get_behavior_based_recommendations,
    get_deep_learning_recommendations,
    get_cf_similar
)

app = create_app()

with app.app_context():
    print("--- User Check ---")
    user = User.query.first()
    if not user:
        print("No users found!")
    else:
        print(f"Found User: {user.id} ({user.email})")
        user_id = user.id

        print("\n--- Book Check ---")
        total_books = Book.query.count()
        user_books = Book.query.filter(Book.owner_id.isnot(None)).count()
        print(f"Total Books: {total_books}")
        print(f"User Books (owner_id != None): {user_books}")

        print("\n--- Trending Check ---")
        try:
            trending = get_trending(limit=5)
            print(f"Trending results: {len(trending)}")
            if trending:
                print(f"Sample: {trending[0].get('title')}")
        except Exception as e:
            print(f"Trending Error: {e}")

        print("\n--- Behavior Check ---")
        try:
            behavior = get_behavior_based_recommendations(user_id, limit=5)
            print(f"Behavior results: {len(behavior)}")
        except Exception as e:
            print(f"Behavior Error: {e}")

        print("\n--- Deep Learning Check ---")
        try:
            dl = get_deep_learning_recommendations(user_id, limit=5)
            print(f"Deep Learning results: {len(dl)}")
        except Exception as e:
            print(f"Deep Learning Error: {e}")

        print("\n--- CF Check ---")
        try:
            cf = get_cf_similar(user_id, top_n=5)
            print(f"CF results: {len(cf)}")
        except Exception as e:
            print(f"CF Error: {e}")
