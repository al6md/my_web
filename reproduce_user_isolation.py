import os
import sys
# Add current directory to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, SearchHistory, UserPreference
from flask_book_recommendation.recommender import get_topic_based, get_last_search_recommendations
import random

app = create_app()

def cleanup_test_data(user_emails):
    with app.app_context():
        for email in user_emails:
            u = User.query.filter_by(email=email).first()
            if u:
                db.session.query(SearchHistory).filter_by(user_id=u.id).delete()
                UserPreference.query.filter_by(user_id=u.id).delete()
                db.session.delete(u)
        db.session.commit()

def create_test_user(name, email, topic, queries):
    u = User(name=name, email=email, password_hash="dummy")
    db.session.add(u)
    db.session.commit()
    
    # Add prefs
    p = UserPreference(user_id=u.id, topic=topic, weight=5.0)
    db.session.add(p)
    
    # Add search history
    for q in queries:
        sh = SearchHistory(user_id=u.id, query=q)
        db.session.add(sh)
    db.session.commit()
    return u.id

def run_test():
    with app.app_context():
        email1 = "test_iso_1@example.com"
        email2 = "test_iso_2@example.com"
        cleanup_test_data([email1, email2])
        
        print("Creating User 1 (Topic: Python, Search: machine learning)")
        uid1 = create_test_user("User1", email1, "Python", ["machine learning"])
        
        print("Creating User 2 (Topic: Cooking, Search: italian recipes)")
        uid2 = create_test_user("User2", email2, "Cooking", ["italian recipes"])
        
        # Test Topic Based
        print("\n--- Testing Interest Match ---")
        res1_topic = get_topic_based(uid1, limit=5, randomize=False)
        res2_topic = get_topic_based(uid2, limit=5, randomize=False)
        
        books1 = [b['title'] for b in res1_topic.get('books', [])]
        books2 = [b['title'] for b in res2_topic.get('books', [])]
        
        print(f"User 1 Interests Recs: {books1}")
        print(f"User 2 Interests Recs: {books2}")
        
        if set(books1) == set(books2) and books1:
            print("FAIL: Interest Match returned identical books!")
        else:
            print("PASS: Interest Match returned different books.")

        # Test Search History
        print("\n--- Testing Search History ---")
        q1, res1_search = get_last_search_recommendations(uid1, limit=5, randomize=False)
        q2, res2_search = get_last_search_recommendations(uid2, limit=5, randomize=False)
        
        print(f"User 1 Search Query: {q1}")
        print(f"User 2 Search Query: {q2}")
        
        if str(q1).lower() == str(q2).lower():
             print("FAIL: Search Query is identical!")
        elif "machine learning" not in str(q1).lower():
             print(f"FAIL: User 1 query expected 'machine learning', got '{q1}'")
        elif "italian recipes" not in str(q2).lower():
             print(f"FAIL: User 2 query expected 'italian recipes', got '{q2}'")
        else:
             print("PASS: Search Query logic seems correct.")

        cleanup_test_data([email1, email2])

if __name__ == "__main__":
    run_test()
