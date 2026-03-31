import sqlite3
def check():
    conn = sqlite3.connect('instance/app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM books WHERE title LIKE '%فضاء%' LIMIT 5;")
    print("Space books:", cursor.fetchall())
    
    cursor.execute("SELECT id, query FROM search_history ORDER BY id DESC LIMIT 5;")
    print("Recent Searches:", cursor.fetchall())
    conn.close()

if __name__ == '__main__':
    check()
