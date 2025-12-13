
# User Preferences (Genres) — Integration Guide

This adds a simple **favorite genres** feature using your existing stack (Flask, SQLAlchemy, Flask‑Login, Bootstrap).

## What was added
1. **Models** (`models.py`):
   - `Genre` model
   - Association table `user_genres`
   - Relationship `User.favorite_genres` (dynamic)
2. **Blueprint**: `routes/preferences.py`
   - `GET /preferences/` shows the form
   - `POST /preferences/` saves selections
3. **Template**: `templates/preferences.html`
4. **Navigation**: link added to `Preferences` in `base.html`
5. **Seeding**: `seed_genres.sql` with common genres

## How to apply DB changes (MySQL)
From a MySQL client connected to your `book_recommendation` database:

```sql
-- Create tables if missing (run once)
CREATE TABLE IF NOT EXISTS genres (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(80) UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS user_genres (
  user_id INT NOT NULL,
  genre_id INT NOT NULL,
  PRIMARY KEY (user_id, genre_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
);

-- Seed genres
SOURCE seed_genres.sql;
```

> If you're using `db.create_all()` (already present in `app.py`), the tables will be created automatically based on models. You can still run `seed_genres.sql` to populate sample genres.

## Usage
- Login/Register (existing auth).
- Open **Preferences** from the navbar.
- Select genres and save.
- Access current user preferences from Python:

```python
current_user.favorite_genres.all()         # list of Genre
[g.name for g in current_user.favorite_genres]  # names
```

## Notes
- Keep `SECRET_KEY` secure in `config.py` for production.
- To personalize book lists, filter/boost by `current_user.favorite_genres` in your recommendations.
