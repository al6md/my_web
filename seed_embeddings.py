import numpy as np
from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import Book, BookEmbedding
from flask_book_recommendation.extensions import db

app = create_app()

def seed_dummy_embeddings():
    with app.app_context():
        books = Book.query.all()
        print(f"Found {len(books)} books. Checking embeddings...")
        
        count = 0
        for book in books:
            # Check if exists
            exists = BookEmbedding.query.filter_by(book_id=book.id).first()
            if not exists:
                # Create dummy vector (768 dim)
                vec = np.random.randn(768).astype(np.float32)
                
                new_emb = BookEmbedding(
                    book_id=book.id,
                    vector=vec
                )
                db.session.add(new_emb)
                count += 1
                
        db.session.commit()
        print(f"✅ Created {count} new dummy embeddings.")

if __name__ == "__main__":
    seed_dummy_embeddings()
