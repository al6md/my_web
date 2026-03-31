# final_audit_check.py
import sys
import os
import logging

# Ensure we're in the right directory
sys.path.append(os.getcwd())

from flask_book_recommendation.app import app
from flask_book_recommendation.models import User, Book
from ai_book_recommender.unified_pipeline import UnifiedRecommendationPipeline
from flask_book_recommendation.recommender import (
    get_deep_learning_recommendations,
    get_mood_based_recommendations,
    get_cf_similar,
    get_top_rated
)

# Configure logging to see internal messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FinalAudit")

from flask_book_recommendation.routes.main import _build_featured_lists
from unittest.mock import MagicMock

def run_audit():
    with app.app_context():
        # Using User 100 (Synthetic User from Bootstrap)
        user = User.query.filter_by(email='user100@example.com').first()
        if not user:
            user = User.query.first()
        
        user_id = user.id if user else None
        
        # Mocking current_user for Mood API which uses flask_login proxy
        import flask_login
        original_user = flask_login.current_user
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = user_id
        flask_login.current_user = mock_user

        print(f"\n====================================================")
        print(f"🕵️  FINAL ALGORITHM AUDIT FOR USER: {user_id}")
        print(f"====================================================\n")

        # 1. Test Unified Recommendation Pipeline (The new engine)
        print("Testing UnifiedRecommendationPipeline (The 9-Step Brain)...")
        try:
            engine = UnifiedRecommendationPipeline()
            engine.flask_app = app
            
            methods = {
                "Full Stack (Elite)": engine.recommend_full_stack,
                "Trending For You": engine.recommend_trending,
                "Because You Read": engine.recommend_because_you_read,
                "Top Neural Picks": engine.recommend_top_neural,
                "Graph Discovery": engine.recommend_graph_discovery
            }
            
            for name, func in methods.items():
                try:
                    recs = func(user_id=user_id, top_k=5)
                    count = len(recs)
                    status = "✅ WORKING" if count > 0 else "⚠️ EMPTY (Check data/history)"
                    print(f"  - {name:20}: {status} ({count} items)")
                except Exception as e:
                    print(f"  - {name:20}: ❌ FAILED - {str(e)}")
        except Exception as e:
            print(f"❌ Failed to initialize Unified Pipeline: {e}")

        # 2. Test Secondary Algorithms
        print("\nTesting Secondary & Traditional Algorithms...")
        
        # Two-Tower (Legacy)
        try:
            recs = get_deep_learning_recommendations(user_id, limit=5)
            count = len(recs)
            status = "✅ WORKING" if count > 0 else "⚠️ EMPTY"
            print(f"  - Two-Tower (Legacy) : {status} ({count} items)")
        except Exception as e:
            print(f"  - Two-Tower (Legacy) : ❌ FAILED - {str(e)}")

        # Mood-Based
        try:
            recs = get_mood_based_recommendations(mood_key="happy", limit=5)
            count = len(recs)
            status = "✅ WORKING" if count > 0 else "⚠️ EMPTY"
            print(f"  - Mood-Based AI     : {status} ({count} items)")
        except Exception as e:
            print(f"  - Mood-Based AI     : ❌ FAILED - {str(e)}")

        # Collaborative Filtering
        try:
            recs = get_cf_similar(user_id, top_n=5)
            count = len(recs)
            status = "✅ WORKING" if count > 0 else "⚠️ EMPTY"
            print(f"  - Similar Minds (CF): {status} ({count} items)")
        except Exception as e:
            print(f"  - Similar Minds (CF): ❌ FAILED - {str(e)}")

        # Top Rated (Stats)
        try:
            recs = get_top_rated(limit=5)
            count = len(recs)
            status = "✅ WORKING" if count > 0 else "⚠️ EMPTY"
            print(f"  - Top Rated (Stats) : {status} ({count} items)")
        except Exception as e:
            print(f"  - Top Rated (Stats) : ❌ FAILED - {str(e)}")

        # Featured Lists (Homepage)
        print("\nTesting UI Features...")
        try:
            lists = _build_featured_lists()
            count = len(lists)
            status = "✅ WORKING" if count > 0 else "⚠️ EMPTY"
            print(f"  - Featured Lists    : {status} ({count} categories)")
        except Exception as e:
            print(f"  - Featured Lists    : ❌ FAILED - {str(e)}")

        print(f"\n====================================================")
        print(f"✨ AUDIT COMPLETE")
        print(f"====================================================\n")

if __name__ == '__main__':
    run_audit()
