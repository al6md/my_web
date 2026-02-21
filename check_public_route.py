import sys
import os

# Set up path to import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask_book_recommendation.app import create_app

app = create_app()

with app.test_client() as client:
    print("Sending GET request to /public/books...")
    try:
        response = client.get('/public/books')
        print(f"Status Code: {response.status_code}")
        if response.status_code == 500:
            print("500 Error occurred. Please see stdout/stderr for traceback.")
        else:
            print("Request succeeded. No 500 error!")
    except Exception as e:
        import traceback
        traceback.print_exc()
