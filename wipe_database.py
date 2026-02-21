import sqlite3
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "flask_book_recommendation", "app.db")

print(f"Connecting to {db_path}...")
if not os.path.exists(db_path):
    print("Database not found!")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Get all table names
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cur.fetchall()]

# Tables to NOT delete because they manage the schema or internal sqlite state
exclude_tables = ['sqlite_sequence', 'alembic_version']

print(f"Found {len(tables)} tables.")

for table in tables:
    if table in exclude_tables:
        print(f"Skipping internal table: {table}")
        continue
    
    print(f"Cleaning table: {table}...")
    try:
        cur.execute(f"DELETE FROM {table};")
        print(f"  - Table {table} cleared.")
    except Exception as e:
        print(f"  - Error cleaning {table}: {e}")

# Commit deletions before vacuuming or doing other non-transactional work
conn.commit()

# Reset auto-increment counters
print("Resetting auto-increment counters...")
try:
    # Check if table exists first
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';")
    if cur.fetchone():
        cur.execute("DELETE FROM sqlite_sequence;")
        print("  - Counters reset.")
    else:
        print("  - sqlite_sequence table does not exist, skipping.")
except Exception as e:
    print(f"  - Error resetting counters: {e}")

conn.commit()

# Compact the database (must be outside transaction)
print("Vacuuming database...")
try:
    conn.isolation_level = None # set to autocommit for vacuum
    conn.execute("VACUUM;")
    conn.isolation_level = "" # restore default
    print("  - Database vacuumed.")
except Exception as e:
    print(f"  - Error vacuuming: {e}")

conn.close()

print("\nDatabase cleaning complete! Everything is now fresh.")
