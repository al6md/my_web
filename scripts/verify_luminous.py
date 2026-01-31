import sys
import os

# Ensure we can import the app
sys.path.append(os.getcwd())

from flask_book_recommendation.app import create_app, db
from flask_book_recommendation.models import User

def verify_updates():
    print("Starting Verification for Luminous Horizon...")
    app = create_app()
    client = app.test_client()

    with app.app_context():
        # 1. Check Homepage
        print("\nChecking Homepage (public)...")
        res = client.get('/')
        if res.status_code == 200:
            content = res.data.decode('utf-8')
            if 'luminous.css' in content:
                print("PASS: Luminous CSS linked.")
            else:
                print("FAIL: Luminous CSS NOT found!")
            
            if 'hero-orbs' in content:
                print("PASS: Hero Orbs found.")
            else:
                print("FAIL: Hero Orbs missing!")

            if 'book-carousel-3d' in content:
                print("PASS: 3D Carousel found.")
            else:
                print("FAIL: 3D Carousel missing!")
        else:
            print(f"FAIL: Homepage failed with {res.status_code}")

        # 2. Check Explore Page (public)
        print("\nChecking Explore Page (public)...")
        res = client.get('/explore/')
        if res.status_code == 200:
            content = res.data.decode('utf-8')
            if 'tab-mood' in content:
                print("PASS: Mood Tabs found.")
            else:
                print("FAIL: Mood Tabs missing!")
            if 'luminous.css' in content:
                 print("PASS: Luminous CSS available.")
            else:
                 print("FAIL: Luminous CSS missing on Explore!")
        else:
             print(f"FAIL: Explore Page failed with {res.status_code}")

        # 3. Simulate Logged-in User for Algorithms
        print("\nChecking Explore Page (Authenticated)...")
        # We need a user. Let's pick the first one or create dummy
        user = User.query.first()
        if user:
            print(f"Authenticating as user: {user.name} (ID: {user.id})")
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
            
            res = client.get('/explore/')
            if res.status_code == 200:
                content = res.data.decode('utf-8')
                # Check for new sections
                if 'special:cf' in content:
                    print("PASS: AI Collaborative Filtering section found.")
                else:
                    print("WARN: AI Collaborative Filtering section NOT found (maybe insufficient data?).")

                if 'special:topic-based' in content:
                    print("PASS: Topic-Based section found.")
                else:
                    print("WARN: Topic-Based section NOT found (maybe insufficient data?).")

                if 'special:because-you-read' in content:
                    print("PASS: 'Because You Read' section found.")
                else:
                    print("WARN: 'Because You Read' section NOT found.")
            else:
                print(f"FAIL: Auth Explore failed with {res.status_code}")
        else:
            print("WARN: No users found in DB to test authentication.")

if __name__ == "__main__":
    verify_updates()
