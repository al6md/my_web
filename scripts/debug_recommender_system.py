
import sys
import os
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, SearchHistory, UserPreference
from flask_book_recommendation.recommender import get_last_search_recommendations, get_homepage_sections

app = create_app()

def debug_recommendations():
    with app.app_context():
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns_info = inspector.get_columns('search_history')
        print(f"Table 'search_history' columns info:")
        for c in columns_info:
            print(f" - {c['name']}: nullable={c['nullable']}")
        
        columns = [c['name'] for c in columns_info]
        
        if 'query' not in columns and 'search_term' not in columns:
            print("CRITICAL: Neither 'query' nor 'search_term' column exists!")

        # Get the first user (usually the one being tested)
        user = User.query.first()
        if not user:
            print("No users found in database.")
            return

        print(f"--- Debugging for User: {user.name} (ID: {user.id}) ---")

        # 0. Simulate a NEW search
        print("\n[0] Simulating search for 'Python'...")
        try:
            from datetime import datetime
            new_search = SearchHistory(
                user_id=user.id,
                query="Python",
                created_at=datetime.utcnow()
            )
            db.session.add(new_search)
            db.session.commit()
            print("   SUCCESS: Inserted fake search for 'Python'")
        except Exception as e:
            db.session.rollback()
            print(f"   FAILED to insert: {e}")

        # 1. Check Search History
        print("\n[1] Checking Last 5 Search History Entries:")
        history = (
            db.session.query(SearchHistory)
            .filter_by(user_id=user.id)
            .order_by(SearchHistory.created_at.desc())
            .limit(5)
            .all()
        )
        
        if not history:
            print("   NO SEARCH HISTORY FOUND!")
        else:
            for h in history:
                # Handle 'query' or 'search_term' attribute dynamically in case of schema confusion
                q_val = getattr(h, 'query', getattr(h, 'search_term', 'UNKNOWN_ATTR'))
                print(f"   - ID: {h.id}, Query: '{q_val}', Time: {h.created_at}")

        # 2. Check User Preferences
        print("\n[2] Checking Top 5 User Preferences:")
        prefs = (
            UserPreference.query
            .filter_by(user_id=user.id)
            .order_by(UserPreference.weight.desc())
            .limit(5)
            .all()
        )
        for p in prefs:
            print(f"   - Topic: '{p.topic}', Weight: {p.weight}")

        # 3. Test get_last_search_recommendations
        print("\n[3] Testing get_last_search_recommendations...")
        try:
            query_text, books = get_last_search_recommendations(user.id, limit=3)
            print(f"   Query Text: {query_text}")
            if books:
                print(f"   Found {len(books)} books.")
                for b in books:
                    print(f"      * {b.get('title')} ({b.get('reason')})")
            else:
                print("   NO BOOKS RETURNED.")
        except Exception as e:
            print(f"   CRASHED: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_recommendations()
