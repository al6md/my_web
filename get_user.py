from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import User
from flask_book_recommendation.extensions import db

app = create_app()
with app.app_context():
    user = User.query.first()
    if user:
        print(f"FIRST_USER_ID:{user.id}")
    else:
        print("NO_USERS_FOUND")
