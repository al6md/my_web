
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask
from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import User, UserPreference, UserGenre, Genre, Book
from flask_book_recommendation.recommender import get_behavior_based_recommendations

def verify_cold_start():
    app = create_app()
    with app.app_context():
        print("🚀 Starting Cold Start Verification")
        
        # 1. Create a dummy test user
        email = "test_cold_start@example.com"
        user = User.query.filter_by(email=email).first()
        if user:
            # Clean up previous test
            db.session.delete(user)
            db.session.commit()
            
        user = User(name="Test User", email=email, password_hash="dummy")
        db.session.add(user)
        db.session.commit()
        print(f"✅ Created fresh user: {user.id}")
        
        # Cleanup potential orphans (if ID reused)
        UserPreference.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        
        # 2. Add Interest (e.g., 'Artificial Intelligence')
        # Use a topic that we know exists in our books
        topic = "Machine Learning" 
        print(f"👉 Setting interest: {topic}")
        
        # Simulate API logic
        db.session.add(UserPreference(user_id=user.id, topic=topic, weight=2.0))
        db.session.commit()
        
        # 3. Get Recommendations
        print("🔄 Fetching recommendations...")
        recs = get_behavior_based_recommendations(user.id, limit=5, offset=0)
        
        # 4. Verify
        print(f"📚 Got {len(recs)} recommendations")
        
        match_count = 0
        for b in recs:
            print(f"   - {b['title']} (Reason: {b.get('reason','')})")
            # Check if title or description relates to topic
            txt = (b['title'] + " " + (b.get('description') or "")).lower()
            if "machine" in txt or "learning" in txt or "ai" in txt or "intelligence" in txt:
                match_count += 1
                
        if match_count > 0:
            print(f"✅ SUCCESS: {match_count}/5 books match '{topic}'")
        else:
            print(f"❌ FAILURE: No books matched '{topic}'. System might be ignoring explicit interests.")
            
        # Cleanup
        db.session.delete(user)
        db.session.commit()

if __name__ == "__main__":
    verify_cold_start()
