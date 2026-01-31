from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import get_deep_learning_recommendations
from flask_book_recommendation.models import User

app = create_app()

def verify_dl():
    with app.app_context():
        # Get a test user (User ID 1 or first available)
        user = User.query.first()
        if not user:
            print("❌ No users found in database to test with.")
            return

        print(f"\n🔍 Testing Deep Learning Recommendations for User: {user.name} (ID: {user.id})")
        print("="*60)
        
        # Call the new function
        recs = get_deep_learning_recommendations(user.id, limit=5)
        
        if not recs:
            print("⚠️ No recommendations returned. (Check if model is trained or needs more data)")
        else:
            print(f"✅ Success! Generated {len(recs)} recommendations:\n")
            for i, book in enumerate(recs, 1):
                print(f"{i}. {book['title']}")
                print(f"   Reason: {book.get('reason')}")
                print("-" * 30)

if __name__ == "__main__":
    verify_dl()
