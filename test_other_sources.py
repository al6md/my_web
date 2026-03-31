import requests
import json

def test_gutenberg(query):
    print(f"\nTesting Gutenberg for: {query}")
    try:
        r = requests.get("https://gutendex.com/books", params={"search": query}, timeout=5)
        if r.ok:
            results = r.json().get("results", [])
            print(f"Found {len(results)} items")
            for b in results[:3]:
                print(f"- {b.get('title')}")
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

def test_openlib(query):
    print(f"\nTesting OpenLibrary for: {query}")
    try:
        r = requests.get("https://openlibrary.org/search.json", params={"q": query, "limit": 5}, timeout=5)
        if r.ok:
            docs = r.json().get("docs", [])
            print(f"Found {len(docs)} items")
            for d in docs[:3]:
                print(f"- {d.get('title')}")
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

def test_archive(query):
    print(f"\nTesting Archive for: {query}")
    try:
        search_query = f"{query} mediatype:texts"
        params = {"q": search_query, "rows": 5, "output": "json"}
        r = requests.get("https://archive.org/advancedsearch.php", params=params, timeout=5)
        if r.ok:
            data = r.json()
            docs = data.get("response", {}).get("docs", [])
            print(f"Found {len(docs)} items")
            for d in docs[:3]:
                print(f"- {d.get('title')}")
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

test_gutenberg("History")
test_openlib("History")
test_archive("History")
