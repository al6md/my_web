from flask_book_recommendation.app import create_app
from ai_book_recommender.unified_pipeline import get_unified_engine

app = create_app()

with app.app_context():
    from flask_book_recommendation.recommender.helpers import get_popular_books
    from flask_book_recommendation.models import BookEmbedding
    
    pop_bids = [b.id for b in get_popular_books(app, 500)]
    print(f"Total popular books: {len(pop_bids)}")
    
    rows = BookEmbedding.query.filter(BookEmbedding.book_id.in_(pop_bids)).all()
    print(f"Popular books with embeddings: {len(rows)}")
