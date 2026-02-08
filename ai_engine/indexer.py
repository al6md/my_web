import sqlite3
import numpy as np
from .config import settings
from .embeddings import embedding_service
from .retrieval import RetrievalEngine

def fetch_books_from_db():
    # Connect to the SQLite DB directly
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    # Check if path is relative, make it absolute based on assumptions if needed
    # Assuming app.db is in flask_book_recommendation/app.db or root
    # Based on file list: flask_book_recommendation/app.db
    
    # We try to locate the DB
    possible_paths = [
        "flask_book_recommendation/app.db",
        "../flask_book_recommendation/app.db",
        "app.db"
    ]
    
    conn = None
    for p in possible_paths:
        if os.path.exists(p):
            conn = sqlite3.connect(p)
            print(f"Connected to DB at {p}")
            break
            
    if not conn:
        print("Warning: Database not found. Creating dummy data for index.")
        return [], []

    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, author FROM books")
    rows = cursor.fetchall()
    conn.close()
    
    ids = []
    texts = []
    for r in rows:
        bid, title, desc, author = r
        # Semantic representation: Title + Author + Description
        text = f"{title} by {author}. {desc or ''}"
        ids.append(bid)
        texts.append(text)
        
    return ids, texts

def build_core_index():
    print("Fetching books...")
    ids, texts = fetch_books_from_db()
    
    if not ids:
        print("No books found to index.")
        return

    print(f"Encoding {len(texts)} books... (This may take a while locally)")
    embeddings = embedding_service.encode(texts)
    
    print("Building FAISS index...")
    retriever = RetrievalEngine()
    retriever.build_index(embeddings, ids)
    print("Index build complete.")

if __name__ == "__main__":
    import os
    build_core_index()
