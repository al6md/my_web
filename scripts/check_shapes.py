import os
import sys
import pickle

sys.path.append(os.getcwd())
from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import BookEmbedding

app = create_app()
with app.app_context():
    rows = BookEmbedding.query.all()
    shapes = {}
    for be in rows:
        try:
            if be.vector:
                v = pickle.loads(be.vector)
                s = getattr(v, 'shape', str(type(v)))
                shapes[s] = shapes.get(s, 0) + 1
                if str(s) != '(384,)':
                    print(f"Mismatch: Book {be.book_id} has shape {s}")
        except Exception as e:
            print(f"Could not parse book {be.book_id}: {e}")

    print("Shape Summary:", shapes)
