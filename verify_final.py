import sys
import os

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import BookEmbedding
from flask_book_recommendation.recommender import get_deep_learning_recommendations

def verify():
    app = create_app()
    with app.app_context():
        count = BookEmbedding.query.count()
        print(f"Final Embedding Count: {count}")
        
        if count > 0:
            print("Testing Recommender...")
            try:
                # Use user_id=1
                recs = get_deep_learning_recommendations(user_id=1, limit=5, randomize=False)
                print(f"Transformer Results: {len(recs)}")
                for r in recs:
                    print(f" - {r.get('title')} ({r.get('source')})")
            except Exception as e:
                print(f"Recommender Error: {e}")
        else:
            print("Still no embeddings!")

if __name__ == "__main__":
    verify()
