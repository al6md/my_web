
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Adding the project root to sys.path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, Book, UserPreference, SearchHistory
from flask_book_recommendation.recommender import (
    get_hybrid_recommendations, 
    get_author_books, 
    get_discovery_picks, 
    rerank_search_results,
    get_hidden_gems,
    get_genre_explorer
)

def verify_all():
    app = create_app()
    with app.app_context():
        print("--- Testing get_discovery_picks ---")
        picks = get_discovery_picks(limit=5)
        print(f"Discovery Picks count: {len(picks)}")
        for i, b in enumerate(picks):
            print(f"  {i+1}. {b.get('title')} by {b.get('author')} (Source: {b.get('source')})")

        print("\n--- Testing get_author_books ---")
        author = "Agatha Christie"
        auth_books = get_author_books(author, limit=5)
        print(f"Books by {author}: {len(auth_books)}")
        for b in auth_books:
            print(f"  - {b.get('title')}")

        print("\n--- Testing rerank_search_results ---")
        # Try to find a user with preferences
        pref = UserPreference.query.first()
        if pref:
            user_id = pref.user_id
            topics = [p.topic for p in UserPreference.query.filter_by(user_id=user_id).all()]
            print(f"User ID: {user_id}, Preferences: {topics}")
            mock_results = [
                {"id": "1", "title": "History of World", "author": "X", "categories": ["History"]},
                {"id": "2", "title": "Python Programming", "author": "Y", "categories": ["Programming"]},
                {"id": "3", "title": "Modern Art", "author": "Z", "categories": ["Art"]}
            ]
            reranked = rerank_search_results(user_id, mock_results)
            print("Reranked results order:")
            for b in reranked:
                print(f"  - {b.get('title')}")
        else:
            print("No user with preferences found for testing rerank.")
            user_id = None

        print("\n--- Testing get_hybrid_recommendations ---")
        # Find a book from DB
        book = Book.query.first()
        if book:
            print(f"Reference Book: {book.title}")
            recs = get_hybrid_recommendations(user_id, book, limit=5)
            print(f"Hybrid Recommendations count: {len(recs)}")
            for b in recs:
                print(f"  - {b.get('title')} (Reason: {b.get('reason')})")
        else:
            # Try with a mock book
            from types import SimpleNamespace
            mock_book = SimpleNamespace(id=None, google_id="mock_id", title="The Great Gatsby", author="F. Scott Fitzgerald", description="A classic.")
            print(f"Reference Mock Book: {mock_book.title}")
            recs = get_hybrid_recommendations(None, mock_book, limit=5)
            print(f"Hybrid Recommendations (Mock) count: {len(recs)}")
            for b in recs:
                print(f"  - {b.get('title')} (Reason: {b.get('reason')})")


        print("\n--- Testing get_hidden_gems ---")
        gems = get_hidden_gems(limit=5)
        print(f"Hidden Gems count: {len(gems)}")
        for b in gems:
            print(f"  - {b.get('title')} (Reason: {b.get('reason')})")

        print("\n--- Testing get_genre_explorer ---")
        if user_id:
            res = get_genre_explorer(user_id, limit=5)
            if res:
                print(f"Genre Explorer Suggestion: {res.get('genre')}")
                for b in res.get('books', []):
                    print(f"  - {b.get('title')}")
            else:
                print("Genre Explorer returned None")
        else:
            print("Skipping Genre Explorer (no user_id)")

if __name__ == "__main__":
    verify_all()
