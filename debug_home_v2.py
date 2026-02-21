
import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from flask import Flask, request
from flask_login import LoginManager, UserMixin, current_user

# Setup simple logging
logging.basicConfig(level=logging.DEBUG)

try:
    from flask_book_recommendation.app import create_app
    from flask_book_recommendation.extensions import db
    from flask_book_recommendation.models import User
    
    app = create_app()
    
    # Create a dummy user for testing if needed
    class MockUser(UserMixin):
        id = 1
        is_authenticated = True
        
    with app.test_request_context('/'):
        # Mock login
        from flask_login import login_user
        # We need to bypass actual DB user fetching for simple testing unless we have a real DB
        # But let's try to query a real user if possible, or fall back to mock
        
        print("Attempting to call home()...")
        try:
            from flask_book_recommendation.routes.main import home
            
            # Mock current_user
            # Flask-Login usually needs a user loader, but we can try to push a user
            # Alternatively, we can use app.test_client() which is better
            
            with app.test_client() as client:
                # Force login if implementation allows, or just test as guest first
                print("Testing as Guest...")
                resp = client.get('/')
                print(f"Guest Status: {resp.status_code}")
                
                # Setup User 1 with preferences
                with app.app_context():
                    u = User.query.get(1)
                    if u:
                        print(f"User 1 found: {u.email}")
                        from flask_book_recommendation.models import UserPreference
                        if not UserPreference.query.filter_by(user_id=1).first():
                             print("Adding dummy preferences for testing...")
                             db.session.add(UserPreference(user_id=1, topic="Data Science", weight=1.0))
                             db.session.add(UserPreference(user_id=1, topic="History", weight=0.8))
                             db.session.commit()
                    else:
                        print("User 1 NOT found! creating...")
                        # Create if missing (using raw SQL or model if possible/safe)
                        # Skip for now, assume seeded.
                        pass

                # Login as User 1
                with client.session_transaction() as sess:
                    sess['_user_id'] = '1'
                    sess['_fresh'] = True
                
                
                print("Testing as User ID 1...")
                resp = client.get('/')
                print(f"User Status: {resp.status_code}")
                
                if resp.status_code == 500:
                    print("Error detected as User!")

        except Exception as e:
            print(f"Caught Exception: {e}")
            import traceback
            traceback.print_exc()

except Exception as e:
    print(f"Setup Error: {e}")
    import traceback
    traceback.print_exc()
