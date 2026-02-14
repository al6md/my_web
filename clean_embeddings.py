import sys
import os

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import BookEmbedding

def clean_embs():
    app = create_app()
    with app.app_context():
        print("Cleaning all embeddings...")
        deleted = db.session.query(BookEmbedding).delete()
        db.session.commit()
        print(f"Deleted {deleted} embeddings. Ready for regeneration.")

if __name__ == "__main__":
    clean_embs()
