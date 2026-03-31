import requests
import os
from dotenv import load_dotenv

# Load from flask_book_recommendation/.env
dotenv_path = "flask_book_recommendation/.env"
load_dotenv(dotenv_path)

API_URL = "https://www.googleapis.com/books/v1/volumes"
query = "subject:History"
params = {
    "q": query,
    "maxResults": 12,
    "startIndex": 0,
    "orderBy": "relevance",
    "printType": "books",
    "key": os.environ.get("GOOGLE_BOOKS_API_KEY")
}

print(f"Searching for: {query}")
print(f"API Key: {os.environ.get('GOOGLE_BOOKS_API_KEY')}")

try:
    r = requests.get(API_URL, params=params, timeout=5)
    print(f"Status Code: {r.status_code}")
    if r.ok:
        data = r.json()
        items = data.get("items", [])
        print(f"Found {len(items)} items")
        total_items = data.get("totalItems", 0)
        print(f"Total Items: {total_items}")
        for it in items[:3]:
            print(f"- {it.get('volumeInfo', {}).get('title')}")
    else:
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Exception: {e}")
