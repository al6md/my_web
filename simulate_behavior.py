
import sys
import os
from datetime import datetime

# إضافة مسار المشروع
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, UserBookView
from flask_book_recommendation.utils import get_ai_personalized_recommendations, update_user_preferences_from_behavior

app = create_app()

def simulate_behavior():
    with app.app_context():
        # 1. Get or Create a test user
        user = User.query.filter_by(email="test@example.com").first()
        if not user:
            print("Creating test user...")
            user = User(name="TestUser", email="test@example.com")
            user.password_hash = "scrypt:..."  # Mock hash or use set_password properly
            # better to just set a dummy hash for simulation
            db.session.add(user)
            db.session.commit()
        
        print(f"Using User: {user.name} (ID: {user.id})")
        
        # 2. Simulate viewing some books (e.g., Python/AI)
        # using fake google_ids for real books (or semi-real)
        # "Python Crash Course" - id: "N7xQAQAAQBAJ" (example, random string)
        # Actually let's use some known topic keywords to fake the "info"
        
        books_to_view = [
            {"title": "Python for Data Science", "author": "Jake VanderPlas", "categories": ["Computers", "Data"], "id": "python_1"},
            {"title": "Hands-On Machine Learning", "author": "Aurélien Géron", "categories": ["Computers", "AI"], "id": "ai_1"},
            {"title": "Deep Learning", "author": "Ian Goodfellow", "categories": ["Computers", "AI"], "id": "ai_2"}
        ]
        
        print("\n👀 Simulating views...")
        for b in books_to_view:
            # Add to UserBookView
            view = UserBookView.query.filter_by(user_id=user.id, google_id=b["id"]).first()
            if not view:
                view = UserBookView(user_id=user.id, google_id=b["id"], view_count=1)
                db.session.add(view)
            else:
                view.view_count += 1
            
            # Update preferences
            update_user_preferences_from_behavior(user.id, "view", b)
            print(f"  - Viewed: {b['title']}")
            
        db.session.commit()
        
        # 3. Test Recommendations
        print("\n🤖 Generating AI Recommendations...")
        result = get_ai_personalized_recommendations(user.id, limit=5)
        
        if result.get("success"):
            print("\n✅ Success!")
            print(f"AI Analysis: {result.get('ai_analysis')}")
            print("Suggested Topics:", result.get("suggested_topics"))
            print("Books Found:")
            for b in result.get("books", []):
                print(f"  - {b['title']} ({b['reason']})")
        else:
            print("\n❌ Failed:")
            print(result.get("error"))
            print(result.get("ai_analysis"))

if __name__ == "__main__":
    simulate_behavior()
