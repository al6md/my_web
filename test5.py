import sqlite3
import pickle
import numpy as np
def check():
    conn = sqlite3.connect('flask_book_recommendation/app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT vector FROM book_embeddings LIMIT 5;')
    for row in cursor.fetchall():
        vec = row[0]
        if isinstance(vec, bytes):
            vec = pickle.loads(vec)
        arr = np.asarray(vec, dtype=np.float32)
        print("Shape:", arr.shape)
    conn.close()

if __name__ == '__main__':
    check()
