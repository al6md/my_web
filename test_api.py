import requests
import time

category_configs = [
    {'title': 'كتب خيالية', 'query': 'subject:fiction', 'cat': 'Fiction'},
    {'title': 'روايات رومانسية', 'query': 'subject:romance', 'cat': 'Romance'}
]

API_URL = 'https://www.googleapis.com/books/v1/volumes'
for cfg in category_configs:
    print(f"Testing {cfg['query']}...")
    try:
        r = requests.get(API_URL, params={
            'q': cfg['query'], 
            'maxResults': 4, 
            'orderBy': 'relevance', 
            'printType': 'books'
        }, timeout=5)
        print(r.status_code)
        if r.ok:
            data = r.json()
            items = data.get('items', [])
            total = data.get('totalItems', 0)
            print(f"Total: {total}, Items: {len(items)}")
            if items:
                print(items[0].get('volumeInfo', {}).get('title'))
        else:
            print(r.text)
    except Exception as e:
        print(f"Error: {e}")
