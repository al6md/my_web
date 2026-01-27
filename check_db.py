
import sqlite3
import os

db_path = os.path.join("flask_book_recommendation", "app.db")
print(f"Checking database at: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables found:")
    for t in tables:
        print(f"- {t[0]}")
    
    # Check explicitly for users
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    if columns:
        print("\nColumns in 'users' table:")
        for c in columns:
            print(f"- {c[1]} ({c[2]})")
    else:
        print("\nTable 'users' NOT found or empty schema info.")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
