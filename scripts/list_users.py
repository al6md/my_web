import sqlite3

conn = sqlite3.connect('flask_book_recommendation/app.db')
cursor = conn.cursor()

# Count users
cursor.execute('SELECT COUNT(*) FROM users')
count = cursor.fetchone()[0]
print(f"\nTotal users in database: {count}\n")

# List users
cursor.execute('SELECT id, name, email FROM users ORDER BY id DESC LIMIT 15')
rows = cursor.fetchall()

if rows:
    print("Users:")
    for r in rows:
        print(f"  ID: {r[0]}, Name: {r[1]}, Email: {r[2]}")
else:
    print("No users found in database!")

# Check if specific email exists
cursor.execute("SELECT * FROM users WHERE email LIKE '%almagd%'")
found = cursor.fetchall()
print(f"\nUsers with 'almagd' in email: {len(found)}")

conn.close()
