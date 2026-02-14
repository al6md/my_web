import sys
import os
import numpy as np

# Setup path
basedir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(basedir)

from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import BookEmbedding

def check_dims():
    app = create_app()
    with app.app_context():
        embs = BookEmbedding.query.all()
        dims = {}
        for e in embs:
            if e.vector:
                l = len(e.vector)
                dims[l] = dims.get(l, 0) + 1
        
        print("Embedding Dimensions Distribution:")
        for d, count in dims.items():
            print(f"Dimension {d}: {count} books")
            
        if len(dims) > 1:
            print("FAIL: Mixed dimensions found!")
        elif 384 not in dims:
             print("WARNING: No 384-dim embeddings found (Required for current model).")

if __name__ == "__main__":
    check_dims()
