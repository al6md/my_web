import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "flask_book_recommendation", "app.db")
print(f"DB path: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path, timeout=2)
cur = conn.cursor()

print("\n=== USERS ===")
cur.execute("SELECT id, name, email, onboarding_completed FROM users")
users = cur.fetchall()
for u in users:
    print(f"  ID={u[0]}, name='{u[1]}', email='{u[2]}', onboarding={u[3]}")

print("\n=== PREFERENCES PER USER ===")
for u in users:
    uid = u[0]
    cur.execute("SELECT topic, weight FROM user_preferences WHERE user_id=? ORDER BY weight DESC LIMIT 8", (uid,))
    prefs = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM user_preferences WHERE user_id=?", (uid,))
    total = cur.fetchone()[0]
    print(f"  User {uid} ({u[1]}): {total} prefs -> {prefs}")

print("\n=== SEARCH HISTORY PER USER ===")
for u in users:
    uid = u[0]
    cur.execute("SELECT query FROM search_history WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (uid,))
    searches = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM search_history WHERE user_id=?", (uid,))
    total = cur.fetchone()[0]
    print(f"  User {uid} ({u[1]}): {total} searches -> {searches}")

print("\n=== CROSS-USER OVERLAP ===")
user_topics = {}
for u in users:
    uid = u[0]
    cur.execute("SELECT topic FROM user_preferences WHERE user_id=?", (uid,))
    user_topics[uid] = set(r[0].lower() for r in cur.fetchall())

for i in range(len(users)):
    for j in range(i + 1, len(users)):
        u1id, u2id = users[i][0], users[j][0]
        s1 = user_topics.get(u1id, set())
        s2 = user_topics.get(u2id, set())
        shared = s1 & s2
        if s1 or s2:
            pct = len(shared) / max(len(s1 | s2), 1) * 100
            print(f"  {u1id} vs {u2id}: {len(shared)} shared / ({len(s1)},{len(s2)}) = {pct:.0f}%")

conn.close()
print("\nDone!")
