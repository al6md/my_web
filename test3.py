import sqlite3
conn = sqlite3.connect('flask_book_recommendation/app.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM book_embeddings;')
print('Total embeddings:', cursor.fetchone()[0])
conn.close()
