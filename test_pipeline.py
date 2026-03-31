# test_pipeline.py
import sys
import os

# Ensure we're in the right directory
sys.path.append(os.getcwd())

from flask_book_recommendation.app import app
from flask_book_recommendation.models import User
from ai_book_recommender.unified_pipeline import UnifiedRecommendationPipeline

def test():
    with app.app_context():
        # Get a real user, or dummy user if None
        user = User.query.filter_by(email='user100@example.com').first()
        user_id = user.id if user else None
        print(f"Testing recommendations for User ID: {user_id}")
        
        pipeline = UnifiedRecommendationPipeline()
        pipeline.flask_app = app
        
        # Test full stack recommendation
        recs = pipeline.recommend_full_stack(
            user_id=user_id,
            top_k=5
        )
        
        print(f"\nGot {len(recs)} recommendations:")
        for rec in recs:
            print(f"- Book ID: {rec['book_id']}, Score: {rec['score']:.4f}")

if __name__ == '__main__':
    test()
