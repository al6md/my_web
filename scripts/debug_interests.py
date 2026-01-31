"""
Debug script to check interests and API calls
"""
import sys
sys.path.insert(0, '.')

from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import UserPreference, SearchHistory
from flask_book_recommendation.recommender import get_topic_based

app = create_app()
with app.app_context():
    # Get all user preferences
    print("=" * 50)
    print("USER PREFERENCES:")
    print("=" * 50)
    prefs = UserPreference.query.order_by(UserPreference.weight.desc()).limit(15).all()
    if not prefs:
        print("  No preferences found!")
    for p in prefs:
        print(f"  User {p.user_id}: '{p.topic}' (weight: {p.weight})")
    
    # Get search history
    print("\n" + "=" * 50)
    print("SEARCH HISTORY:")
    print("=" * 50)
    searches = SearchHistory.query.order_by(SearchHistory.created_at.desc()).limit(5).all()
    if not searches:
        print("  No search history found!")
    for s in searches:
        print(f"  User {s.user_id}: '{s.query}' at {s.created_at}")
    
    # Test get_topic_based for user 1
    print("\n" + "=" * 50)
    print("TESTING get_topic_based for user 1:")
    print("=" * 50)
    try:
        result = get_topic_based(user_id=1, limit=6, offset=0)
        if isinstance(result, dict):
            books = result.get('books', [])
            exhausted = result.get('interests_exhausted', False)
            print(f"  Exhausted: {exhausted}")
            print(f"  Found {len(books)} books:")
            for b in books[:5]:
                print(f"    - ID: {b.get('id')}")
                print(f"      Title: {b.get('title')}")
                print(f"      Author: {b.get('author')}")
                print(f"      Source: {b.get('source')}")
                print()
        else:
            print(f"  Got list: {len(result)} books")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nDone!")
