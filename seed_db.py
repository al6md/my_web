import sys
import os
import random
from sentence_transformers import SentenceTransformer

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import Book, BookEmbedding
from flask_book_recommendation.utils import fetch_google_books

def seed_database():
    app = create_app()
    with app.app_context():
        print("--- initializing Seeding ---")
        
        # queries to fetch
        queries = [
            "Cristiano Ronaldo",
            "Lionel Messi", # Related
            "Football Biographies",
            "Best Sellers 2024",
            "Artificial Intelligence", # General interest
            "Psychology of Success"
        ]
        
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Model loaded.")
        
        total_added = 0
        
        for q in queries:
            print(f"Fetching books for: {q}...")
            # Fetch 40 books per query (max allowed by Google API one shot usually)
            books_data, _ = fetch_google_books(q, max_results=40)
            
            if not books_data:
                print(f"No books found for {q}")
                continue
                
            print(f"Found {len(books_data)} books for {q}. Processing...")
            
            for b_data in books_data:
                gid = b_data.get('id')
                title = b_data.get('volumeInfo', {}).get('title')
                if not gid or not title:
                    continue
                    
                # Check exist
                existing = Book.query.filter_by(google_id=gid).first()
                if existing:
                    # Check embedding
                    if not BookEmbedding.query.filter_by(book_id=existing.id).first():
                        # Create embedding only
                        desc = existing.description or existing.title
                        vec = model.encode(desc).tolist()
                        emb = BookEmbedding(book_id=existing.id, vector=vec)
                        db.session.add(emb)
                        print(f" + Added missing embedding for {title}")
                    continue
                
                # Create Book
                vi = b_data.get('volumeInfo', {})
                desc = vi.get('description', '')
                authors = ", ".join(vi.get('authors', []))
                cover = (vi.get('imageLinks') or {}).get('thumbnail', '').replace('http://', 'https://')
                
                new_book = Book(
                    title=title,
                    author=authors,
                    description=desc,
                    cover_url=cover,
                    google_id=gid,
                    publisher=vi.get('publisher'),
                    published_date=vi.get('publishedDate'),
                    page_count=vi.get('pageCount'),
                    language=vi.get('language'),
                    # We link them to NO owner, or a system admin owner if needed.
                    # For now, owner_id=None means "System/Public Book" usually, 
                    # but trending logic filters for owner_id.isnot(None).
                    # Transformer uses ALL books or User books?
                    # Transformer recommender uses `Book.query` usually?
                    # Let's check recommender. logic.
                    # It uses embeddings.
                )
                
                # To make them appear in "Trending" (which user likes?), they need an owner?
                # User asked for "New books of same type".
                # Transformer recommends based on embeddings from ALL books in DB ideally.
                # Let's add them as NULL owner first.
                
                db.session.add(new_book)
                db.session.flush() # to get ID
                
                # Create Embedding
                text_to_embed = f"{title} {authors} {desc}"
                vec = model.encode(text_to_embed).tolist()
                
                emb = BookEmbedding(book_id=new_book.id, vector=vec)
                db.session.add(emb)
                
                total_added += 1
                if total_added % 10 == 0:
                    print(f"Saved {total_added} books...")
                    db.session.commit()
            
            db.session.commit()
            
        print(f"--- Seeding Complete. Added {total_added} new books. ---")

if __name__ == "__main__":
    seed_database()
