from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from sqlalchemy import text
import datetime

app = create_app()
with app.app_context():
    try:
        # إضافة أعمدة جديدة لجدول المستخدمين إذا لم تكن موجودة
        with db.engine.connect() as conn:
            # التحقق من وجود الأعمدة
            inspector = db.inspect(db.engine)
            columns = [c['name'] for c in inspector.get_columns('users')]
            
            new_cols = [
                ('bio', 'TEXT'),
                ('reading_goal', 'INTEGER DEFAULT 0'),
                ('rank', "VARCHAR(50) DEFAULT 'Novice Reader'"),
                ('last_active_date', 'DATE'),
                ('current_streak', 'INTEGER DEFAULT 0')
            ]
            
            for col_name, col_type in new_cols:
                if col_name not in columns:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                    print(f"Added '{col_name}' column.")
            
            conn.commit()
            print("Database schema updated successfully.")
    except Exception as e:
        print(f"Error updating database: {e}")
