
import os
import sys
import logging

sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from ai_book_recommender.unified_pipeline import UnifiedRecommendationPipeline
from flask_book_recommendation.models import User

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("VerifyPersonas")

PERSONAS = [
    {"name": "Tech Geek", "email": "tech.geek@example.com"},
    {"name": "Romantic Dreamer", "email": "romantic.dreamer@example.com"},
    {"name": "Historian", "email": "historian@example.com"}
]

def verify_personas():
    app = create_app()
    with app.app_context():
        # Initialize pipeline and MANUALLY set flask_app to enable deep retrieval
        engine = UnifiedRecommendationPipeline(load_all_models=True)
        engine.flask_app = app
        
        logger.info("\n========== 🧠 AI RECOMMENDATION VERIFICATION ==========\n")
        
        for p in PERSONAS:
            user = User.query.filter_by(email=p['email']).first()
            if not user:
                logger.error(f"User {p['name']} not found!")
                continue
                
            logger.info(f"--- 👤 Persona: {p['name']} (ID: {user.id}) ---")
            
            # Fetch "Recommended For You" (Full Stack / Hybrid Graph + Neural)
            recs = engine.recommend_full_stack(user_id=user.id, top_k=5)
            
            if not recs:
                logger.info("   No recommendations generated.")
            else:
                for i, r in enumerate(recs, 1):
                    # Safely handle attributes vs dictionary keys depending on what engine returns
                    title = r.get('title', 'Unknown') if isinstance(r, dict) else getattr(r, 'title', 'Unknown')
                    cat = r.get('categories', '') if isinstance(r, dict) else getattr(r, 'categories', '')
                    logger.info(f"   {i}. {title} [{cat}]")
            logger.info("")

if __name__ == "__main__":
    verify_personas()
