import requests
import os

def test_api():
    API_URL = "https://www.googleapis.com/books/v1/volumes"
    query = "subject:fiction"
    params = {
        "q": query, "maxResults": 5,
        "printType": "books"
    }
    print(f"Testing Google Books with {params}...")
    r = requests.get(API_URL, params=params)
    print(f"Status: {r.status_code}")
    print(f"URL: {r.url}")
    if r.ok:
        data = r.json()
        items = data.get("items", [])
        print(f"Items found: {len(items)}, Total reported: {data.get('totalItems')}")
        for it in items:
            print(f"- {it.get('volumeInfo', {}).get('title')}")
    else:
        print(f"Error: {r.text}")

if __name__ == "__main__":
    test_api()

