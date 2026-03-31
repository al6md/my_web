from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import Book, BookEmbedding

app = create_app()

with app.app_context():
    books = Book.query.count()
    embs = BookEmbedding.query.count()
    print(f'DB BOOKS: {books}')
    print(f'DB EMBEDDINGS: {embs}')
