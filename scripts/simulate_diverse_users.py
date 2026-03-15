
import os
import sys
import logging
import random

# Add project root to path
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("SimulatePersonas")

PERSONAS = [
    {
        "name": "Tech Geek",
        "email": "tech.geek@example.com",
        "keywords": ["Programming", "Artificial Intelligence", "Cybersecurity", "Python", "Data"]
    },
    {
        "name": "Romantic Dreamer",
        "email": "romantic.dreamer@example.com",
        "keywords": ["Romance", "Poetry", "Love Stories", "Fiction"]
    },
    {
        "name": "Historian",
        "email": "historian@example.com",
        "keywords": ["World History", "Biography", "Political Science", "History"]
    }
]

def simulate_personas():
    logger.info("🧪 Generating distinct user personas and highly clustered interactions...")
    app = create_app()
    with app.app_context():
        from flask_book_recommendation.models import User, Book, UserBookView, UserRatingCF, UserPreference
        from werkzeug.security import generate_password_hash
        
        all_books = Book.query.all()
        logger.info(f"Available books in DB: {len(all_books)}")
        
        for p_data in PERSONAS:
            logger.info(f"\n--- Setting up Persona: {p_data['name']} ---")
            
            # 1. Create or get user
            user = User.query.filter_by(email=p_data['email']).first()
            if not user:
                user = User(name=p_data['name'], email=p_data['email'], password_hash=generate_password_hash("password123"))
                db.session.add(user)
                db.session.commit()
                logger.info(f"Created new user: {user.name} (ID: {user.id})")
            else:
                logger.info(f"Using existing user: {user.name} (ID: {user.id})")
                
            # Clear existing data for a clean slate
            UserBookView.query.filter_by(user_id=user.id).delete()
            UserRatingCF.query.filter_by(user_id=user.id).delete()
            UserPreference.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            
            # 2. Find books matching persona keywords
            target_books = []
            for b in all_books:
                cat = b.categories or ""
                if any(kw.lower() in cat.lower() for kw in p_data['keywords']):
                    target_books.append(b)
            
            logger.info(f"Found {len(target_books)} matching books for this persona.")
            
            if not target_books:
                logger.warning(f"No books found for {p_data['name']}. Skipping.")
                continue
                
            # 3. Generate hyper-focused interactions
            # We want strong signals. High views, 5-star ratings for ONLY these books.
            num_interact = min(25, len(target_books))
            interact_books = random.sample(target_books, num_interact)
            
            for b in interact_books:
                if not b.google_id: continue
                
                # High View Count
                view = UserBookView(user_id=user.id, google_id=b.google_id, book_id=b.id, view_count=random.randint(5, 15))
                db.session.add(view)
                
                # 5-Star Rating
                rating = UserRatingCF.query.filter_by(user_id=user.id, google_id=b.google_id).first()
                if not rating:
                    rating = UserRatingCF(user_id=user.id, google_id=b.google_id, rating=5.0)
                    db.session.add(rating)
                else:
                    rating.rating = 5.0
                
                # Explicit Preferences (from Online Learner logic)
                for kw in p_data['keywords']:
                    if kw.lower() in (b.categories or "").lower():
                        pref = UserPreference.query.filter_by(user_id=user.id, topic=kw).first()
                        if not pref:
                            pref = UserPreference(user_id=user.id, topic=kw, weight=1.0)
                            db.session.add(pref)
                        else:
                            pref.weight += 1.0
            
            db.session.commit()
            logger.info(f"✅ Simulated {num_interact} deep interactions for {user.name}.")

if __name__ == "__main__":
    simulate_personas()
    logger.info("\n🎉 Persona simulation complete!")
