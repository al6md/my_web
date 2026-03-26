import os
import sys

# Add the project root to the path
project_root = os.path.abspath(os.path.join(os.getcwd(), ".."))
sys.path.append(project_root)

from flask_book_recommendation_starter.flask_book_recommendation import create_app
from flask_book_recommendation_starter.flask_book_recommendation.extensions import db
from flask_book_recommendation_starter.flask_book_recommendation.models import Book

app = create_app()

with app.app_context():
    # Find all books with via.placeholder.com in their cover or cover_url
    books_to_fix = Book.query.filter(
        (Book.cover.like("%via.placeholder.com%")) | 
        (Book.cover_url.like("%via.placeholder.com%"))
    ).all()
    
    print(f"Found {len(books_to_fix)} books with via.placeholder.com URLs.")
    
    count = 0
    for book in books_to_fix:
        if book.cover and "via.placeholder.com" in book.cover:
            book.cover = book.cover.replace("via.placeholder.com", "placehold.co")
            count += 1
        if book.cover_url and "via.placeholder.com" in book.cover_url:
            book.cover_url = book.cover_url.replace("via.placeholder.com", "placehold.co")
            count += 1
            
    db.session.commit()
    print(f"Successfully fixed {count} URLs in the database.")
    
    # Also, check if any books have NO cover and set a placeholder
    books_no_cover = Book.query.filter(
        (Book.cover == None) & (Book.cover_url == None)
    ).all()
    print(f"Found {len(books_no_cover)} books with NO cover.")
