"""
Fix corrupted preferences - remove 'special:*' entries
"""
import sys
sys.path.insert(0, '.')

from flask_book_recommendation.app import create_app
from flask_book_recommendation.models import UserPreference
from flask_book_recommendation.extensions import db

app = create_app()
with app.app_context():
    # Find and delete bad preferences
    bad_prefs = UserPreference.query.filter(UserPreference.topic.like('special:%')).all()
    print(f"Found {len(bad_prefs)} bad preferences to delete:")
    for p in bad_prefs:
        print(f"  - User {p.user_id}: '{p.topic}' (weight: {p.weight})")
    
    if bad_prefs:
        for p in bad_prefs:
            db.session.delete(p)
        db.session.commit()
        print("\nDeleted successfully!")
    else:
        print("\nNo bad preferences found.")
    
    # Show remaining preferences 
    print("\nRemaining preferences for users:")
    remaining = UserPreference.query.order_by(UserPreference.weight.desc()).limit(10).all()
    for p in remaining:
        print(f"  User {p.user_id}: '{p.topic}' (weight: {p.weight})")
