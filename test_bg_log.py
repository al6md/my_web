from flask_book_recommendation.app import create_app
from flask_book_recommendation.routes.public import background_log_search, background_record_feedback

app = create_app()

print("DB URI:", app.config['SQLALCHEMY_DATABASE_URI'])

print("Testing background_log_search...")
background_log_search(app, 1, "فضاء")

print("Finished Testing background_log_search.")
