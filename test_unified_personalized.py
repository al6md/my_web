import sys
import os
import time

# Add project root to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, User, Genre, UserGenre, SearchHistory
from ai_book_recommender.unified_pipeline import get_unified_engine

app = create_app()

def setup_test_data(user_id=1):
    print(f"--- Setting up test data for User ID {user_id} ---")
    with app.app_context():
        user = User.query.get(user_id)
        if not user:
            print(f"User {user_id} not found, creating placeholder...")
            user = User(id=user_id, name="Test User", email=f"test{user_id}@example.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()

        # 1. Clear existing interests and set to "Programming"
        print("Setting interests to 'Computers' and 'Technology'...")
        UserGenre.query.filter_by(user_id=user_id).delete()
        
        comp_genre = Genre.query.filter_by(name="Computers").first()
        if not comp_genre:
            comp_genre = Genre(name="Computers")
            db.session.add(comp_genre)
            db.session.commit()
            
        tech_genre = Genre.query.filter_by(name="Technology").first()
        if not tech_genre:
            tech_genre = Genre(name="Technology")
            db.session.add(tech_genre)
            db.session.commit()

        db.session.add(UserGenre(user_id=user_id, genre_id=comp_genre.id))
        db.session.add(UserGenre(user_id=user_id, genre_id=tech_genre.id))
        db.session.commit()

        # 2. Add search history for "History"
        print("Adding search history for 'Ancient History'...")
        search = SearchHistory(user_id=user_id, query="Ancient History")
        db.session.add(search)
        db.session.commit()

def run_test(user_id=1):
    print(f"\n--- Running Unified Pipeline for User ID {user_id} ---")
    with app.app_context():
        engine = get_unified_engine()
        engine.flask_app = app
        
        start = time.time()
        results = engine.recommend_full_stack(user_id=user_id, top_k=20)
        elapsed = time.time() - start
        
        print(f"Pipeline completed in {elapsed:.2f}s. Received {len(results)} results.")
        
        interest_matches = 0
        search_matches = 0
        random_books = 0
        
        for i, r in enumerate(results):
            title = r.get('title', 'Unknown')
            author = r.get('author', 'Unknown')
            # In unified pipeline output, categories might be in '_raw' or 'categories'
            cats = r.get('categories', [])
            if not cats and '_raw' in r:
                 # Check if it was Book object dict or external
                 raw = r['_raw']
                 if isinstance(raw, dict):
                     cats = raw.get('categories', [])
            
            cats_str = ",".join(cats) if isinstance(cats, list) else str(cats)
            
            is_interest = any(kw in cats_str.lower() for kw in ["computer", "tech", "program", "code"])
            is_search = "history" in cats_str.lower() or "history" in title.lower()
            
            label = ""
            if is_interest: 
                label += "[INTEREST] "
                interest_matches += 1
            if is_search: 
                label += "[SEARCH] "
                search_matches += 1
            
            if not is_interest and not is_search:
                label += "[? RANDOM ?] "
                random_books += 1
                
            print(f"{i+1}. {label}{title} - {author} ({cats_str})")
            
        print(f"\n--- Summary ---")
        print(f"Interest Matches: {interest_matches}")
        print(f"Search Matches: {search_matches}")
        print(f"Random/Unclear: {random_books}")
        print(f"Total: {len(results)}")
        
        if random_books > 5 and len(results) > 10:
            print("\nWARNING: Too many random books! Purge might be failing.")
        else:
            print("\nSUCCESS: Recommendations appear focused on interests and behavior.")

if __name__ == "__main__":
    setup_test_data()
    run_test()
