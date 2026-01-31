
import sys
import os

# Adjust path to import from the package
sys.path.append(os.getcwd())


from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.recommender import get_behavior_based_recommendations
from flask_book_recommendation.models import User

app = create_app()

def test_recommendations(user_id=1):
    with app.app_context():
        print(f"\n--- Testing for User ID: {user_id} ---")
        user = User.query.get(user_id)
        if not user:
            print(f"User {user_id} not found!")
            return

        print(f"User found: {user.name} (ID: {user.id})")
        
        # Test the function
        try:
            recs = get_behavior_based_recommendations(user_id, limit=12)
            print(f"\nResult: Found {len(recs)} recommendations.")
            for r in recs:
                print(f" - {r.get('title')} ({r.get('rec_type')})")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        uid = int(sys.argv[1])
    else:
        uid = 1
    test_recommendations(uid)
