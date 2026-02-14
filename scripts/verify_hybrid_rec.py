from flask import Flask
from flask_book_recommendation.app import create_app, db
from flask_book_recommendation.models import User
from flask_book_recommendation.recommender import get_behavior_based_recommendations

app = create_app()

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


with app.app_context():
    # Helper to get a user
    user = User.query.first()
    if not user:
        print("No users found.")
        exit()

    print(f"Testing Hybrid Recommendations for User: {user.name} (ID: {user.id})")
    
    # Call the function
    try:
        recs = get_behavior_based_recommendations(user.id, limit=10, randomize=True)
        print(f"\n--- Hybrid Recommendations ({len(recs)}) ---")
        for i, book in enumerate(recs):
            print(f"{i+1}. {book.get('title')} (Source: {book.get('source')}) - Reason: {book.get('reason')}")
            
    except Exception as e:
        print(f"Error calling hybrid algorithm: {e}")
