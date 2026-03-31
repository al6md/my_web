import sqlite3
def check():
    conn = sqlite3.connect('flask_book_recommendation/app.db')
    cursor = conn.cursor()
    # Get top 5 popular books
    cursor.execute("SELECT id FROM books LIMIT 10;")
    bids = [row[0] for row in cursor.fetchall()]
    print("Popular Book IDs:", bids)
    
    # Check embeddings
    if bids:
        placeholders = ','.join(['?'] * len(bids))
        cursor.execute(f"SELECT book_id FROM book_embeddings WHERE book_id IN ({placeholders});", bids)
        emb_bids = [row[0] for row in cursor.fetchall()]
        print("Book IDs with Embeddings:", emb_bids)
    
    conn.close()

if __name__ == '__main__':
    check()
